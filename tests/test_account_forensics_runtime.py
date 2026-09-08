"""Integrated saved-account forensic component on small, fully synthetic artifacts."""

import copy
import csv
import json
import time
from dataclasses import asdict
from pathlib import Path

import duckdb
import pytest
from test_account_forensics_inputs import synthetic_calendar
from test_account_forensics_persistence import fixture

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.account_forensics_evidence import GROUPS
from stephen_quant.discovery.account_forensics_runtime import build_saved_report
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def save(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return file_sha(path)


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    started = time.perf_counter()

    def stage(label):
        print(f"SYNTHETIC_STAGE {label} elapsed={time.perf_counter() - started:.3f}", flush=True)

    stage("fixture_begin")
    root = tmp_path_factory.mktemp("forensic-synthetic")
    calendar = synthetic_calendar()
    execution = calendar[242:]
    targets, diagnostics = fixture()
    remap = dict(zip([t["trade_date"] for t in targets], execution, strict=True))
    for t in targets:
        t["trade_date"] = remap[t["trade_date"]]
    for d in diagnostics:
        d["date"], d["execution_date"] = remap[d["date"]], remap[d["execution_date"]]
    ranks = {dt: {f"S{n:03d}": {"cell": n % 20} for n in range(200)} for dt in calendar}
    bars, sessions, source_rows = {}, [], []
    for i, dt in enumerate(calendar):
        rows = []
        for n in range(200):
            if n == 1 and 245 <= i < 269:
                continue  # Exactly24 missing execution sessions, followed by recovery.
            name, price = f"S{n:03d}", 10 + n / 100
            b = StatefulBar(dt, name, price, price, 1e9, dt + "T08:00:00+08:00")
            rows.append(b)
            source_rows.append((dt, name, "synthetic", price, price, 1000000, 1000000,
                                1, dt + "T18:00:00+08:00"))
        bars[dt] = {b.instrument: asdict(b) for b in rows}
        if dt >= "2023-01-01":
            sessions.append(tuple(rows))
    native_targets = tuple(TargetAllocation(t["trade_date"], t["trade_date"] + "T08:00:00+08:00",
                                            t["weights"], t["rebalance"]) for t in targets)
    reports = {}
    for cost in (82, 164):
        scale = cost / 82
        config = StatefulExecutionConfig(commission_bps=6 * scale, slippage_bps=30 * scale,
                                         sell_tax_bps=10 * scale, rebalance_mode="target_changes")
        reports[cost] = asdict(run_stateful_execution(tuple(sessions), native_targets, config,
                                                     initial_nav=3_000_000))
    bindings = {}
    for group, policies in GROUPS.items():
        folder = root / group
        files, accounts = {}, {}
        files["RESULT.json"] = save(folder, "RESULT.json", {
            "diagnostics": {policy: diagnostics for policy in policies}})
        for p in policies:
            target = f"targets/{p}.json"
            files[target] = save(folder, target, targets)
            for c in (82, 164):
                key = f"{p}-{c}"
                report, ledger = f"account_reports/{key}.json", f"accounts/{key}.jsonl"
                files[report] = save(folder, report, reports[c])
                files[ledger] = save(folder, ledger, {"synthetic_binding_only": True})
                accounts[f"{group}/{key}"] = {"key": key, "report": report,
                                              "ledger": ledger, "target": target}
        bindings[group] = {"root": str(folder), "files": files, "accounts": accounts}
    history_root = root / "history-input"
    history_sha = save(history_root, "history/history.json", {
        "calendar": calendar, "bars": bars, "ranks": ranks})
    bindings["history"] = {"root": str(history_root), "files": {"history/history.json": history_sha}}
    stage("history_saved")
    source = root / "sources"
    source.mkdir()
    import _duckdb

    print("SYNTHETIC_DUCKDB", duckdb.__version__, _duckdb.__file__,
          file_sha(Path(_duckdb.__file__)), flush=True)
    stage("connect_before")
    with duckdb.connect(":memory:", config={"threads": 1}) as db:
        stage("connect_after")
        stage("create_before")
        db.execute("CREATE TABLE daily(trade_date VARCHAR,instrument VARCHAR,name VARCHAR,"
                   "open DOUBLE,close DOUBLE,amount DOUBLE,volume DOUBLE,"
                   "adjustment_factor DOUBLE,available_at VARCHAR)")
        stage("create_after")
        # Transport the unchanged synthetic rows through COPY, not large Python
        # list parameters. Explicit table schema and exact field-level roundtrip
        # checks keep this a fixture transport change, not a data-model change.
        stage("csv_write_before")
        csv_path = root / "synthetic-daily.csv"
        fields = ("trade_date", "instrument", "name", "open", "close", "amount", "volume",
                  "adjustment_factor", "available_at")
        with csv_path.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter=",", quotechar='"', lineterminator="\n")
            writer.writerow(fields)
            writer.writerows(source_rows)
        stage("csv_write_after")
        stage("csv_copy_before")
        db.execute("COPY daily FROM ? (FORMAT CSV, HEADER true, DELIMITER ',', QUOTE '\"', ESCAPE '\"')",
                   [str(csv_path)])
        stage("csv_copy_after")
        stage("count_before")
        assert db.execute("SELECT count(*) FROM daily").fetchone()[0] == len(source_rows)
        stage("count_after")
        assert len(source_rows) == 145176
        stage("csv_roundtrip_before")
        verify_rows(db.execute("SELECT * FROM daily ORDER BY trade_date,instrument"), source_rows)
        stage("csv_roundtrip_after")
        stage("copy_before")
        db.execute("COPY daily TO ? (FORMAT PARQUET)", [str(source / "daily.parquet")])
        stage("copy_after")
        stage("parquet_roundtrip_before")
        verify_rows(db.execute("SELECT * FROM read_parquet(?) ORDER BY trade_date,instrument",
                               [str(source / "daily.parquet")]), source_rows)
        stage("parquet_roundtrip_after")
        transport = {"rows": len(source_rows), "fields": fields,
                     "expected_rows_sha256": sha256_json(source_rows),
                     "csv_sha256": file_sha(csv_path),
                     "parquet_sha256": file_sha(source / "daily.parquet"),
                     "exact_csv_and_parquet_roundtrip": True}
        save(root, "SYNTHETIC_TRANSPORT.json", transport)
        print("SYNTHETIC_TRANSPORT", json.dumps(transport, sort_keys=True), flush=True)
    stage("connection_closed")
    save(source, "fund_flow.parquet", {"synthetic": "hashed only"})
    save(source, "manifest.json", {"synthetic": True})
    bindings["sources"] = {"root": str(source), "files": {
        n: file_sha(source / n) for n in ("daily.parquet", "fund_flow.parquet", "manifest.json")}}
    evidence = {"bindings": bindings, "account_count": 12, "raw_global_trial_lower_bound": 3737,
                "new_accounts": 0, "new_fits": 0, "new_predictions": 0, "validated_alpha": False}
    stage("fixture_ready")
    return evidence, {"count": 726, "sha256": sha256_json(calendar)}


def verify_rows(cursor, expected):
    index, previous = 0, None
    while batch := cursor.fetchmany(2048):
        for actual in batch:
            assert index < len(expected), "extra synthetic row"
            key = actual[:2]
            assert previous is None or key > previous, "duplicate or unordered synthetic key"
            assert actual == expected[index], "synthetic field transport changed"
            previous = key
            index += 1
    assert index == len(expected), "missing synthetic row"


def test_all12_native_saved_accounts_and_actual_parquet_sources(artifacts, tmp_path):
    evidence, binding = artifacts
    out = tmp_path / "report"
    print("SYNTHETIC_STAGE full_report_before", flush=True)
    result = build_saved_report(evidence, calendar_binding=binding, output=out)
    print("SYNTHETIC_STAGE full_report_after", flush=True)
    assert result["account_count"] == 12 and len(result["execution_calendar"]) == 484
    assert result["source_query"]["absent_keys"] == 24
    assert result["source_query"]["matched_rows"] == 2
    assert set(result["source_status"].values()) == {"EXPLAINED_BY_FROZEN_SOURCE"}
    assert all(v["maintenance_count"] == 97 for v in result["membership"].values())
    assert len(result["output_files"]) == 38
    assert result["primary"]["82"]["windows"]["continuous"]["profit_difference_cny"] == 0
    assert not result["validated_alpha"]
    assert result["component_status"] == "SAVED_REPORT_BUILT_NOT_INDEPENDENTLY_VERIFIED"
    for name, digest in result["output_files"].items():
        assert file_sha(out / name) == digest
    with pytest.raises(FileExistsError):
        build_saved_report(evidence, calendar_binding=binding, output=out)


@pytest.mark.parametrize("bad", ["missing", "identity", "path", "debt", "fit", "eligible",
                                  "result_binding", "extra_binding"])
def test_bad_contract_or_bytes_fail_closed(artifacts, tmp_path, bad):
    evidence, binding = copy.deepcopy(artifacts)
    if bad == "missing":
        evidence["bindings"]["grouped"]["accounts"].pop("grouped/risk-82")
    elif bad == "identity":
        evidence["account_count"] = 11
    elif bad == "path":
        evidence["bindings"]["grouped"]["accounts"]["grouped/risk-82"]["report"] = "../escape"
    elif bad == "debt":
        evidence["raw_global_trial_lower_bound"] = 0
    elif bad == "fit":
        evidence["new_fits"] = 1
    elif bad == "result_binding":
        evidence["bindings"]["construction"]["files"].pop("RESULT.json")
    elif bad == "extra_binding":
        evidence["bindings"]["construction"]["files"]["unselected.json"] = "0" * 64
    else:
        evidence["bindings"]["grouped"]["files"]["account_reports/risk-82.json"] = "0" * 64
    out = tmp_path / "report"
    with pytest.raises(ValueError):
        build_saved_report(evidence, calendar_binding=binding, output=out)
    if bad == "eligible":
        terminal = json.loads((out / "TERMINAL.json").read_text())
        assert terminal["outcome"] == "FAILED" and terminal["stage"] == "input_verification"
        assert not (out / "SUMMARY.json").exists()


def test_overlapping_output_refused_without_touching_source(artifacts):
    evidence, binding = artifacts
    out = Path(evidence["bindings"]["sources"]["root"]) / "report"
    with pytest.raises(ValueError, match="disjoint"):
        build_saved_report(evidence, calendar_binding=binding, output=out)
    assert not out.exists()


def test_intermediate_failure_keeps_partial_without_summary(artifacts, tmp_path, monkeypatch):
    from stephen_quant.discovery import account_forensics_runtime as runtime

    evidence, binding = artifacts
    original = runtime.account_summary
    calls = 0

    def fail_second(report, *, calendar):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("synthetic intermediate failure")
        return original(report, calendar=calendar)

    monkeypatch.setattr(runtime, "account_summary", fail_second)
    out = tmp_path / "partial"
    with pytest.raises(ValueError, match="synthetic intermediate"):
        build_saved_report(evidence, calendar_binding=binding, output=out)
    terminal = json.loads((out / "TERMINAL.json").read_text())
    assert terminal["outcome"] == "FAILED"
    assert len(terminal["completed_account_keys"]) == 1
    assert terminal["stage"].startswith("saved_account:")
    assert terminal["automatic_retry"] is False
    assert len(list((out / "chains").glob("*.json"))) == 1
    assert not (out / "SUMMARY.json").exists()
    with pytest.raises(FileExistsError):
        build_saved_report(evidence, calendar_binding=binding, output=out)
