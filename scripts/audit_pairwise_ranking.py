"""Independent source, pair membership/labels, convex stationarity, targets and accounts."""

import argparse
import gzip
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict, deque
from itertools import pairwise
from pathlib import Path

import duckdb
import numpy as np
from audit_conditional_risk import compare, market_account_check, quote, read
from sparse_account_audit import audit_accounts, near

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json

FIELDS = (
    "volatility_20",
    "ret_20",
    "liquidity",
    "flow_consistency",
    "auction_tail_balance",
    "chip_path_efficiency",
)


def unzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def temporal_reference(history):
    f, a, c = map(list, zip(*history, strict=True))
    den = sum(map(abs, f))
    scale = max(map(abs, a))
    cubes = [(v / scale) ** 3 for v in a] if scale else [0.0] * 20
    ad = sum(map(abs, cubes))
    cd = sum(abs(v - u) for u, v in pairwise(c))
    return [
        sum(1 if v > 0 else -1 if v < 0 else 0 for v in f) / 20 * abs(sum(f)) / den if den else 0.0,
        sum(cubes) / ad if ad else 0.0,
        (c[-1] - c[0]) / cd if cd else 0.0,
    ]


def source_check(con, feature_cache, coverage, calendar):
    expected_calendar = [
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT trade_date FROM daily_source WHERE trade_date>=DATE '2022-01-01' ORDER BY 1"
        ).fetchall()
    ]
    if expected_calendar != calendar or calendar[-1] >= "2025-01-01":
        raise ValueError("source global calendar/boundary mismatch")
    histories, last, current, completed = {}, {}, {}, {}
    date_now = None

    def finish():
        if date_now is not None:
            completed[date_now] = len(current)
            if date_now in feature_cache:
                compare(current, feature_cache[date_now], "raw temporal fields " + date_now)

    cur = con.execute("SELECT * FROM eligible ORDER BY idx,instrument")
    n = 0
    for batch in iter(lambda: cur.fetchmany(25000), []):
        for idx, dt, name, vol, ret, adv, flow, auction, width in batch:
            dt = str(dt)
            if date_now != dt:
                finish()
                date_now, current = dt, {}
            raw = [flow, auction, width]
            if not all(v is not None and math.isfinite(v) for v in raw):
                histories.pop(name, None)
                last.pop(name, None)
                continue
            if last.get(name) != idx - 1:
                histories[name] = deque(maxlen=20)
            histories[name].append(raw)
            last[name] = idx
            risk = [vol, ret, adv]
            if len(histories[name]) == 20 and all(v is not None and math.isfinite(v) for v in risk):
                current[name] = dict(
                    zip(FIELDS, risk + temporal_reference(histories[name]), strict=True)
                )
                n += 1
    finish()
    compare(
        [{"date": d, "common": completed.get(d, 0)} for d in calendar],
        coverage,
        "raw feature coverage",
    )
    if not set(feature_cache) <= set(calendar):
        raise ValueError("unexpected rank feature dates")
    return n


def ranks_reference(features):
    names = sorted(features, key=lambda n: (features[n]["volatility_20"], n))
    vol, cells = defaultdict(list), defaultdict(list)
    for i, n in enumerate(names):
        vol[(i * 5) // len(names)].append(n)
    for v, names in vol.items():
        names.sort(key=lambda n: (features[n]["liquidity"], n))
        for i, n in enumerate(names):
            cells[v * 4 + (i * 4) // len(names)].append(n)
    out = {}
    for c, names in cells.items():
        for n in names:
            out[n] = {"cell": c, "x": [], "vol": features[n]["volatility_20"]}
        for field in FIELDS:
            tied = defaultdict(list)
            for n in names:
                tied[features[n][field]].append(n)
            offset = 0
            for value in sorted(tied):
                group = tied[value]
                rank = offset + (len(group) + 1) / 2
                for n in group:
                    out[n]["x"].append(2 * rank / (len(names) + 1) - 1)
                offset += len(group)
    return out


def fixed_hash(n):
    return hashlib.sha256(("v11.19:184:" + n).encode()).hexdigest()


def pair_reference(con, calendar, cache):
    prefix = [d for d in calendar if "2022-01-01" <= d < "2024-01-01"][:-5]
    rows, requests = [], []
    for i in range(0, len(prefix) - 21, 5):
        dt = prefix[i]
        groups = defaultdict(list)
        for n, r in cache[dt].items():
            groups[r["cell"]].append(n)
        for c, ns in sorted(groups.items()):
            ns = sorted(ns, key=lambda n: (fixed_hash(n), n))[:64]
            for j in range(0, len(ns) - 1, 2):
                a, b = ns[j : j + 2]
                rows.append(
                    {
                        "date": dt,
                        "entry_date": prefix[i + 1],
                        "label_end": prefix[i + 21],
                        "cell": c,
                        "left": a,
                        "right": b,
                        "left_x": cache[dt][a]["x"],
                        "right_x": cache[dt][b]["x"],
                    }
                )
                requests += [(dt, n, prefix[i + 1], prefix[i + 21]) for n in (a, b)]
    con.execute(
        """CREATE TABLE requests AS SELECT (value->>0)::DATE signal_date,
        value->>1 instrument,(value->>2)::DATE entry,(value->>3)::DATE endpoint
        FROM json_each(?)""",
        [json.dumps(requests)],
    )
    con.execute("""CREATE TABLE endpoints AS SELECT q.*,e.op entry_price,z.op end_price
        FROM requests q LEFT JOIN valid_bars e ON e.date=q.entry AND e.instrument=q.instrument
        LEFT JOIN valid_bars z ON z.date=q.endpoint AND z.instrument=q.instrument""")
    # Only genuinely missing endpoints need a bounded historical mark lookup.
    con.execute("""CREATE TABLE stale AS SELECT e.signal_date,e.instrument,s.cp,s.date FROM endpoints e
        LEFT JOIN LATERAL (SELECT cp,date FROM valid_bars v WHERE v.instrument=e.instrument
        AND v.date>=e.entry AND v.date<e.endpoint ORDER BY date DESC LIMIT 1) s ON true
        WHERE e.entry_price IS NOT NULL AND e.end_price IS NULL""")
    legs = {}
    for (
        dt,
        n,
        entry,
        end,
        ep,
        zp,
        sp,
        sd,
    ) in con.execute("""SELECT e.signal_date,e.instrument,e.entry,e.endpoint,
        e.entry_price,e.end_price,s.cp,s.date FROM endpoints e LEFT JOIN stale s USING(signal_date,instrument)""").fetchall():
        valid, fresh = ep is not None, zp is not None
        price = (zp if fresh else sp if sp is not None else ep) if valid else None
        legs[(str(dt), n)] = {
            "entry_valid": valid,
            "return": price / ep - 1 if valid else None,
            "entry_price": ep,
            "end_price": price,
            "mark_date": str(end if fresh else sd if sd else entry) if valid else None,
            "fresh_end": valid and fresh,
        }
    for r in rows:
        r["left_label"], r["right_label"] = [legs[(r["date"], r[k])] for k in ("left", "right")]
        r["supported"] = r["left_label"]["entry_valid"] and r["right_label"]["entry_valid"]
    return rows


def phi(x, basis, kind):
    z = x[:3] if kind == "risk" else x[:]
    return (
        z + [z[i] * z[j] for i in range(len(z)) for j in range(i, len(z))]
        if basis == "quadratic"
        else z
    )


def matrix_reference(rows, basis, kind):
    counts = Counter(r["date"] for r in rows)
    weights = [1 / (len(counts) * counts[r["date"]]) for r in rows]
    x = [
        [
            a - b
            for a, b in zip(
                phi(r["left_x"], basis, kind), phi(r["right_x"], basis, kind), strict=True
            )
        ]
        for r in rows
    ]
    outcomes = [[r["left_label"]["return"], r["right_label"]["return"]] for r in rows]
    if kind == "shuffle":
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[(r["date"], r["cell"])].append(i)
        for indices in groups.values():
            flat = [v for i in indices for v in outcomes[i]]
            shift = len(flat) // 3
            for j, i in enumerate(indices):
                outcomes[i] = [flat[(2 * j + k - shift) % len(flat)] for k in (0, 1)]
    delta = [a - b for a, b in outcomes]
    y = delta if kind == "regression" else [1.0 if d > 0 else 0.0 if d < 0 else 0.5 for d in delta]
    return {"x": x, "y": y, "weights": weights}


def model_check(model, pairs, calendar):
    y, b, k = model["year"], model["basis"], model["kind"]
    cutoff = [d for d in calendar if "2022-01-01" <= d < f"{y}-01-01"][-6]
    rows = [r for r in pairs if r["supported"] and r["label_end"] <= cutoff]
    sessions = sorted({r["date"] for r in rows})
    if (
        model["fit_cutoff"] != cutoff
        or model["training_signal_sessions"] != sessions
        or len(sessions) < 30
        or model["maximum_label_end"] != max(r["label_end"] for r in rows)
        or model["training_pairs"] != len(rows)
        or model["training_rows_sha256"] != sha256_json(rows)
    ):
        raise ValueError("mature training prefix/hash mismatch")
    matrix = matrix_reference(rows, b, k)
    if sha256_json(matrix) != model["training_design_sha256"]:
        raise ValueError("independent pair basis/date-weight/shuffle matrix mismatch")
    x, w, target = np.asarray(matrix["x"]), np.asarray(matrix["weights"]), np.asarray(matrix["y"])
    beta = np.asarray(model["weights"])
    z = x @ beta
    if k == "regression":
        residual, curvature = z - target, np.ones(len(z))
        loss = float(np.sum(w * (z - target) ** 2) / 2)
    else:
        p = np.asarray(
            [1 / (1 + math.exp(-v)) if v >= 0 else math.exp(v) / (1 + math.exp(v)) for v in z]
        )
        residual, curvature = p - target, p * (1 - p)
        loss = sum(
            wi * (max(v, 0) + math.log1p(math.exp(-abs(v))) - yi * v)
            for wi, v, yi in zip(w, z, target, strict=True)
        )
    gradient = x.T @ (w * residual) + 0.01 * beta
    hessian = x.T @ ((w * curvature)[:, None] * x) + 0.01 * np.eye(len(beta))
    if max(abs(gradient)) > 1.1e-9 or min(np.linalg.eigvalsh(hessian)) < 0.00999999:
        raise ValueError("independent strictly convex stationary solution failed")
    near(
        loss + 0.005 * float(beta @ beta),
        model["optimizer"]["loss_trace"][-1],
        "training loss",
        1e-10,
    )
    compare(model["date_weight_range"], [1 / len(sessions)] * 2, "equal date weights")
    if model["training_signal_dates"] != len(sessions) or model["parameter_count"] != len(beta):
        raise ValueError("model dimensions mismatch")


def target_reference(calendar, cache, policy, models):
    window = [d for d in calendar if d >= "2023-01-01"]
    holdings = [() for _ in range(4)]
    live = [{} for _ in range(4)]
    targets, details = [], [[] for _ in range(4)]
    for i, dt in enumerate(window):
        refresh = False
        signal = window[i - 1] if i else dt
        for slot, phase in enumerate((0, 5, 10, 15)):
            if i < phase + 1 or (i - phase - 1) % 20:
                continue
            refresh = True
            rows = cache[signal]
            if policy in ("hash", "lowvol"):
                scores = {
                    n: int(fixed_hash(n), 16) if policy == "hash" else -r["vol"]
                    for n, r in rows.items()
                }
            else:
                m = models[int(dt[:4])]
                scores = {
                    n: sum(
                        a * b
                        for a, b in zip(
                            phi(r["x"], m["basis"], m["kind"]), m["weights"], strict=True
                        )
                    )
                    for n, r in rows.items()
                }
            selected = []
            for cell in range(20):
                ordered = sorted(
                    (n for n, r in rows.items() if r["cell"] == cell), key=lambda n: (-scores[n], n)
                )
                chosen = [n for n in ordered[:3] if n in holdings[slot]][:2]
                for n in ordered:
                    if len(chosen) == 2:
                        break
                    if n not in chosen:
                        chosen.append(n)
                selected.extend(chosen)
            selected.sort()
            details[slot].append(
                {
                    "date": signal,
                    "phase": phase,
                    "eligible": len(rows),
                    "selected": len(selected),
                    "new_members": len(set(selected) - set(holdings[slot])),
                    "scores_sha256": sha256_json(scores),
                }
            )
            holdings[slot] = selected
            live[slot] = {n: 0.025 for n in selected}
        weights = {}
        if refresh:
            for sleeve in live:
                for n, v in sleeve.items():
                    weights[n] = weights.get(n, 0) + v / 4
        targets.append(
            {
                "trade_date": dt,
                "decided_at": signal + ("T23:59:59+08:00" if i else "T08:00:00+08:00"),
                "weights": weights,
                "rebalance": refresh,
                "forced_exits": [],
            }
        )
    return targets, [d for ds in details for d in ds]


def native_check(output, result, models):
    with sqlite3.connect(
        f"file:{(output / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        rows = db.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if (
            len(rows) != 24
            or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 32
        ):
            raise ValueError("native24trials32fits required")
        seen = set()
        for tid, hp, rr, ss, code in rows:
            p, stages = json.loads(hp), json.loads(ss)
            key = p["key"]
            seen.add(key)
            if (
                p not in result["spec"]["plans"]
                or json.loads(rr) != result["records"][key]
                or code != result["spec"]["runtime_code_sha256"]
            ):
                raise ValueError("native result identity mismatch")
            fits = db.execute(
                "SELECT evidence_json,evidence_sha256 FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                (tid,),
            ).fetchall()
            expected = (
                []
                if p["basis"] == "none"
                else [
                    {
                        "stage_id": str(y),
                        "training_not_before": "2022-01-01",
                        "training_not_after": f"{y - 1}-12-31",
                        "prediction_start": f"{y}-01-01",
                        "prediction_end": f"{y}-12-31",
                    }
                    for y in (2023, 2024)
                ]
            )
            if stages != expected or len(stages) != len(fits):
                raise ValueError("native supervision contract mismatch")
            payload = []
            for stage, (raw, sha) in zip(stages, fits, strict=True):
                f = json.loads(raw)
                mk, y = key.rsplit("-", 1)[0], int(stage["stage_id"])
                m = models[mk][y]
                if (
                    sha256_json(f) != sha
                    or f["stage"] != stage
                    or f["model_content_sha256"] != sha256_json(m)
                    or f["artifact_sha256"] != result["models_sha256"][f"{mk}-{y}"]
                    or f["training_signal_sessions"] != m["training_signal_sessions"]
                    or f["training_end"] != m["fit_cutoff"]
                    or f["maximum_label_end"] != m["maximum_label_end"]
                    or not f["maximum_label_end"] <= f["training_end"] < stage["prediction_start"]
                ):
                    raise ValueError("native fit maturity/artifact mismatch")
                payload.append(f)
            if sha256_json(payload) != result["records"][key]["fit_lineage_sha256"]:
                raise ValueError("fit lineage digest mismatch")
        if seen != set(result["records"]):
            raise ValueError("native candidate set mismatch")


def audit(output, inputs):
    output, inputs = Path(output).resolve(), Path(inputs).resolve()
    result = read(output / "RESULT.json")
    spec = result["spec"]
    if protected_digest([Path(p) for p in spec["protected_files"]])[0] != spec[
        "protected_before"
    ] or any(file_sha(p) != s for p, s in spec["protected_files"].items()):
        raise ValueError("protected source/evidence changed")
    for field, name in (
        ("auditor_sha256", "audit_pairwise_ranking.py"),
        ("audit_query_sha256", "pairwise_source_audit.sql"),
    ):
        if file_sha(Path(__file__).with_name(name)) != spec[field]:
            raise ValueError("preregistered auditor changed")
    calendar = read(output / "calendar.json")
    features, cache = unzip(output / "feature_cache.json.gz"), unzip(output / "rank_cache.json.gz")
    saved_pairs = unzip(output / "training_pairs.json.gz")
    if set(features) != set(cache):
        raise ValueError("rank source dates mismatch")
    query = Path(__file__).with_name("pairwise_source_audit.sql").read_text(encoding="utf-8")
    with duckdb.connect(
        config={"threads": 4, "memory_limit": "4GB", "temp_directory": str(output / "audit-temp")}
    ) as con:
        for name in ("daily", "fund_flow", "auction", "chip"):
            con.execute(
                f"CREATE VIEW {name}_source AS SELECT * FROM read_parquet({quote(inputs / (name + '.parquet'))})"
            )
        con.execute(
            "CREATE TABLE calendar AS SELECT key::INTEGER idx,value::DATE date FROM json_each(?)",
            [json.dumps(calendar)],
        )
        con.execute(query)
        feature_count = source_check(con, features, read(output / "coverage.json"), calendar)
        for dt, f in features.items():
            compare(ranks_reference(f), cache[dt], "current cells/ranks " + dt)
        references = pair_reference(con, calendar, cache)
        compare(references, saved_pairs, "source full pair membership/outcomes")
        market_evidence = market_account_check(con, output)
        # All adjusted shares reconcile to source opening fills; valuation writeoffs do not dispose shares.
        con.execute("""CREATE TABLE fills AS SELECT d.date::DATE date,o.instrument,sum(o.executed_notional/b.op) delta
           FROM saved_accounts d CROSS JOIN unnest(d.orders) x(o) JOIN valid_bars b
           ON b.date=d.date::DATE AND b.instrument=o.instrument GROUP BY d.date,o.instrument""")
        # Per-account share continuity is checked below using a bounded source price dictionary.
        prices = {
            (str(d), n): p
            for d, n, p in con.execute(
                "SELECT date,instrument,op FROM valid_bars WHERE date>=DATE '2023-01-01'"
            ).fetchall()
        }
    del features
    print(
        json.dumps(
            {"raw_feature_rows": feature_count, "rank_dates": len(cache), "pairs": len(references)}
        ),
        flush=True,
    )
    models = {}
    for b in ("linear", "quadratic"):
        for k in ("full", "risk", "shuffle", "regression"):
            mk = f"{b}-{k}"
            models[mk] = {}
            for y in (2023, 2024):
                p = output / f"models/{mk}-{y}.json"
                if file_sha(p) != result["models_sha256"][f"{mk}-{y}"]:
                    raise ValueError("model file changed")
                m = read(p)
                if (m["year"], m["basis"], m["kind"]) != (y, b, k):
                    raise ValueError("model identity differs from declared experiment")
                model_check(m, saved_pairs, calendar)
                models[mk][y] = m
    diagnostics = read(output / "selection_diagnostics.json")
    seen = set()
    for p in spec["plans"]:
        tk = p["key"].rsplit("-", 1)[0]
        if tk not in seen:
            if p["policy"].startswith("original_"):
                base = "lowvol" if p["policy"] == "original_lowvol" else "stable_lowrisk"
                targets = read(spec["original_target_files"][base])
            else:
                targets, detail = target_reference(calendar, cache, p["policy"], models.get(tk))
                compare(detail, diagnostics[tk], "decision provenance")
            compare(
                targets, read(output / f"targets/{tk}.json"), "independent target reconstruction"
            )
            seen.add(tk)
        shares = {}
        with (output / f"accounts/{p['key']}.jsonl").open(encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                for o in d["orders"]:
                    if abs(o["executed_notional"]) > 1e-12:
                        price = prices.get((d["date"], o["instrument"]))
                        if price is None:
                            raise ValueError("fill without source open")
                        shares[o["instrument"]] = (
                            shares.get(o["instrument"], 0) + o["executed_notional"] / price
                        )
                actual = {x["instrument"]: x["shares"] for x in d["positions"]}
                for n in set(actual) | set(shares):
                    near(actual.get(n, 0), shares.get(n, 0), "source fill share continuity", 1e-7)
    rows, balance = audit_accounts(output, result, expected_accounts=24)
    native_check(output, result, models)
    for identity, costs in result["checks"].items():
        for cost, expected in costs.items():
            c = result["records"][f"{identity}-full-{cost}"]
            controls = [
                result["records"][f"{identity}-{k}-{cost}"]
                for k in ("risk", "shuffle", "regression")
            ] + [
                result["records"][f"control-{k}-{cost}"]
                for k in ("hash", "lowvol", "original_lowvol", "original_stable")
            ]
            computed = {
                "accounts": c["audit"]["pass"] and all(x["audit"]["pass"] for x in controls),
                "both_years_positive": all(v > 0 for v in c["years"].values()),
                "sharpe": c["pooled_sharpe"] >= 0.7,
                "drawdown": c["metrics"]["max_drawdown"] >= -0.25,
                "total_increment": all(
                    c["metrics"]["net_total_return"] - x["metrics"]["net_total_return"] >= 0.03
                    for x in controls
                ),
                "annual_increment": all(
                    c["years"][y] - x["years"][y] >= -0.05
                    for y in ("2023", "2024")
                    for x in controls
                ),
            }
            for y in ("2023", "2024"):
                ds = [d for d in diagnostics[identity + "-full"] if d["date"].startswith(y)]
                computed["coverage_" + y] = (
                    bool(ds) and sum(d["selected"] for d in ds) / (40 * len(ds)) >= 0.95
                )
            compare(computed, expected, "independent economic screen")
        if result["screen_survived"][identity] != all(all(c.values()) for c in costs.values()):
            raise ValueError("survival conjunction failed")
    if (
        read(output / "first_read_reservations.json")
        != {"trials": spec["plans"], "spec_sha256": sha256_json(spec)}
        or result["raw_global_trial_lower_bound"] != 3624
        or result["completed_trials"] != 24
        or result["validated_alpha"]
    ):
        raise ValueError("reservation/debt/certification mismatch")
    summary = {
        "version": result["version"],
        "rows": rows,
        "checks": result["checks"],
        "screen_survived": result["screen_survived"],
        "source_result_sha256": file_sha(output / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "raw_trial_lower_bound": 3624,
        "new_trials": 24,
        "models": 16,
        "native_fits": 32,
        "target_sets": len(seen),
        "training_pairs": len(saved_pairs),
        "source_feature_rows": feature_count,
        "rank_dates": len(cache),
        "raw_account_checks": market_evidence,
        "maximum_balance_residual_cny": balance,
        "independent_audit_pass": True,
        "validated_alpha": False,
        "statistics": result["statistics"],
    }
    write_json(
        output / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "summary": summary,
            "source_query": query,
            "evidence_hashes": {
                p.relative_to(output).as_posix(): file_sha(p)
                for p in output.rglob("*")
                if p.is_file()
            },
        },
    )
    print(
        json.dumps({"independent_audit": "PASS", "accounts": 24, "models": 16, "native_fits": 32}),
        flush=True,
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
