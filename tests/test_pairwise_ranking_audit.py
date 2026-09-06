import copy
import json
from dataclasses import asdict, replace
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
from test_pairwise_ranking import days, labels, registry_trial

from stephen_quant.discovery.pairwise_ranking import (
    BASES,
    KINDS,
    fit_model,
    plans,
    prepare,
    targets_for,
    training_pairs,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha, load_frozen_days


@pytest.fixture
def auditor(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import audit_pairwise_ranking

    return audit_pairwise_ranking


@pytest.mark.parametrize("basis", BASES)
@pytest.mark.parametrize("kind", KINDS)
def test_independent_matrix_and_convex_stationarity(auditor, basis, kind):
    rows, calendar = labels()
    model = fit_model(rows, calendar, 2023, basis, kind)
    auditor.model_check(model, rows, calendar)
    model["weights"][0] += 0.01
    with pytest.raises(ValueError):
        auditor.model_check(model, rows, calendar)


@pytest.mark.parametrize("policy", ["full", "hash", "lowvol"])
def test_independent_targets_and_rank_ties(auditor, tmp_path, policy):
    source, _ = prepare(days(95))
    window = tuple(
        replace(d, date=str(date(2023, 1, 1) + timedelta(days=i)))
        for i, d in enumerate(source[-50:])
    )
    rows, calendar = labels()
    reg, tid = registry_trial(tmp_path, policy == "full")
    models, paths = {}, {}
    if policy == "full":
        for y in (2023, 2024):
            m = fit_model(rows, calendar, y, "quadratic", "full")
            path = tmp_path / f"model{y}.json"
            path.write_text(json.dumps(m))
            reg.record_model_fit(tid, str(y), model=m, artifact_path=path)
            models[y], paths[y] = m, path
    cache = {}
    targets, details = targets_for(reg, tid, window, policy, cache, models, paths)
    for d in window:
        if d.date in cache:
            auditor.compare(cache[d.date], auditor.ranks_reference(d.features), "ranks")
    expected, ed = auditor.target_reference([d.date for d in window], cache, policy, models)
    auditor.compare(json.loads(json.dumps([asdict(t) for t in targets])), expected, "targets")
    auditor.compare(details, ed, "selection")


def test_raw_source_paths_pair_selection_and_labels(auditor, tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    with duckdb.connect() as con:
        con.execute("""CREATE TABLE daily AS SELECT DATE '2021-12-01'+i::INTEGER trade_date,
            '6'||lpad(j::VARCHAR,5,'0')||'.SH' instrument,'example' AS name,
            10+i*.01+sin(i*.13+j)*.05 AS open,10+i*.01+cos(i*.13+j)*.05 AS close,
            20000.0+j*10 amount,1000.0 volume,1.0 adjustment_factor,
            (DATE '2021-12-01'+i::INTEGER)::TIMESTAMPTZ available_at FROM range(280) x(i),range(100) y(j)""")
        con.execute(
            "DELETE FROM daily WHERE instrument='600001.SH' AND trade_date IN(DATE '2022-02-05',DATE '2022-02-10')"
        )
        con.execute(
            "UPDATE daily SET available_at=available_at+INTERVAL 2 DAY WHERE instrument='600002.SH' AND trade_date=DATE '2022-02-09'"
        )
        queries = {
            "daily": "SELECT * FROM daily",
            "minute": "SELECT trade_date,instrument,available_at,.01 late_30_return,.02 realized_volatility,.01 amihud_intraday FROM daily WHERE false",
            "fund_flow": "SELECT trade_date,instrument,available_at,sin(epoch(trade_date)/86400)*1000 net_inflow_amount FROM daily",
            "chip": "SELECT trade_date,instrument,available_at,8.0 chip_cost_15,12+sin(epoch(trade_date)/86400)*.3 chip_cost_85,10.0 chip_weighted_cost FROM daily",
            "auction": "SELECT trade_date,instrument,available_at,cos(epoch(trade_date)/86400)*.01 auction_return FROM daily",
        }
        sources = []
        for name, q in queries.items():
            path = inputs / f"{name}.parquet"
            con.execute(f"COPY ({q}) TO {auditor.quote(path)} (FORMAT PARQUET)")
            con.execute(
                f"CREATE VIEW {name}_source AS SELECT * FROM read_parquet({auditor.quote(path)})"
            )
            sources.append({"source": name, "file": path.name, "sha256": file_sha(path)})
        (inputs / "manifest.json").write_text(
            json.dumps({"sources": sources, "snapshot_sha256": sha256_json(sources)})
        )
        raw, _ = load_frozen_days(inputs)
        prepared, coverage = prepare(raw)
        calendar = [d.date for d in prepared]
        cache = {}
        pairs = training_pairs(prepared, cache)
        fields = {d.date: d.features for d in prepared if d.date in cache}
        con.execute(
            "CREATE TABLE calendar AS SELECT key::INTEGER idx,value::DATE date FROM json_each(?)",
            [json.dumps(calendar)],
        )
        con.execute(
            (Path(__file__).resolve().parents[1] / "scripts/pairwise_source_audit.sql").read_text()
        )
        assert auditor.source_check(con, fields, coverage, calendar) > 10000
        ref = auditor.pair_reference(con, calendar, cache)
        auditor.compare(pairs, ref, "full raw labels")
        bad = copy.deepcopy(pairs)
        bad[0]["left_label"]["return"] += 0.01
        with pytest.raises(ValueError):
            auditor.compare(bad, ref, "fake label")


def test_native24reservations32fits_and_exclusive_output(auditor, tmp_path):
    from run_pairwise_ranking import reserve, write_gzip

    spec = {"plans": plans(), "runtime_code_sha256": "synthetic-code"}
    reg, tids = reserve(tmp_path, spec)
    rows, calendar = labels()
    models, paths = {}, {}
    result = {"spec": spec, "records": {}, "models_sha256": {}}
    for b in BASES:
        for k in KINDS:
            mk = f"{b}-{k}"
            models[mk], paths[mk] = {}, {}
            for y in (2023, 2024):
                m = fit_model(rows, calendar, y, b, k)
                p = tmp_path / f"{mk}-{y}.json"
                p.write_text(json.dumps(m))
                models[mk][y], paths[mk][y] = m, p
                result["models_sha256"][f"{mk}-{y}"] = file_sha(p)
    for p in plans():
        key = p["key"]
        if p["policy"] in KINDS:
            mk = key.rsplit("-", 1)[0]
            for y in (2023, 2024):
                reg.record_model_fit(
                    tids[key], str(y), model=models[mk][y], artifact_path=paths[mk][y]
                )
        row = {"fit_lineage_sha256": reg.fit_lineage(tids[key])["sha256"]}
        reg.record_trial_result(tids[key], json.dumps(row))
        result["records"][key] = row
    auditor.native_check(tmp_path, result, models)
    write_gzip(tmp_path / "evidence.gz", {"fixture": 1})
    with pytest.raises(FileExistsError):
        write_gzip(tmp_path / "evidence.gz", {"fixture": 2})
    assert auditor.unzip(tmp_path / "evidence.gz") == {"fixture": 1}
