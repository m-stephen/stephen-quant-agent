"""Independent raw SQL / graph statistics / target schedule / cash and native audit."""

import argparse
import hashlib
import json
import sqlite3
from itertools import groupby
from pathlib import Path

import duckdb
from sparse_account_audit import audit_accounts, near

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


def source_check(con):
    fields = ("return1", "volatility_20", "liquidity", "ret_20", "price", "flow")
    terms = ["e.instrument IS NULL OR r.instrument IS NULL"]
    for f in fields:
        terms.extend(
            [f"(e.{f} IS NULL)!=(r.{f} IS NULL)", f"abs(e.{f}-r.{f})>1e-10+1e-8*abs(r.{f})"]
        )
    bad = con.execute(
        "SELECT count(*) FROM evidence e FULL JOIN reconstructed r USING(date,instrument) WHERE "
        + " OR ".join(terms)
    ).fetchone()[0]
    if bad:
        raise ValueError(f"source/support reconstruction mismatch: {bad}")
    if con.execute(
        "SELECT count(*) FROM (SELECT date,instrument FROM evidence GROUP BY ALL HAVING count(*)!=1)"
    ).fetchone()[0]:
        raise ValueError("duplicate source evidence")
    return con.execute("SELECT count(*) FROM evidence").fetchone()[0]


def graph_check(con, models, calendar):
    total, samples = 0, 0
    for year, m in models.items():
        prefix = [d for d in calendar if "2022-01-01" <= d < f"{year}-01-01"][:-5]
        if (
            m["fit_kind"] != "unsupervised"
            or m["fit_cutoff"] != prefix[-1]
            or "maximum_label_end" in m
        ):
            raise ValueError("graph cutoff/kind mismatch")
        con.execute(
            "CREATE OR REPLACE TABLE train AS SELECT * FROM demeaned WHERE date<=?", [prefix[-1]]
        )
        counts = dict(
            con.execute(
                "SELECT instrument,count(*) FROM train GROUP BY instrument HAVING count(*)>=120"
            ).fetchall()
        )
        if counts != m["training_counts"] or sorted(counts) != m["nodes"]:
            raise ValueError("training node support mismatch")
        observed = [
            str(r[0])
            for r in con.execute(
                "SELECT DISTINCT date FROM train WHERE instrument IN (SELECT instrument FROM train GROUP BY instrument HAVING count(*)>=120) ORDER BY date"
            ).fetchall()
        ]
        if (
            observed != m["training_observation_sessions"]
            or len(observed) != m["training_observation_dates"]
            or observed[-1] != m["maximum_observation_at"]
        ):
            raise ValueError("actual training sessions mismatch")
        # Check all chosen correlations with independent SQL aggregates; includes missingness.
        edges = [
            {"receiver": n, "peer": p, "weight": w, "overlap": m["overlaps"][n][i]}
            for n, es in m["graph"].items()
            for i, (p, w) in enumerate(es)
        ]
        con.execute(
            "CREATE OR REPLACE TABLE selected AS SELECT value->>'receiver' receiver,value->>'peer' peer,"
            "(value->>'weight')::DOUBLE weight,(value->>'overlap')::INTEGER overlap FROM json_each(?)",
            [json.dumps(edges)],
        )
        bad = con.execute("""WITH a AS (SELECT e.receiver,e.peer,e.weight,e.overlap,count(*) n,
          corr(x.residual,y.residual) r FROM selected e
          JOIN train x ON x.instrument=e.receiver JOIN train y ON y.instrument=e.peer AND y.date=x.date
          GROUP BY ALL) SELECT count(*) FROM a WHERE n!=overlap OR n<120 OR receiver=peer
          OR r<0.15-1e-12 OR NOT isfinite(r) OR abs(r-weight)>1e-10""").fetchone()[0]
        if bad:
            raise ValueError("selected correlation audit failed")
        total += len(edges)
        # Independently verify top10 selection for a fixed identity-hash sample, not return winners.
        chosen = sorted(
            m["nodes"], key=lambda n: hashlib.sha256(f"audit184:{n}".encode()).hexdigest()
        )[:20]
        con.execute(
            "CREATE OR REPLACE TABLE sample AS SELECT value->>'$' instrument FROM json_each(?)",
            [json.dumps(chosen)],
        )
        ranked = con.execute("""WITH a AS (SELECT x.instrument receiver,y.instrument peer,
          count(*) n,corr(x.residual,y.residual) r FROM train x JOIN train y ON x.date=y.date
          WHERE x.instrument IN (SELECT instrument FROM sample) AND x.instrument!=y.instrument
          AND y.instrument IN (SELECT instrument FROM train GROUP BY instrument HAVING count(*)>=120)
          GROUP BY ALL HAVING n>=120 AND isfinite(r) AND r>=0.15), b AS (
          SELECT *,row_number() OVER(PARTITION BY receiver ORDER BY r DESC,peer) k FROM a)
          SELECT receiver,peer FROM b WHERE k<=10 ORDER BY receiver,k""").fetchall()
        expected = {n: [] for n in chosen}
        for n, p in ranked:
            expected[n].append(p)
        for n, peers in expected.items():
            if (peers if len(peers) == 10 else []) != [p for p, _ in m["graph"].get(n, [])]:
                raise ValueError("sampled top10 graph selection mismatch")
        samples += len(chosen)
        perm = m["permutation"]
        if set(perm) != set(perm.values()) or set(perm) != set(m["nodes"]):
            raise ValueError("invalid node permutation")
        if {perm[n]: [[perm[p], w] for p, w in es] for n, es in m["graph"].items()} != m["shuffle"]:
            raise ValueError("shuffle topology mismatch")
        last = con.execute("""SELECT instrument,volatility_20,liquidity,ret_20 FROM train
          QUALIFY row_number() OVER(PARTITION BY instrument ORDER BY date DESC)=1""").fetchall()
        for n, vol, adv, ret in last:
            if n in counts:
                for k, v in zip(
                    ("volatility_20", "liquidity", "ret_20"), (vol, adv, ret), strict=True
                ):
                    near(v, m["training_risk"][n][k], "training risk state", 1e-10)
        # Risk-cell permutation membership and fixed hash mapping independently reconstructed.
        ordered = sorted(counts, key=lambda n: (m["training_risk"][n]["volatility_20"], n))
        for gi in range(3):
            group = [n for i, n in enumerate(ordered) if 3 * i // len(ordered) == gi]
            halves = (group[: (len(group) + 1) // 2], group[(len(group) + 1) // 2 :])
            for half in halves:
                ns = sorted(half, key=lambda n: (m["training_risk"][n]["liquidity"], n))
                for ai in range(2):
                    cell = [n for i, n in enumerate(ns) if 2 * i // len(ns) == ai]
                    old = sorted(cell)
                    new = sorted(
                        cell,
                        key=lambda n: (
                            hashlib.sha256(f"v11.17:184:{year}:{n}".encode()).hexdigest(),
                            n,
                        ),
                    )
                    if any(perm[a] != b for a, b in zip(old, new, strict=True)):
                        raise ValueError("fixed risk-cell permutation mismatch")
    return {"selected_edges": total, "top10_receivers_sampled": samples}


def score_table(con, models):
    edges = [
        {"year": y, "policy": p, "receiver": n, "peer": peer, "weight": weight}
        for y, m in models.items()
        for p, g in (("peer", "graph"), ("shuffle", "shuffle"))
        for n, es in m[g].items()
        for peer, weight in es
    ]
    con.execute(
        "CREATE TABLE edges AS SELECT (value->>'year')::INTEGER AS year,value->>'policy' AS policy,"
        "value->>'receiver' AS receiver,value->>'peer' AS peer,(value->>'weight')::DOUBLE AS weight FROM json_each(?)",
        [json.dumps(edges)],
    )
    con.execute("""CREATE TABLE signal_dates AS SELECT c.idx,c.date execution,p.date signal,
      year(c.date) AS year FROM calendar c JOIN calendar p ON p.idx=c.idx-1 WHERE year(c.date)>=2023""")
    con.execute("""CREATE TABLE own AS SELECT s.*,r.instrument,r.price,r.flow,r.volatility_20,r.liquidity
      FROM signal_dates s JOIN reconstructed r ON r.date=s.signal WHERE r.price IS NOT NULL AND r.flow IS NOT NULL""")
    con.execute("""CREATE TABLE score AS WITH a AS (
      SELECT o.idx,o.execution,o.signal,o.instrument,o.price,o.flow,o.volatility_20,o.liquidity,e.policy,
      sum(p.price*e.weight)/sum(e.weight)-o.price AS pg,
      sum(p.flow*e.weight)/sum(e.weight)-o.flow AS fg,count(*) n
      FROM own o JOIN edges e ON e.year=o.year AND e.receiver=o.instrument
      JOIN own p ON p.execution=o.execution AND p.instrument=e.peer
      GROUP BY o.idx,o.execution,o.signal,o.instrument,o.price,o.flow,o.volatility_20,o.liquidity,e.policy
      HAVING n>=8), b AS (
      SELECT idx,execution,signal,instrument,price,flow,volatility_20,liquidity,
      max(pg) FILTER(WHERE policy='peer') price_peer,max(pg) FILTER(WHERE policy='shuffle') price_shuffle,
      max(fg) FILTER(WHERE policy='peer') flow_peer,max(fg) FILTER(WHERE policy='shuffle') flow_shuffle
      FROM a GROUP BY ALL HAVING count(*)=2), c AS (
      SELECT *,row_number() OVER(PARTITION BY execution ORDER BY volatility_20,instrument)-1 vi,
      count(*) OVER(PARTITION BY execution) ns FROM b), d AS (
      SELECT *,floor(3.0*vi/ns)::INTEGER gi FROM c), e AS (
      SELECT *,row_number() OVER(PARTITION BY execution,gi ORDER BY volatility_20,instrument)-1 j,
      count(*) OVER(PARTITION BY execution,gi) gn FROM d), f AS (
      SELECT *,CASE WHEN j<ceil(gn/2.0) THEN 0 ELSE 1 END vh FROM e), g AS (
      SELECT *,row_number() OVER(PARTITION BY execution,gi,vh ORDER BY liquidity,instrument)-1 ai,
      count(*) OVER(PARTITION BY execution,gi,vh) hn FROM f)
      SELECT *,2*vh+floor(2.0*ai/hn)::INTEGER cell FROM g""")


def target_check(con, output, result, calendar):
    dates = [d for d in calendar if d >= "2023-01-01"]
    all_keys = sorted(
        {
            r["identity"] + "-" + r["policy"]
            for r in result["records"].values()
            if r["identity"] != "anchor"
        }
    )
    expected = {k: read(output / "targets" / f"{k}.json") for k in all_keys}
    holdings = {k: [(), (), (), ()] for k in all_keys}
    cursor = con.execute(
        "SELECT execution,instrument,gi,cell,price,flow,price_peer,price_shuffle,flow_peer,flow_shuffle FROM score ORDER BY execution,instrument"
    )

    def stream():
        for batch in iter(lambda: cursor.fetchmany(10000), []):
            yield from batch

    grouped = iter((str(dt), list(rows)) for dt, rows in groupby(stream(), key=lambda r: r[0]))
    current = next(grouped, None)
    for i, dt in enumerate(dates):
        rows = current[1] if current is not None and current[0] == dt else []
        if current is not None and current[0] == dt:
            current = next(grouped, None)
        refresh = i >= 1 and (i - 1) % 5 == 0
        phase = ((i - 1) % 20) // 5
        for key in all_keys:
            signal, group, policy = key.split("-")
            gi = ("low", "middle", "high").index(group)
            weights = {}
            if refresh:
                chosen = []
                for cell in range(4):
                    cell_rows = [r for r in rows if r[2] == gi and r[3] == cell]

                    def score(r, policy=policy, signal=signal):
                        if policy == "hash":
                            return int(
                                hashlib.sha256(f"v11.17:184:{r[1]}".encode()).hexdigest(), 16
                            )
                        if policy == "own":
                            return -r[4 if signal == "price" else 5]
                        return r[(6 if signal == "price" else 8) + (policy == "shuffle")]

                    ordered = [r[1] for r in sorted(cell_rows, key=lambda r: (-score(r), r[1]))]
                    retained = [n for n in ordered[:13] if n in holdings[key][phase]][:10]
                    chosen.extend(
                        retained + [n for n in ordered if n not in retained][: 10 - len(retained)]
                    )
                holdings[key][phase] = tuple(sorted(chosen))
                for sleeve in holdings[key]:
                    for n in sleeve:
                        weights[n] = weights.get(n, 0) + 0.00625
            target = {
                "trade_date": dt,
                "decided_at": calendar[calendar.index(dt) - 1] + "T23:59:59+08:00",
                "weights": weights,
                "rebalance": refresh,
                "forced_exits": [],
            }
            if target != expected[key][i]:
                raise ValueError(f"independent target reconstruction failed: {key} {dt}")
    return len(all_keys)


def audit(output, inputs):
    output, inputs = Path(output).resolve(), Path(inputs).resolve()
    r = read(output / "RESULT.json")
    spec = r["spec"]
    protected = [Path(p) for p in spec["protected_files"]]
    if protected_digest(protected)[0] != spec["protected_before"]:
        raise ValueError("protected evidence changed")
    for p, sha in spec["protected_files"].items():
        if file_sha(Path(p)) != sha:
            raise ValueError("source hash changed")
    models = {y: read(output / f"models/{y}.json") for y in (2023, 2024)}
    for y in models:
        if file_sha(output / f"models/{y}.json") != r["models_sha256"][str(y)]:
            raise ValueError("model bytes changed")
    calendar = read(output / "calendar.json")
    con = duckdb.connect(
        config={"threads": 4, "memory_limit": "4GB", "temp_directory": str(output / "audit-temp")}
    )
    try:
        for name, path in (
            ("daily_source", inputs / "daily.parquet"),
            ("flow_source", inputs / "fund_flow.parquet"),
        ):
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet({quote(path)})")
        con.execute(
            "CREATE TABLE calendar AS SELECT (key::INTEGER) idx,value::DATE date FROM json_each(?)",
            [json.dumps(calendar)],
        )
        con.execute(
            f"CREATE VIEW evidence AS SELECT * FROM read_csv_auto({quote(output / 'peer_inputs.csv.gz')},sample_size=-1)"
        )
        query = Path("scripts/peer_source_audit.sql").read_text(encoding="utf-8")
        con.execute(query)
        input_rows = source_check(con)
        print(json.dumps({"source_audit": input_rows}), flush=True)
        graphs = graph_check(con, models, calendar)
        print(json.dumps({"graph_audit": graphs}), flush=True)
        score_table(con, models)
        diagnostics = read(output / "coverage.json")
        ref_coverage = {}
        for dt, eligible, common in con.execute(
            "SELECT d.execution,(SELECT count(*) FROM own o WHERE o.execution=d.execution),(SELECT count(*) FROM score s WHERE s.execution=d.execution) FROM signal_dates d ORDER BY execution"
        ).fetchall():
            ref_coverage[str(dt)] = (eligible, common)
        sizes = {
            (str(dt), ("low", "middle", "high")[g]): n
            for dt, g, n in con.execute(
                "SELECT execution,gi,count(*) FROM score GROUP BY ALL"
            ).fetchall()
        }
        for d in diagnostics:
            a, b = ref_coverage[d["date"]]
            if (a, b) != (d["eligible"], d["common"]):
                raise ValueError("coverage mismatch")
            near(b / a if a else 0, d["ratio"], "coverage ratio", 1e-12)
            if any(d[g] != sizes.get((d["date"], g), 0) for g in ("low", "middle", "high")):
                raise ValueError("stratum coverage mismatch")
        targets = target_check(con, output, r, calendar)
        print(json.dumps({"target_audit": targets}), flush=True)
    finally:
        con.close()
    rows, balance = audit_accounts(output, r)
    with sqlite3.connect(
        f"file:{(output / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        native = db.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if (
            len(native) != 50
            or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 96
        ):
            raise ValueError("native trials/fits incomplete")
        for tid, hp, rr, ss, code in native:
            p, stages = json.loads(hp), json.loads(ss)
            if (
                p not in spec["plans"]
                or json.loads(rr) != r["records"][p["key"]]
                or code != spec["runtime_code_sha256"]
            ):
                raise ValueError("native result mismatch")
            fits = db.execute(
                "SELECT evidence_json,evidence_sha256 FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                (tid,),
            ).fetchall()
            if len(stages) != (0 if p["identity"] == "anchor" else 2) or len(fits) != len(stages):
                raise ValueError("native stages mismatch")
            payload = []
            for stage, (raw, sha) in zip(stages, fits, strict=True):
                f = json.loads(raw)
                year = int(stage["stage_id"])
                if (
                    sha256_json(f) != sha
                    or f["stage"] != stage
                    or stage["fit_kind"] != "unsupervised"
                    or f["artifact_sha256"] != r["models_sha256"][str(year)]
                    or f["model_content_sha256"] != sha256_json(models[year])
                    or f["training_observation_sessions"]
                    != models[year]["training_observation_sessions"]
                    or f["training_end"] != models[year]["fit_cutoff"]
                    or not f["training_end"] < stage["prediction_start"]
                ):
                    raise ValueError("native fitted model mismatch")
                payload.append(f)
            if sha256_json(payload) != r["records"][p["key"]]["fit_lineage_sha256"]:
                raise ValueError("native lineage hash mismatch")
    for identity, costs in r["checks"].items():
        for cost, expected in costs.items():
            c = r["records"][f"{identity}-peer-{cost}"]
            controls = [
                r["records"][f"{identity}-{p}-{cost}"] for p in ("own", "shuffle", "hash")
            ] + [r["records"][f"anchor-lowvol-{cost}"]]
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
                ds = [d for d in diagnostics if d["date"].startswith(y)]
                computed[f"coverage_{y}"] = (
                    bool(ds) and sum(d["ratio"] for d in ds) / len(ds) >= 0.7
                )
                computed[f"stratum_size_{y}"] = (
                    bool(ds) and sum(d[c["group"]] >= 40 for d in ds) / len(ds) >= 0.95
                )
            if computed != expected:
                raise ValueError("independent screen mismatch")
        if r["screen_survived"][identity] != all(all(x.values()) for x in costs.values()):
            raise ValueError("survivor mismatch")
    first = read(output / "first_read_reservations.json")
    if first["trials"] != spec["plans"] or first["spec_sha256"] != sha256_json(spec):
        raise ValueError("first-read reservation mismatch")
    if (
        r["raw_global_trial_lower_bound"] != 3556
        or r["completed_trials"] != 50
        or r["validated_alpha"]
    ):
        raise ValueError("debt/certification mismatch")
    summary = {
        "version": r["version"],
        "rows": rows,
        "checks": r["checks"],
        "screen_survived": r["screen_survived"],
        "source_result_sha256": file_sha(output / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "raw_trial_lower_bound": 3556,
        "new_trials": 50,
        "validated_alpha": False,
        "statistics": r["statistics"],
        "restricted_rows_read": 0,
        "maximum_balance_residual_cny": balance,
        "independent_audit_pass": True,
        "input_rows": input_rows,
        "graph_checks": graphs,
        "target_sets": targets,
        "coverage": {
            y: {
                "mean_common_ratio": sum(d["ratio"] for d in diagnostics if d["date"].startswith(y))
                / sum(d["date"].startswith(y) for d in diagnostics)
            }
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
    write_json(Path("docs/V11_17_RESULT.summary.json"), summary)
    print(json.dumps({"independent_audit": True, "survivors": r["screen_survived"]}), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
