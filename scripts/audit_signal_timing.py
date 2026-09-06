"""Independent SQL from endpoint/weight evidence; no new candidate or source window."""

import argparse
import json
import math
import sqlite3
from pathlib import Path

import duckdb

from stephen_quant.discovery.signal_timing import READOUTS
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def quoted(path):
    return "'" + str(path).replace("'", "''") + "'"


def audit(output, inputs):
    output, inputs = Path(output), Path(inputs)
    r = read(output / "RESULT.json")
    if file_sha(output / "endpoints.csv.gz") != r["evidence_sha256"]:
        raise ValueError("endpoint hash mismatch")
    if file_sha(output / "date_responses.json") != r["daily_sha256"]:
        raise ValueError("date hash mismatch")
    protected = r["spec"]["protected_files"]
    if protected_digest([Path(p) for p in protected])[0] != r["spec"]["protected_before"] or any(
        file_sha(p) != digest for p, digest in protected.items()
    ):
        raise ValueError("protected source changed")
    con = duckdb.connect()
    con.execute("SET threads=4")
    con.execute("SET memory_limit='4GB'")
    con.execute(f"SET temp_directory={quoted(output / 'audit_tmp')}")
    con.execute(
        f"CREATE TABLE e AS SELECT * FROM read_csv({quoted(output / 'endpoints.csv.gz')},header=true)"
    )
    count = con.execute("SELECT count(*) FROM e").fetchone()[0]
    assert count == r["evidence_rows"]
    assert (
        con.execute(
            "SELECT count(*) FROM (SELECT date,instrument FROM e GROUP BY ALL HAVING count(*)!=1)"
        ).fetchone()[0]
        == 0
    )
    assert (
        con.execute("SELECT min(date),max(date),max(exit20_date) FROM e").fetchone()[2].isoformat()
        < "2025-01-01"
    )
    # Independently reconstruct stratum and four risk/ADV cells from recorded asof fields.
    cell_sql = """WITH a AS (SELECT *,row_number() OVER(PARTITION BY date ORDER BY volatility_20,instrument)-1 AS vi,
      count(*) OVER(PARTITION BY date) AS n FROM e),
    b AS (SELECT *,floor(3.0*vi/n)::INTEGER AS gi FROM a),
    c AS (SELECT *,row_number() OVER(PARTITION BY date,gi ORDER BY volatility_20,instrument)-1 AS j,
      count(*) OVER(PARTITION BY date,gi) AS gn FROM b),
    d AS (SELECT *,CASE WHEN j<ceil(gn/2.0) THEN 0 ELSE 1 END AS vh FROM c),
    f AS (SELECT *,row_number() OVER(PARTITION BY date,gi,vh ORDER BY liquidity,instrument)-1 AS ai,
      count(*) OVER(PARTITION BY date,gi,vh) AS hn FROM d)
    SELECT count(*) FROM f WHERE "group"!=list_extract(['low','middle','high'],gi+1)
      OR cell != 2*vh+floor(2.0*ai/hn)::INTEGER"""
    assert con.execute(cell_sql).fetchone()[0] == 0
    print(json.dumps({"audit": "asof_partition", "rows": count}), flush=True)
    ranks = []
    for field in ("flow_consistency", "auction_tail_balance", "chip_path_efficiency", "ret_20"):
        ranks.append(
            f'(rank() OVER(PARTITION BY date,"group",cell ORDER BY {field})+'
            f'(count(*) OVER(PARTITION BY date,"group",cell,{field})-1)/2.0)/'
            '(count(*) OVER(PARTITION BY date,"group",cell)+1) AS r_' + field
        )
    con.execute("CREATE TABLE ranked AS SELECT *," + ",".join(ranks) + " FROM e")
    expressions = {
        "flow_price_absorption": "r_flow_consistency*(1-r_ret_20)",
        "quiet_accumulation": "r_flow_consistency*(1-r_chip_path_efficiency)",
        "auction_exhaustion": "(1-r_auction_tail_balance)*(1-r_ret_20)",
        "price_reversal": "1-r_ret_20",
        "hash": "sha256('v11.14:184:'||instrument)",
    }
    for p, expr in expressions.items():
        query = f"""SELECT count(*) FROM (SELECT *,row_number() OVER(
          PARTITION BY date,"group",cell ORDER BY {expr} DESC,instrument) AS sr FROM ranked)
          WHERE abs(w_{p}-(CASE WHEN sr<=10 THEN 0.025 ELSE 0 END))>1e-12"""
        assert con.execute(query).fetchone()[0] == 0, p
    assert (
        con.execute("""SELECT count(*) FROM (SELECT *,count(*) OVER(PARTITION BY date,"group",cell) AS cn
                          FROM e) WHERE abs(w_cell_equal_weight-0.25/cn)>1e-12""").fetchone()[0]
        == 0
    )
    con.execute("DROP TABLE ranked")
    print(json.dumps({"audit": "all_membership_weights"}), flush=True)
    # Verify every price endpoint against the already frozen raw daily extract.
    con.execute(
        f"CREATE VIEW raw AS SELECT *,open*adjustment_factor AS ao,close*adjustment_factor AS ac "
        f"FROM read_parquet({quoted(inputs / 'daily.parquet')}) WHERE open>0 AND close>0 "
        "AND adjustment_factor>0 AND isfinite(open) AND isfinite(close) AND isfinite(adjustment_factor)"
    )
    for tag in ("signal", "entry", "exit1", "exit5", "exit20"):
        bad = con.execute(f"""SELECT count(*) FROM e LEFT JOIN raw r ON
          e.instrument=r.instrument AND e.{tag}_date=r.trade_date WHERE
          (e.{tag}_open IS NULL)!=(r.ao IS NULL) OR (e.{tag}_close IS NULL)!=(r.ac IS NULL)
          OR abs(e.{tag}_open-r.ao)>1e-10 OR abs(e.{tag}_close-r.ac)>1e-10""").fetchone()[0]
        assert bad == 0, tag
    # Global-calendar maturity and endpoint spacing,not per-stock observed-row lag.
    con.execute(
        "CREATE TABLE cal AS SELECT trade_date,row_number() OVER(ORDER BY trade_date) AS i "
        "FROM (SELECT DISTINCT trade_date FROM raw WHERE trade_date>=DATE '2022-01-01')"
    )
    for tag, lag in (("entry", 1), ("exit1", 2), ("exit5", 6), ("exit20", 21)):
        assert (
            con.execute(f"""SELECT count(*) FROM e JOIN cal a ON e.date=a.trade_date
          LEFT JOIN cal b ON b.i=a.i+{lag} WHERE e.{tag}_date IS DISTINCT FROM b.trade_date""").fetchone()[
                0
            ]
            == 0
        )
    print(json.dumps({"audit": "all_price_endpoints_and_calendar"}), flush=True)
    weights = ",".join(f"('{p}',w_{p})" for p in READOUTS)
    pairs = (
        "('before_entry',signal_close,entry_open,NULL),('same_day',entry_open,entry_close,NULL),"
        + ",".join(f"('open_{h}',entry_open,exit{h}_open,exit{h}_sell)" for h in (1, 5, 20))
    )
    # Durable original aggregation SQL,including label construction and missing denominators.
    query = f"""WITH e AS (SELECT * FROM read_csv('artifacts/signal-timing/epoch-001/endpoints.csv.gz',header=true)),
    expanded AS (SELECT e.*,p.policy,p.w,l.label,l.start,l.finish,l.sell,
      (l.start>0 AND l.finish>0 AND isfinite(l.start) AND isfinite(l.finish)) AS valid,
      coalesce(entry_open>0 AND isfinite(entry_open) AND entry_buy=1,false) AS enterable
      FROM e CROSS JOIN LATERAL (VALUES {weights}) p(policy,w)
      CROSS JOIN LATERAL (VALUES {pairs}) l(label,start,finish,sell)),
    date_rows AS (SELECT date,year,"group",policy,label,sum(w) AS weight,
      sum(w*CASE WHEN valid THEN finish/start-1 ELSE 0 END) AS gross,
      sum(w*CASE WHEN valid THEN 1 ELSE 0 END) AS valid_weight,
      sum(w*CASE WHEN enterable THEN 1 ELSE 0 END) AS entry_weight,
      CASE WHEN label LIKE 'open_%' THEN sum(w*CASE WHEN NOT enterable THEN 0
        WHEN valid AND sell=1 THEN finish/start-1 ELSE -1 END) END AS stress
      FROM expanded GROUP BY date,year,"group",policy,label)
    SELECT * FROM date_rows ORDER BY date,"group",policy,label"""
    actual_query = query.replace(
        "read_csv('artifacts/signal-timing/epoch-001/endpoints.csv.gz',header=true)", "e"
    )
    # Avoid recursive CTE shadowing of physical e.
    actual_query = actual_query.replace("WITH e AS (SELECT * FROM e),", "WITH ")
    cursor = con.execute(actual_query)
    columns = [x[0] for x in cursor.description]
    sql_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    expected = {
        (x["date"], x["group"], x["policy"], x["label"]): x
        for x in read(output / "date_responses.json")
    }
    assert len(sql_rows) == len(expected) == r["signal_dates"] * 90
    maximum = 0
    for x in sql_rows:
        key = (x["date"].isoformat(), x["group"], x["policy"], x["label"])
        y = expected[key]
        assert str(x["year"]) == y["year"]
        for field in ("weight", "gross", "valid_weight", "entry_weight", "stress"):
            assert (x[field] is None) == (y[field] is None)
            if x[field] is not None:
                maximum = max(maximum, abs(x[field] - y[field]))
                assert math.isclose(x[field], y[field], rel_tol=1e-9, abs_tol=1e-11), (key, field)
    annual_sql = """SELECT "group",policy,label,year,count(*) AS dates,avg(weight) AS mean_weight,
      avg(gross) AS mean_gross,avg(valid_weight) AS valid_weight,avg(entry_weight) AS entry_weight,
      avg(stress) AS mean_stress,sum(gross)/nullif(sum(valid_weight),0) AS complete_price_mean
      FROM date_rows GROUP BY ALL ORDER BY "group",policy,label,year"""
    annual_query = actual_query.rsplit("SELECT * FROM date_rows", 1)[0] + annual_sql
    cur = con.execute(annual_query)
    cols = [x[0] for x in cur.description]
    annual = [dict(zip(cols, x)) for x in cur.fetchall()]
    expected_annual = {(x["group"], x["policy"], x["label"], x["year"]): x for x in r["summary"]}
    assert len(annual) == len(expected_annual) == 180
    for x in annual:
        x["year"] = str(x["year"])
        y = expected_annual[x["group"], x["policy"], x["label"], x["year"]]
        for k in x:
            if isinstance(x[k], (float, int)) and x[k] is not None:
                assert math.isclose(x[k], y[k], rel_tol=1e-9, abs_tol=1e-11), (x, k)
            else:
                assert x[k] == y[k]
    checks = {}
    for group in ("low", "middle", "high"):
        for policy in ("flow_price_absorption", "quiet_accumulation", "auction_exhaustion"):
            for label in ("open_1", "open_5", "open_20"):
                ok = True
                for year in ("2023", "2024"):
                    y = expected_annual[group, policy, label, year]
                    cs = [
                        expected_annual[group, p, label, year]
                        for p in ("hash", "price_reversal", "cell_equal_weight")
                    ]
                    ok &= (
                        y["mean_gross"] > 0.0164
                        and y["valid_weight"] >= 0.99
                        and y["entry_weight"] >= 0.98
                        and y["mean_stress"] > 0
                        and all(y["mean_gross"] - c["mean_gross"] >= 0.003 for c in cs)
                    )
                checks[f"{group}-{policy}-{label}"] = ok
    assert checks == r["strong_responses"]
    with sqlite3.connect(f"file:{output / 'registry.sqlite3'}?mode=ro", uri=True) as db:
        assert (
            db.execute("SELECT count(*) FROM trials WHERE result_json IS NOT NULL").fetchone()[0]
            == 90
        )
        assert db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 0
        assert (
            db.execute(
                "SELECT count(*) FROM trial_fit_contracts WHERE stages_json='[]'"
            ).fetchone()[0]
            == 90
        )
    con.close()
    write_json(
        output / "INDEPENDENT_AUDIT.json",
        dict(
            **{"pass": True},
            evidence_rows=count,
            date_rows=len(expected),
            annual_rows=len(annual),
            maximum_aggregate_difference=maximum,
            result_sha256=file_sha(output / "RESULT.json"),
            membership_checks="all asof group/cell/top10/hash/EW via independent SQL",
            endpoint_checks="all prices vs frozen daily and global calendar",
            native_no_fit_trials=90,
            query=query.rsplit("SELECT * FROM date_rows", 1)[0] + annual_sql,
            additional_trials=0,
            validated_alpha=False,
        ),
    )
    write_json(
        Path("docs/V11_15_RESULT.summary.json"),
        {
            "rows": annual,
            "strong_responses": checks,
            "raw_global_trial_lower_bound": 3456,
            "validated_alpha": False,
            "signal_dates": r["signal_dates"],
            "first_signal": r["first_signal"],
            "last_signal": r["last_signal"],
        },
    )
    print(
        json.dumps({"audit_pass": True, "max_difference": maximum, "strong_responses": checks}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    audit(args.output, args.inputs)
