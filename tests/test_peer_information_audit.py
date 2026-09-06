import copy
import json
from dataclasses import asdict, replace
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
from test_peer_information import make_registry, synthetic_days

from stephen_quant.discovery.peer_information import fit_graph, plans, prepared_signals, targets_for


@pytest.fixture
def audit_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import audit_peer_information

    return audit_peer_information


def test_independent_raw_sql_price_flow_and_gap(audit_module):
    rows = [
        {
            "trade_date": str(date(2022, 1, 1) + timedelta(days=i)),
            "instrument": "a",
            "name": "firm",
            "open": 10 * 1.01**i,
            "close": 10 * 1.01**i,
            "adjustment_factor": 1.0,
            "amount": 20_000.0,
            "available_at": str(date(2022, 1, 1) + timedelta(days=i)) + "T15:00:00+08:00",
        }
        for i in range(70)
    ]
    flow = [
        {
            "trade_date": r["trade_date"],
            "instrument": "a",
            "net_inflow_amount": 2e6,
            "available_at": r["available_at"],
        }
        for i, r in enumerate(rows)
        if i != 40
    ]
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE daily_source AS SELECT (value->>'trade_date')::DATE trade_date,"
            "value->>'instrument' instrument,value->>'name' AS name,(value->>'open')::DOUBLE open,"
            "(value->>'close')::DOUBLE AS close,(value->>'adjustment_factor')::DOUBLE adjustment_factor,"
            "(value->>'amount')::DOUBLE amount,(value->>'available_at')::TIMESTAMPTZ available_at FROM json_each(?)",
            [json.dumps(rows)],
        )
        con.execute(
            "CREATE TABLE flow_source AS SELECT (value->>'trade_date')::DATE trade_date,"
            "value->>'instrument' instrument,(value->>'net_inflow_amount')::DOUBLE net_inflow_amount,"
            "(value->>'available_at')::TIMESTAMPTZ available_at FROM json_each(?)",
            [json.dumps(flow)],
        )
        con.execute(
            "CREATE TABLE calendar AS SELECT row_number() OVER(ORDER BY trade_date)-1 idx,trade_date date FROM daily_source"
        )
        con.execute(
            (Path(__file__).resolve().parents[1] / "scripts/peer_source_audit.sql").read_text()
        )
        result = con.execute(
            "SELECT idx,return1,price,flow FROM reconstructed ORDER BY idx"
        ).fetchall()
        assert result[0][0] == 21  # ret20 establishes base eligibility; next adjacent return.
        for i, ret, price, f in result:
            assert ret == pytest.approx(0.01)
            ready = i >= 25 and not 40 <= i <= 44
            assert (price is not None) == ready
            if ready:
                assert price == pytest.approx(1.01**5 - 1)
                assert f == pytest.approx(0.1)
        con.execute(
            "CREATE TABLE evidence AS SELECT date,instrument,return1,volatility_20,liquidity,ret_20,price,flow FROM reconstructed"
        )
        assert audit_module.source_check(con) == len(result)
        con.execute("UPDATE evidence SET price=price+.01 WHERE price IS NOT NULL")
        with pytest.raises(ValueError, match="reconstruction"):
            audit_module.source_check(con)


@pytest.mark.parametrize("mutation", [None, "weight", "permutation", "cutoff", "count"])
def test_independent_graph_audit_catches_tampering(audit_module, mutation):
    days = synthetic_days()
    model = copy.deepcopy(fit_graph(days, 2023))
    if mutation == "weight":
        model["graph"]["n000"][0][1] *= 0.9
    elif mutation == "permutation":
        model["permutation"]["n000"] = "invalid"
    elif mutation == "cutoff":
        model["fit_cutoff"] = days[-1].date
    elif mutation == "count":
        model["training_counts"]["n000"] += 1
    rows = []
    for d in days:
        mean = sum(f["return1"] for f in d.features.values()) / len(d.features)
        rows.extend(
            {
                "date": d.date,
                "instrument": n,
                "residual": f["return1"] - mean,
                **{k: f[k] for k in ("volatility_20", "liquidity", "ret_20")},
            }
            for n, f in d.features.items()
        )
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE demeaned AS SELECT (value->>'date')::DATE date,value->>'instrument' instrument,"
            "(value->>'residual')::DOUBLE residual,(value->>'volatility_20')::DOUBLE volatility_20,"
            "(value->>'liquidity')::DOUBLE liquidity,(value->>'ret_20')::DOUBLE ret_20 FROM json_each(?)",
            [json.dumps(rows)],
        )
        if mutation:
            with pytest.raises(ValueError):
                audit_module.graph_check(con, {2023: model}, [d.date for d in days])
        else:
            report = audit_module.graph_check(con, {2023: model}, [d.date for d in days])
            assert report == {"selected_edges": 480, "top10_receivers_sampled": 20}


def test_independent_signal_and_all_target_clocks(audit_module, tmp_path):
    past = synthetic_days(size=144)
    future = tuple(
        replace(past[i], date=str(date(2023, 1, 2) + timedelta(days=i))) for i in range(50)
    )
    days = past + future
    model = fit_graph(days, 2023)
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    reg, tid, _ = make_registry(tmp_path)
    reg.record_model_fit(tid, "2023", model=model, artifact_path=path)
    cache, coverage = prepared_signals(reg, tid, days, {2023: model}, {2023: path})
    (tmp_path / "targets").mkdir()
    records = {}
    for p in plans():
        if p["identity"] == "anchor":
            continue
        records[p["key"]] = p
        target = targets_for(days, cache, p["group"], p["signal"], p["policy"])
        (tmp_path / "targets" / f"{p['identity']}-{p['policy']}.json").write_text(
            json.dumps([asdict(t) for t in target])
        )
    raw = [{"date": d.date, "instrument": n, **f} for d in days for n, f in d.features.items()]
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE calendar AS SELECT key::INTEGER idx,value::DATE date FROM json_each(?)",
            [json.dumps([d.date for d in days])],
        )
        con.execute(
            "CREATE TABLE reconstructed AS SELECT (value->>'date')::DATE date,value->>'instrument' instrument,"
            "(value->>'price')::DOUBLE price,(value->>'flow')::DOUBLE flow,"
            "(value->>'volatility_20')::DOUBLE volatility_20,(value->>'liquidity')::DOUBLE liquidity FROM json_each(?)",
            [json.dumps(raw)],
        )
        audit_module.score_table(con, {2023: model})
        assert con.execute("SELECT count(*) FROM score").fetchone()[0] == sum(
            x["common"] for x in coverage
        )
        assert (
            audit_module.target_check(con, tmp_path, {"records": records}, [d.date for d in days])
            == 24
        )
        selected = tmp_path / "targets/price-low-peer.json"
        content = json.loads(selected.read_text())
        content[1]["decided_at"] = content[1]["trade_date"] + "T23:59:59+08:00"
        selected.write_text(json.dumps(content))
        with pytest.raises(ValueError, match="target reconstruction"):
            audit_module.target_check(con, tmp_path, {"records": records}, [d.date for d in days])
