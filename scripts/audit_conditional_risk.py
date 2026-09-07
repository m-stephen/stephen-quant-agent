"""Independent source SQL, normal equations, exposure/target/account and native audit."""

import argparse
import csv
import gzip
import json
import math
import sqlite3
from pathlib import Path

import duckdb
from sparse_account_audit import audit_accounts, near

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def quote(p):
    return "'" + str(p).replace("'", "''") + "'"


def compare(a, b, why):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            raise ValueError(why + " keys")
        for k in a:
            compare(a[k], b[k], why + "/" + str(k))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            raise ValueError(why + " length")
        for x, y in zip(a, b, strict=True):
            compare(x, y, why)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        near(a, b, why, 1e-10)
    elif a != b:
        raise ValueError(why)


def source_references(con):
    baskets = {
        str(d): names
        for d, names in con.execute(
            "SELECT date,list(instrument ORDER BY rn) FROM state_names WHERE rn<=200 GROUP BY date"
        ).fetchall()
    }
    states = []
    for i, d, n, *x in con.execute("SELECT * FROM state_values ORDER BY idx").fetchall():
        states.append(
            {
                "date": str(d),
                "index": i,
                "eligible": n,
                "available": n >= 200,
                "x": x if n >= 200 else None,
                "basket": baskets.get(str(d), []) if n >= 200 else [],
            }
        )
    bydate = {s["date"]: s for s in states}
    labels = []
    for d, entry, end, r, n, fresh in con.execute(
        "SELECT * FROM label_values ORDER BY signal_date"
    ).fetchall():
        labels.append(
            {
                "date": str(d),
                "entry_date": str(entry),
                "label_end": str(end),
                "return": r,
                "entries": n,
                "fresh": fresh,
                "x": bydate[str(d)]["x"],
                "supported": n >= 190 and fresh >= 0.95 * n,
            }
        )
    return states, labels


def components_check(con, path):
    refs = iter(
        con.execute("SELECT * FROM proxy_components ORDER BY signal_date,instrument").fetchall()
    )
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        actual = sorted(csv.DictReader(f), key=lambda r: (r["signal_date"], r["instrument"]))
    n = 0
    keys = (
        "signal_date",
        "instrument",
        "entry_date",
        "label_end",
        "entry_price",
        "end_mark",
        "mark_date",
        "return",
    )
    for row in actual:
        ref = next(refs, None)
        if ref is None:
            raise ValueError("extra proxy component")
        for k, v in zip(keys, ref, strict=True):
            a = row[k]
            if k in ("entry_price", "end_mark", "return"):
                compare(float(a) if a else None, v, "proxy component " + k)
            elif (a or None) != (str(v) if v is not None else None):
                raise ValueError("proxy component identity/clock")
        n += 1
    if next(refs, None) is not None:
        raise ValueError("missing proxy component")
    return n


def solve(matrix, vector):
    """Small pivoted elimination, independent of production NumPy ridge solver."""
    a = [list(row) + [v] for row, v in zip(matrix, vector, strict=True)]
    for i in range(len(a)):
        p = max(range(i, len(a)), key=lambda j: abs(a[j][i]))
        a[i], a[p] = a[p], a[i]
        if abs(a[i][i]) < 1e-14:
            raise ValueError("singular reference equation")
        divisor = a[i][i]
        a[i] = [v / divisor for v in a[i]]
        for j in range(len(a)):
            if j != i:
                ratio = a[j][i]
                a[j] = [x - ratio * y for x, y in zip(a[j], a[i], strict=True)]
    return [row[-1] for row in a]


def allocation(model, x, rule):
    z = [(v - c) / s for v, c, s in zip(x, model["center"], model["scale"], strict=True)]
    mu = model["mean_return"] + sum(a * b for a, b in zip(z, model["beta_return"], strict=True))
    q = model["mean_second"] + sum(a * b for a, b in zip(z, model["beta_second"], strict=True))
    numerator = model["mean_return"] if rule == "risk_only" else mu
    denominator = model["mean_second"] if rule == "mean" else q
    value = numerator / (10 * max(model["second_floor"], denominator))
    return math.floor(max(0.25, min(1.0, value)) * 4 + 0.5) / 4


def fit_reference(labels, calendar, year, shuffled):
    cutoff = [d for d in calendar if "2022-01-01" <= d < f"{year}-01-01"][-6]
    rows = [
        r
        for r in labels
        if r["supported"]
        and "2022-01-01" <= r["date"] < r["entry_date"] <= r["label_end"] <= cutoff
    ]
    n = len(rows)
    if n < 30:
        raise ValueError("insufficient reference training")
    center = [sum(r["x"][j] for r in rows) / n for j in range(4)]
    scale = [math.sqrt(sum((r["x"][j] - center[j]) ** 2 for r in rows) / n) for j in range(4)]
    scale = [s if s > 1e-12 else 1.0 for s in scale]
    z = [[(v - c) / s for v, c, s in zip(r["x"], center, scale, strict=True)] for r in rows]
    shift = n // 3 if shuffled else 0
    y = [rows[(i - shift) % n]["return"] for i in range(n)]
    mu = sum(y) / n
    qbar = sum(v * v for v in y) / n
    matrix = [
        [sum(v[i] * v[j] for v in z) + (n if i == j else 0) for j in range(4)] for i in range(4)
    ]
    beta = []
    for values, m in ((y, mu), ([v * v for v in y], qbar)):
        vector = [sum(v[j] * (r - m) for v, r in zip(z, values, strict=True)) for j in range(4)]
        beta.append(solve(matrix, vector))
    model = {
        "year": year,
        "fit_cutoff": cutoff,
        "maximum_label_end": max(r["label_end"] for r in rows),
        "training_signal_sessions": [r["date"] for r in rows],
        "training_signal_dates": n,
        "training_rows_sha256": sha256_json(rows),
        "shuffled": bool(shuffled),
        "rotation": shift,
        "assigned_label_dates": [rows[(i - shift) % n]["date"] for i in range(n)],
        "center": center,
        "scale": scale,
        "mean_return": mu,
        "mean_second": qbar,
        "second_floor": max(1e-8, 0.1 * qbar),
        "beta_return": beta[0],
        "beta_second": beta[1],
    }
    model["training_mean_exposure"] = {
        rule: sum(allocation(model, r["x"], rule) for r in rows) / n
        for rule in ("mean", "mean_second", "risk_only")
    }
    return model


def prediction_reference(states, models):
    out = {}
    window = [i for i, s in enumerate(states) if s["date"] >= "2023-01-01"]
    for i in window[1:]:
        dt = states[i]["date"]
        s = states[i - 1]
        m = models[int(dt[:4])]
        if not m["fit_cutoff"] < s["date"] < dt:
            raise ValueError("prediction reference chronology")
        out[dt] = {
            "signal_date": s["date"],
            "available": s["available"],
            **{
                rule: allocation(m, s["x"], rule) if s["available"] else 0.25
                for rule in ("mean", "mean_second", "risk_only")
            },
            "training_mean": m["training_mean_exposure"],
        }
    return out


def target_reference(base, predictions, rule, policy):
    live = {}
    exposure = 1.0
    out = []
    diagnostics = []
    for i, t in enumerate(base):
        refresh = i > 0 and i % 5 == 1
        if t["rebalance"]:
            live = dict(t["weights"])
        for n in t["forced_exits"]:
            live.pop(n, None)
        if refresh:
            p = predictions[t["trade_date"]]
            if policy == "fixed":
                exposure = p["training_mean"][rule]
            elif policy == "lag20":
                lag = predictions.get(base[i - 20]["trade_date"]) if i >= 20 else None
                exposure = lag[rule] if lag else p["training_mean"][rule]
            else:
                exposure = p[rule]
        rebalance = t["rebalance"] or refresh
        weights = {n: v * exposure for n, v in live.items()} if rebalance else {}
        out.append(
            {
                **t,
                "weights": weights,
                "rebalance": rebalance,
                "decided_at": base[i - 1]["trade_date"] + "T23:59:59+08:00"
                if i
                else t["decided_at"],
            }
        )
        diagnostics.append(
            {
                "date": t["trade_date"],
                "allocation": exposure,
                "refresh": refresh,
                "base_weight": sum(live.values()),
                "target_weight": sum(weights.values()),
            }
        )
    return out, diagnostics


def native_check(output, result, models):
    with sqlite3.connect(
        f"file:{(output / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        rows = db.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if (
            len(rows) != 44
            or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 72
        ):
            raise ValueError("native budget/fits mismatch")
        for tid, hp, rr, ss, code in rows:
            p, stages = json.loads(hp), json.loads(ss)
            if (
                p not in result["spec"]["plans"]
                or json.loads(rr) != result["records"][p["key"]]
                or code != result["spec"]["runtime_code_sha256"]
            ):
                raise ValueError("native result identity mismatch")
            fits = db.execute(
                "SELECT evidence_json,evidence_sha256 FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                (tid,),
            ).fetchall()
            if len(fits) != len(stages) or len(stages) != (
                0 if p["policy"] in ("original", "unscaled") else 2
            ):
                raise ValueError("native supervised stages mismatch")
            a = "shuffle" if p["policy"] == "shuffle" else "direct"
            payload = []
            for stage, (raw, sha) in zip(stages, fits, strict=True):
                f = json.loads(raw)
                y = int(stage["stage_id"])
                m = models[a][y]
                if (
                    sha256_json(f) != sha
                    or f["stage"] != stage
                    or "fit_kind" in stage
                    or f["artifact_sha256"] != result["models_sha256"][f"{a}-{y}"]
                    or f["model_content_sha256"] != sha256_json(m)
                    or f["training_signal_sessions"] != m["training_signal_sessions"]
                    or f["maximum_label_end"] != m["maximum_label_end"]
                    or f["training_end"] != m["fit_cutoff"]
                    or not f["maximum_label_end"] <= f["training_end"] < stage["prediction_start"]
                ):
                    raise ValueError("native fitted evidence mismatch")
                payload.append(f)
            if sha256_json(payload) != result["records"][p["key"]]["fit_lineage_sha256"]:
                raise ValueError("native fit lineage digest mismatch")


def market_account_check(con, output):
    """Verify recorded liquidity caps and current-close marks against raw source."""
    con.execute(
        f"CREATE OR REPLACE VIEW saved_accounts AS SELECT * FROM read_json_auto({quote(output / 'accounts/*.jsonl')})"
    )
    con.execute("""CREATE OR REPLACE TABLE source_caps AS WITH a AS (
        SELECT *,avg(amount*1000) OVER(PARTITION BY instrument ORDER BY trade_date
        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS adv FROM daily_source), b AS (
        SELECT *,lag(adv) OVER(PARTITION BY instrument ORDER BY trade_date) AS prior_adv FROM a)
        SELECT trade_date AS date,instrument,greatest(0,coalesce(prior_adv,0))*.05 AS cap
        FROM b WHERE open>0 AND close>0 AND adjustment_factor>0
        AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor)""")
    cap_bad = con.execute("""SELECT count(*) FROM saved_accounts d CROSS JOIN unnest(d.orders) x(o)
        LEFT JOIN source_caps b ON b.date=d.date::DATE AND b.instrument=o.instrument
        WHERE abs(o.capacity_notional-coalesce(b.cap,0))>1e-5""").fetchone()[0]
    mark_bad = con.execute("""SELECT count(*) FROM saved_accounts d CROSS JOIN unnest(d.positions) x(p)
        LEFT JOIN valid_bars b ON b.date=d.date::DATE AND b.instrument=p.instrument
        WHERE (p.source='current_close' AND (b.cp IS NULL OR abs(p.mark_price-b.cp)>1e-9*greatest(1,b.cp)))
        OR (p.source!='current_close' AND b.cp IS NOT NULL)
        OR (p.source='conservative_zero_writeoff' AND p.mark_price!=0)""").fetchone()[0]
    if cap_bad or mark_bad:
        raise ValueError("raw-source capacity/current-price mismatch")
    return {"capacity_mismatches": cap_bad, "current_price_mismatches": mark_bad}


def audit(output, inputs):
    output, inputs = Path(output).resolve(), Path(inputs).resolve()
    r = read(output / "RESULT.json")
    spec = r["spec"]
    if protected_digest([Path(p) for p in spec["protected_files"]])[0] != spec["protected_before"]:
        raise ValueError("protected bytes changed")
    if any(file_sha(Path(p)) != sha for p, sha in spec["protected_files"].items()):
        raise ValueError("protected/source digest mismatch")
    calendar = read(output / "calendar.json")
    actual_states = read(output / "states.json")
    saved_labels = read(output / "proxy_labels.json")
    query = Path("scripts/conditional_risk_source_audit.sql").read_text(encoding="utf-8")
    with duckdb.connect(
        config={"threads": 4, "memory_limit": "4GB", "temp_directory": str(output / "audit-temp")}
    ) as con:
        con.execute(
            f"CREATE VIEW daily_source AS SELECT * FROM read_parquet({quote(inputs / 'daily.parquet')})"
        )
        con.execute(
            "CREATE TABLE calendar AS SELECT key::INTEGER idx,value::DATE date FROM json_each(?)",
            [json.dumps(calendar)],
        )
        con.execute(query)
        states, labels = source_references(con)
        compare(actual_states, states, "raw-source state")
        compare(saved_labels, labels, "raw-source proxy label")
        components = components_check(con, output / "proxy_components.csv.gz")
        market_evidence = market_account_check(con, output)
        print(
            json.dumps({"source_states": len(states), "proxy_components": components}), flush=True
        )
    models = {a: {} for a in ("direct", "shuffle")}
    for a, model_set in models.items():
        for y in (2023, 2024):
            p = output / f"models/{a}-{y}.json"
            m = read(p)
            if file_sha(p) != r["models_sha256"][f"{a}-{y}"]:
                raise ValueError("model artifact changed")
            ref = fit_reference(labels, calendar, y, a == "shuffle")
            # Numeric source reconstructions can differ in last-bit aggregation.
            # Exact digest instead binds the saved rows already independently checked.
            exact = fit_reference(saved_labels, calendar, y, a == "shuffle")
            ref["training_rows_sha256"] = exact["training_rows_sha256"]
            compare(m, ref, "independent fitted coefficients/calibration")
            model_set[y] = m
    predictions = {a: prediction_reference(states, ms) for a, ms in models.items()}
    for a, p in predictions.items():
        compare(read(output / f"predictions-{a}.json"), p, "independent predictions")
    anchors = {b: read(p) for b, p in spec["original_target_files"].items()}
    diagnostics = read(output / "allocation_diagnostics.json")
    seen = set()
    for p in spec["plans"]:
        tk = p["key"].rsplit("-", 1)[0]
        if tk in seen:
            continue
        seen.add(tk)
        if p["policy"] in ("original", "unscaled"):
            targets = anchors[p["base"]]
        else:
            targets, detail = target_reference(
                anchors[p["base"]],
                predictions["shuffle" if p["policy"] == "shuffle" else "direct"],
                p["rule"],
                p["policy"],
            )
            compare(diagnostics[tk], detail, "allocation diagnostics")
        compare(read(output / f"targets/{tk}.json"), targets, "independent targets")
    print(json.dumps({"model_audit": 4, "target_sets": len(seen)}), flush=True)
    rows, balance = audit_accounts(output, r, expected_accounts=44)
    native_check(output, r, models)
    for identity, costs in r["checks"].items():
        for cost, expected in costs.items():
            c = r["records"][f"{identity}-model-{cost}"]
            base = c["base"]
            controls = [
                r["records"][f"{identity}-{p}-{cost}"] for p in ("fixed", "lag20", "shuffle")
            ] + [r["records"][f"{base}-{p}-{cost}"] for p in ("risk_only", "unscaled", "original")]
            computed = {
                "accounts": c["audit"]["pass"] and all(x["audit"]["pass"] for x in controls),
                "both_years_positive": all(c["years"][y] > 0 for y in ("2023", "2024")),
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
                ds = [s for s in states if s["date"].startswith(y)]
                computed[f"state_coverage_{y}"] = (
                    bool(ds) and sum(d["available"] for d in ds) / len(ds) >= 0.95
                )
            if computed != expected:
                raise ValueError("independent screen mismatch")
        if r["screen_survived"][identity] != all(all(v.values()) for v in costs.values()):
            raise ValueError("survivor mismatch")
    first = read(output / "first_read_reservations.json")
    if (
        first != {"trials": spec["plans"], "spec_sha256": sha256_json(spec)}
        or r["raw_global_trial_lower_bound"] != 3600
        or r["completed_trials"] != 44
        or r["validated_alpha"]
    ):
        raise ValueError("reservation/debt/certification mismatch")
    summary = {
        "version": r["version"],
        "rows": rows,
        "checks": r["checks"],
        "screen_survived": r["screen_survived"],
        "source_result_sha256": file_sha(output / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "raw_trial_lower_bound": 3600,
        "new_trials": 44,
        "validated_alpha": False,
        "statistics": r["statistics"],
        "maximum_balance_residual_cny": balance,
        "independent_audit_pass": True,
        "states": len(states),
        "proxy_components": components,
        "proxy_labels": len(labels),
        "target_sets": len(seen),
        "models": 4,
        "raw_account_checks": market_evidence,
        "coverage": {
            y: sum(s["available"] for s in states if s["date"].startswith(y))
            / sum(s["date"].startswith(y) for s in states)
            for y in ("2023", "2024")
        },
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
    print(json.dumps({"independent_audit": "PASS", "accounts": 44, "native_fits": 72}), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
