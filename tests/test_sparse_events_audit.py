import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path

import duckdb
import pytest
from test_sparse_events import event, panel

from stephen_quant.discovery.sparse_events import catalog, risk_cells, schedules


def module():
    path = Path(__file__).resolve().parents[1] / "scripts/audit_sparse_events.py"
    spec = importlib.util.spec_from_file_location("sparse_audit_fixture", path)
    result = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(result)
    finally:
        sys.path.pop(0)
    return result


@pytest.mark.parametrize("ast", catalog())
def test_independent_sql_edges_and_reference_schedules(ast):
    days = panel(85, 120)
    for i in (5, 9, 28, 47, 60):
        event(days, i, ("S0000", "S0001"), ast["lag"])
        if ast["start"] == "negative_price_innovation":
            for n in ("S0000", "S0001"):
                days[i - ast["lag"]].features[n]["price_z"] = -3
        for j in range(2, 10):
            days[i].features[f"S{j:04d}"]["price_z"] = 0.2
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE support(index INTEGER,date VARCHAR,instrument VARCHAR,flow DOUBLE,flow_z DOUBLE,price_z DOUBLE,cell VARCHAR)"
    )
    rows = []
    for i, d in enumerate(days):
        cells = risk_cells(d.features)
        rows.extend(
            (i, d.date, n, f["flow"], f["flow_z"], f["price_z"], cells[n])
            for n, f in d.features.items()
        )
    columns = ("index", "date", "instrument", "flow", "flow_z", "price_z", "cell")
    con.execute(
        "INSERT INTO support SELECT (value->>'index')::INTEGER,value->>'date',"
        "value->>'instrument',(value->>'flow')::DOUBLE,(value->>'flow_z')::DOUBLE,"
        "(value->>'price_z')::DOUBLE,value->>'cell' FROM json_each(?)",
        [json.dumps([dict(zip(columns, row)) for row in rows])],
    )
    actual_log = []
    targets, entries, counts = schedules(days, ast, actual_log.append)
    ref_t, ref_e, ref_log, ref_counts = module().reference_schedule(
        con, ast, [d.date for d in days]
    )
    assert entries == ref_e and counts == ref_counts and actual_log == ref_log
    assert {
        p: json.loads(json.dumps([asdict(t) for t in ts])) for p, ts in targets.items()
    } == ref_t
    con.close()


def test_raw_source_sql_executes_and_detects_missing_or_tampered_evidence():
    con = duckdb.connect()
    con.execute("""CREATE TABLE daily_source AS SELECT DATE '2022-01-01'+i::INTEGER AS trade_date,
      'S0000' AS instrument,'firm' AS name,10+sin(i)*.1+i*.001 AS open,
      10+sin(i)*.1+i*.001 AS close,100000.0+i AS amount,1000 AS volume,
      1.0 AS adjustment_factor,
      (DATE '2022-01-01'+i::INTEGER)::TIMESTAMP AT TIME ZONE 'Asia/Shanghai' AS available_at
      FROM range(95) AS x(i)""")
    con.execute("""CREATE TABLE flow_source AS SELECT trade_date,instrument,available_at,
      sin(date_diff('day',DATE '2022-01-01',trade_date))*1000000 AS net_inflow_amount FROM daily_source""")
    con.execute(
        "CREATE TABLE calendar AS SELECT trade_date AS date,row_number() OVER(ORDER BY trade_date)-1 AS idx FROM daily_source"
    )
    query = (Path(__file__).resolve().parents[1] / "scripts/sparse_innovation_audit.sql").read_text(
        encoding="utf-8"
    )
    con.execute(query)
    assert con.execute("SELECT count(*) FROM support").fetchone()[0] > 30
    con.execute("CREATE TABLE evidence AS SELECT * FROM reconstructed")
    audit = module()
    total = audit.verify_normalization(con)
    assert total > 60
    con.execute("UPDATE evidence SET flow_z=flow_z+1 WHERE index=60")
    with pytest.raises(ValueError, match="normalization"):
        audit.verify_normalization(con)
    con.execute("DELETE FROM evidence WHERE index=60")
    with pytest.raises(ValueError, match="normalization"):
        audit.verify_normalization(con)
    con.close()
