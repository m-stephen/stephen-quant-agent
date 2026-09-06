"""Independent raw SQL, event-clock, target, cash-account and native-ledger checks."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import sqlite3
from itertools import groupby
from pathlib import Path

import duckdb
from sparse_account_audit import audit_accounts

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


def verify_normalization(con):
    fields = (
        "close",
        "previous_close",
        "price_return",
        "flow",
        "ret_20",
        "volatility_20",
        "liquidity",
        "flow_z",
        "price_z",
    )
    conditions = ["e.index IS DISTINCT FROM r.index"]
    for f in fields:
        conditions.append(f"(e.{f} IS NULL)!=(r.{f} IS NULL)")
        conditions.append(f"abs(e.{f}-r.{f})>1e-10+1e-8*abs(r.{f})")
    count = con.execute(
        "SELECT count(*) FROM evidence e FULL JOIN reconstructed r USING(date,instrument) WHERE "
        + " OR ".join(conditions)
    ).fetchone()[0]
    if count:
        raise ValueError(f"raw support or rolling normalization mismatch: {count}")
    duplicate = con.execute(
        "SELECT count(*) FROM (SELECT date,instrument FROM evidence GROUP BY ALL HAVING count(*)!=1)"
    ).fetchone()[0]
    if duplicate:
        raise ValueError("duplicate innovation evidence")
    return con.execute("SELECT count(*) FROM evidence").fetchone()[0]


def reference_schedule(con, ast, calendar):
    """SQL determines all first-hit edges; separate clock reconstruction follows.

    Do not call any production selection/standardization/cell helper. Empty days
    are retained through the independently reconstructed global calendar.
    """
    if (
        ast["start"] not in ("positive_flow_innovation", "negative_price_innovation")
        or ast["confirm"] not in ("quiet_positive_flow", "recovery_positive_flow")
        or ast["lag"] not in (1, 3)
    ):
        raise ValueError("unknown registered AST")
    start = (
        "p.flow_z>=2 AND p.flow>0"
        if ast["start"] == "positive_flow_innovation"
        else "p.price_z<=-2"
    )
    confirm = (
        "abs(s.price_z)<=0.5 AND s.flow>0"
        if ast["confirm"] == "quiet_positive_flow"
        else "s.price_z BETWEEN 0 AND 1 AND s.flow>0"
    )
    con.execute("DROP TABLE IF EXISTS hits")
    con.execute(f"""CREATE TABLE hits AS WITH x AS (
      SELECT s.*,coalesce(({start}) AND ({confirm}),false) AS hit,
        ({confirm}) AS confirms
      FROM support s LEFT JOIN support p ON s.instrument=p.instrument AND p.index=s.index-{ast["lag"]}
    ), y AS (SELECT *,lag(index) OVER w AS pi,lag(hit) OVER w AS ph FROM x
      WINDOW w AS(PARTITION BY instrument ORDER BY index))
    SELECT *,hit AND NOT coalesce(pi=index-1 AND ph,false) AS rising FROM y""")
    policies = ("event", "risk_hash", "confirm_only")
    active = {p: [] for p in policies}
    used = {p: {} for p in policies}
    reconstructed, entries, trigger_rows, counts = {p: [] for p in policies}, [], [], []
    identity = ast["identity"]

    cursor = con.execute(
        "SELECT index,instrument,cell,rising,confirms FROM hits "
        "WHERE date>='2023-01-01' ORDER BY index,instrument"
    )

    def stream():
        for batch in iter(lambda: cursor.fetchmany(10000), []):
            yield from batch

    grouped = iter(
        (idx, [row[1:] for row in group])
        for idx, group in groupby(stream(), key=lambda row: row[0])
    )
    current = next(grouped, None)

    def key(p, n):
        return hashlib.sha256(f"v11.16:184:{identity}:{p}:{n}".encode()).hexdigest(), n

    for i, dt in enumerate(calendar[:-1]):
        if dt < "2023-01-01":
            continue
        entry, expiry, trade = i + 1, i + 21, calendar[i + 1]
        for p in policies:
            active[p] = [r for r in active[p] if r[1] > entry]
        while current is not None and current[0] < i:
            current = next(grouped, None)
        data = current[1] if current is not None and current[0] == i else []
        info = {n: (cell, rising, confirms) for n, cell, rising, confirms in data}
        events = [n for n, _, rising, _ in data if rising and i - used["event"].get(n, -40) >= 40]
        used["event"].update({n: i for n in events})
        held = {n for n, _ in active["event"]}
        selected = sorted(set(events) - held, key=lambda n: key("event", n))[: 40 - len(held)]
        trigger_rows.extend(
            {
                "identity": identity,
                "index": i,
                "date": dt,
                "instrument": n,
                "cell": info[n][0],
                "admitted": n in selected,
            }
            for n in sorted(events)
        )
        matched = {p: 0 for p in policies[1:]}
        for n in selected:
            row = {
                "identity": identity,
                "signal_index": i,
                "signal_date": dt,
                "entry_index": entry,
                "entry_date": trade,
                "expiry_index": expiry,
                "event": n,
                "cell": info[n][0],
            }
            active["event"].append((n, expiry))
            for p in policies[1:]:
                held = {name for name, _ in active[p]}
                eligible = [
                    m
                    for m, cell, _, confirms in data
                    if cell == row["cell"]
                    and m not in events
                    and m not in held
                    and i - used[p].get(m, -40) >= 40
                    and (p != "confirm_only" or confirms)
                ]
                chosen = sorted(eligible, key=lambda m: key(p, m))
                row[p] = chosen[0] if chosen else None
                if chosen:
                    active[p].append((chosen[0], expiry))
                    used[p][chosen[0]] = i
                    matched[p] += 1
            entries.append(row)
        counts.append(
            {
                "date": dt,
                "entry_date": trade,
                "year": trade[:4],
                "eligible": len(data),
                "triggers": len(events),
                "admissions": len(selected),
                **matched,
                "desired_names": {p: len(active[p]) for p in policies},
            }
        )
        for p in policies:
            reconstructed[p].append(
                {
                    "trade_date": trade,
                    "decided_at": dt + "T23:59:59+08:00",
                    "weights": {n: 0.025 for n, _ in active[p]},
                    "rebalance": True,
                    "forced_exits": [],
                }
            )
    for p in policies:
        by_date = {t["trade_date"]: t for t in reconstructed[p]}
        reconstructed[p] = [
            by_date.get(
                dt,
                {
                    "trade_date": dt,
                    "decided_at": dt + "T08:00:00+08:00",
                    "weights": {},
                    "rebalance": True,
                    "forced_exits": [],
                },
            )
            for dt in calendar
            if dt >= "2023-01-01"
        ]
    return reconstructed, entries, trigger_rows, counts


def audit(output, inputs):
    output, inputs = Path(output), Path(inputs)
    r = read(output / "RESULT.json")
    spec = r["spec"]
    protected = spec["protected_files"]
    if protected_digest([Path(p) for p in protected])[0] != spec["protected_before"] or any(
        file_sha(p) != digest for p, digest in protected.items()
    ):
        raise ValueError("protected source changed")
    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute(f"SET temp_directory={quote(output / 'audit_tmp')}")
    con.execute(
        f"CREATE TABLE evidence AS SELECT * FROM read_csv({quote(output / 'innovation_inputs.csv.gz')},header=true,sample_size=-1)"
    )
    for alias, file in (("daily_source", "daily"), ("flow_source", "fund_flow")):
        con.execute(
            f"CREATE VIEW {alias} AS SELECT * FROM read_parquet({quote(inputs / (file + '.parquet'))})"
        )
    con.execute("""CREATE TABLE calendar AS SELECT trade_date AS date,
      row_number() OVER(ORDER BY trade_date)-1 AS idx FROM (SELECT DISTINCT trade_date FROM daily_source
      WHERE trade_date>=DATE '2022-01-01' AND trade_date<DATE '2025-01-01'
      AND open>0 AND close>0 AND adjustment_factor>0 AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor))""")
    calendar = [
        x[0].isoformat() for x in con.execute("SELECT date FROM calendar ORDER BY idx").fetchall()
    ]
    if calendar != read(output / "calendar.json"):
        raise ValueError("global calendar mismatch")
    query = Path("scripts/sparse_innovation_audit.sql").read_text(encoding="utf-8")
    con.execute(query)
    count = verify_normalization(con)
    if count != r["innovation_rows"]:
        raise ValueError("evidence count mismatch")
    print(json.dumps({"audit": "raw_support_and_previous20", "rows": count}), flush=True)
    all_counts = read(output / "selection_diagnostics.json")
    for ast in spec["catalog"]:
        identity = ast["identity"]
        targets, admissions, triggers, counts = reference_schedule(con, ast, calendar)
        if (
            admissions != read(output / "admissions" / f"{identity}.json")
            or counts != all_counts[identity]
        ):
            raise ValueError("independent event/control clock mismatch")
        with gzip.open(output / "triggers" / f"{identity}.csv.gz", "rt", encoding="utf-8") as f:
            actual = list(csv.DictReader(f))
        for row in actual:
            row["index"], row["admitted"] = int(row["index"]), row["admitted"] == "True"
        if actual != triggers:
            raise ValueError("all qualifying triggers not bound")
        for policy, rows in targets.items():
            if rows != read(output / "targets" / f"{identity}-{policy}.json"):
                raise ValueError("independent target mismatch")
        print(json.dumps({"audit": "event_schedule", "identity": identity}), flush=True)
    con.close()
    rows, max_balance = audit_accounts(output, r)
    by_key = {row["account_key"]: row for row in rows}
    for identity, costs in r["checks"].items():
        annual = {
            y: {
                k: sum(d[k] for d in all_counts[identity] if d["year"] == y)
                for k in ("admissions", "risk_hash", "confirm_only")
            }
            for y in ("2023", "2024")
        }
        for cost, expected in costs.items():
            a = by_key[f"{identity}-event-{cost}"]
            cs = [by_key[f"{identity}-{p}-{cost}"] for p in ("risk_hash", "confirm_only")] + [
                by_key[f"anchor-lowvol-{cost}"]
            ]
            computed = {
                "accounts": True,
                "both_years_positive": a["return2023"] > 0 and a["return2024"] > 0,
                "sharpe": a["sharpe"] >= 0.7,
                "drawdown": a["max_drawdown"] >= -0.25,
                "total_increment": all(a["net_return"] - c["net_return"] >= 0.03 for c in cs),
                "annual_increment": all(
                    a["return" + y] - c["return" + y] >= -0.05 for c in cs for y in annual
                ),
                "admissions": all(x["admissions"] >= 50 for x in annual.values()),
                "matching": all(
                    x["admissions"] > 0 and x[p] / x["admissions"] >= 0.98
                    for x in annual.values()
                    for p in ("risk_hash", "confirm_only")
                ),
            }
            if computed != expected:
                raise ValueError("independent screen mismatch")
        if r["screen_survived"][identity] != all(all(x.values()) for x in costs.values()):
            raise ValueError("survivor mismatch")
    with sqlite3.connect(
        f"file:{(output / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        native = db.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(native) != 50 or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("50 native NOFIT contracts required")
        seen = set()
        for plan_text, result_text, stages, runtime in native:
            plan = json.loads(plan_text)
            if (
                plan not in spec["plans"]
                or stages != "[]"
                or runtime != spec["runtime_code_sha256"]
                or json.loads(result_text) != r["records"][plan["key"]]
            ):
                raise ValueError("native result or lineage mismatch")
            seen.add(plan["key"])
        if seen != set(r["records"]):
            raise ValueError("native plan set mismatch")
    first = read(output / "first_read_reservations.json")
    if first["trials"] != spec["plans"] or first["spec_sha256"] != sha256_json(spec):
        raise ValueError("first-read reservation mismatch")
    if (
        r["raw_global_trial_lower_bound"] != 3506
        or r["completed_trials"] != 50
        or r["validated_alpha"]
    ):
        raise ValueError("debt/certification mismatch")
    if not all(math.isfinite(row["net_return"]) for row in rows):
        raise ValueError("nonfinite accounts")
    summary = {
        "version": r["version"],
        "rows": rows,
        "checks": r["checks"],
        "screen_survived": r["screen_survived"],
        "source_result_sha256": file_sha(output / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "raw_trial_lower_bound": 3506,
        "new_trials": 50,
        "validated_alpha": False,
        "statistics": r["statistics"],
        "restricted_rows_read": 0,
        "maximum_balance_residual_cny": max_balance,
        "independent_audit_pass": True,
        "admissions": {
            k: {
                y: {
                    f: sum(d[f] for d in ds if d["year"] == y)
                    for f in ("admissions", "risk_hash", "confirm_only")
                }
                for y in ("2023", "2024")
            }
            for k, ds in all_counts.items()
        },
    }
    write_json(
        output / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "summary": summary,
            "innovation_query": query,
            "evidence_hashes": {
                p.relative_to(output).as_posix(): file_sha(p)
                for p in output.rglob("*")
                if p.is_file()
            },
        },
    )
    write_json(Path("docs/V11_16_RESULT.summary.json"), summary)
    print(json.dumps({"independent_audit": True, "survivors": r["screen_survived"]}), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
