import copy
import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import pytest
from test_conditional_risk import fixture_targets, labels

from stephen_quant.discovery.conditional_risk import (
    fit_model,
    market_states,
    overlay_targets,
    proxy_labels,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha, load_frozen_days


@pytest.fixture
def auditor(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import audit_conditional_risk

    return audit_conditional_risk


def test_independent_raw_source_states_labels_and_missing_components(tmp_path, auditor):
    from run_sparse_events import Evidence

    folder = tmp_path / "inputs"
    folder.mkdir()
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE daily AS SELECT DATE '2021-12-01'+i::INTEGER trade_date,"
            "'6'||lpad(j::VARCHAR,5,'0')||'.SH' instrument,'example' AS name,"
            "10+i*.01+sin(i*.13+j)*.05 AS open,10+i*.01+cos(i*.13+j)*.05 AS close,"
            "20000.0 amount,1000.0 volume,1.0 adjustment_factor,"
            "(DATE '2021-12-01'+i::INTEGER)::TIMESTAMPTZ available_at "
            "FROM range(280) x(i),range(205) y(j)"
        )
        con.execute(
            "DELETE FROM daily WHERE instrument='600001.SH' AND trade_date IN(DATE '2022-02-05',DATE '2022-02-10')"
        )
        con.execute(
            "UPDATE daily SET available_at=available_at+INTERVAL 2 DAY WHERE instrument='600002.SH' AND trade_date=DATE '2022-02-09'"
        )
        sources = []
        queries = {
            "daily": "SELECT * FROM daily",
            "minute": "SELECT trade_date,instrument,available_at,.01 late_30_return,.02 realized_volatility,.01 amihud_intraday FROM daily WHERE false",
            "fund_flow": "SELECT trade_date,instrument,available_at,1000.0 net_inflow_amount FROM daily WHERE false",
            "chip": "SELECT trade_date,instrument,available_at,8.0 chip_cost_15,12.0 chip_cost_85,10.0 chip_weighted_cost FROM daily WHERE false",
            "auction": "SELECT trade_date,instrument,available_at,.01 auction_return FROM daily WHERE false",
        }
        for name, q in queries.items():
            p = folder / f"{name}.parquet"
            con.execute(f"COPY ({q}) TO {auditor.quote(p)} (FORMAT PARQUET)")
            sources.append({"source": name, "file": p.name, "sha256": file_sha(p)})
        (folder / "manifest.json").write_text(
            json.dumps({"sources": sources, "snapshot_sha256": sha256_json(sources)})
        )
        days, _ = load_frozen_days(folder)
        states = market_states(days)
        with Evidence(tmp_path / "components.csv.gz") as evidence:
            actual = proxy_labels(days, states, evidence)
        con.execute("CREATE VIEW daily_source AS SELECT * FROM daily")
        con.execute(
            "CREATE TABLE calendar AS SELECT key::INTEGER idx,value::DATE date FROM json_each(?)",
            [json.dumps([d.date for d in days])],
        )
        con.execute(
            (
                Path(__file__).resolve().parents[1] / "scripts/conditional_risk_source_audit.sql"
            ).read_text()
        )
        ref_states, ref_labels = auditor.source_references(con)
        auditor.compare(states, ref_states, "states")
        auditor.compare(actual, ref_labels, "labels")
        assert auditor.components_check(con, tmp_path / "components.csv.gz") == len(actual) * 200
        m = fit_model(actual, [d.date for d in days], 2023)
        r = auditor.fit_reference(ref_labels, [d.date for d in days], 2023, False)
        r["training_rows_sha256"] = m["training_rows_sha256"]
        auditor.compare(m, r, "full source to fitted model")


@pytest.mark.parametrize("shuffled", [False, True])
def test_independent_normal_equations_and_calibration(auditor, shuffled):
    rows, calendar = labels()
    expected = auditor.fit_reference(rows, calendar, 2023, shuffled)
    actual = fit_model(rows, calendar, 2023, shuffled)
    auditor.compare(actual, expected, "model")
    actual["beta_return"][0] += 0.1
    with pytest.raises(ValueError):
        auditor.compare(actual, expected, "tamper")


@pytest.mark.parametrize("policy", ["model", "fixed", "lag20", "shuffle"])
def test_independent_target_calendar_cash_and_forced_exit(auditor, policy):
    base, p = fixture_targets()
    targets, detail = overlay_targets(base, p, "mean", policy)
    expected, ed = auditor.target_reference([asdict(t) for t in base], p, "mean", policy)
    # JSON array normalization is explicit; the original tuple is never edited.
    auditor.compare(
        json.loads(json.dumps([asdict(t) for t in targets])),
        json.loads(json.dumps(expected)),
        "targets",
    )
    auditor.compare(detail, ed, "diagnostics")
    changed = copy.deepcopy(detail)
    changed[21]["allocation"] += 0.01
    with pytest.raises(ValueError):
        auditor.compare(changed, ed, "allocation tamper")


@pytest.mark.parametrize("fault", [None, "price", "cap"])
def test_raw_account_prices_and_caps(auditor, tmp_path, fault):
    folder = tmp_path / "accounts"
    folder.mkdir()
    row = {
        "date": "2022-01-02",
        "orders": [{"instrument": "x", "capacity_notional": 1e6}],
        "positions": [{"instrument": "x", "mark_price": 10.0, "source": "current_close"}],
    }
    if fault == "price":
        row["positions"][0]["mark_price"] += 1
    if fault == "cap":
        row["orders"][0]["capacity_notional"] += 1
    (folder / "fixture.jsonl").write_text(json.dumps(row) + "\n")
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE daily_source AS SELECT DATE '2022-01-01'+i::INTEGER trade_date,"
            "'x' instrument,10.0 AS open,10.0 AS close,1.0 adjustment_factor,20000.0 amount FROM range(2) t(i)"
        )
        con.execute(
            "CREATE TABLE valid_bars AS SELECT trade_date AS date,instrument,close*adjustment_factor AS cp FROM daily_source"
        )
        if fault:
            with pytest.raises(ValueError):
                auditor.market_account_check(con, tmp_path)
        else:
            assert auditor.market_account_check(con, tmp_path) == {
                "capacity_mismatches": 0,
                "current_price_mismatches": 0,
            }
