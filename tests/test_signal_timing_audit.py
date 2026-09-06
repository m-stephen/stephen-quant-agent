"""End-to-end independent auditor calibration using entirely synthetic prices."""

import csv
import gzip
import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.signal_timing import (
    day_response,
    endpoints,
    mature_indices,
    memberships,
    plans,
    strong_responses,
    summarize,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import protected_digest, write_json


def test_independent_endpoint_membership_sql_and_native_ledger(tmp_path, monkeypatch):
    duckdb = pytest.importorskip("duckdb")
    script = Path(__file__).resolve().parents[1] / "scripts/audit_signal_timing.py"
    spec = importlib.util.spec_from_file_location("timing_audit", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.chdir(tmp_path)
    root, inputs = tmp_path / "operation", tmp_path / "inputs"
    root.mkdir()
    inputs.mkdir()
    fs = {
        f"S{i:04}": {
            "volatility_20": (i + 1) / 1000,
            "liquidity": 1e7 * (i % 13 + 1),
            "ret_20": -i,
            "flow_consistency": i,
            "auction_tail_balance": -i,
            "chip_path_efficiency": -i,
        }
        for i in range(121)
    }
    days, raw = [], []
    for year in (2023, 2024):
        for i in range(30):
            dt = (date(year, 1, 1) + timedelta(days=i)).isoformat()
            bars = []
            for j, n in enumerate(fs):
                op = 100 + i + j / 100
                # Include a missing raw endpoint without changing the asof universe.
                if i == 10 and j == 0:
                    continue
                bars.append(StatefulBar(dt, n, op, op + 0.5, 1e6, f"{dt}T08:00:00+08:00"))
                raw.append([dt, n, op, op + 0.5, 1.0])
            days.append(ResearchDay(dt, fs, tuple(bars)))
    maps = [{b.instrument: b for b in d.bars} for d in days]
    with duckdb.connect() as con:
        con.execute(
            "CREATE TABLE raw(trade_date DATE,instrument VARCHAR,open DOUBLE,close DOUBLE,adjustment_factor DOUBLE)"
        )
        con.execute("BEGIN")
        con.executemany("INSERT INTO raw VALUES(?,?,?,?,?)", raw)
        con.execute("COMMIT")
        con.execute(f"COPY raw TO '{(inputs / 'daily.parquet').as_posix()}' (FORMAT PARQUET)")
    evidence = root / "endpoints.csv.gz"
    daily, count = [], 0
    with gzip.open(evidence, "xt", newline="", encoding="utf-8") as stream:
        writer = None
        for i in mature_indices(days):
            members = memberships(days[i].features)
            rows = [{**endpoints(days, maps, i, n), **m, **fs[n]} for n, m in members.items()]
            if writer is None:
                writer = csv.DictWriter(stream, list(rows[0]))
                writer.writeheader()
            writer.writerows(rows)
            daily.extend(day_response(rows))
            count += len(rows)
    write_json(root / "date_responses.json", daily)
    summary = summarize(daily)
    registry = ExperimentRegistry(root / "registry.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = registry.create_experiment(ExperimentSpec("fixture", "fixture", sid, "code", "{}"))
    for p in plans():
        tid = registry.create_trial(
            TrialSpec(
                eid,
                p["key"],
                sha256_json(p),
                json.dumps(p),
                1,
                "unused",
                "unused",
                "2023-01-01",
                "2024-12-31",
                "unused",
                "unused",
                fit_stages=(),
            )
        )
        registry.record_trial_result(tid[0], "{}")
    source = inputs / "daily.parquet"
    write_json(
        root / "RESULT.json",
        {
            "evidence_sha256": file_sha(evidence),
            "daily_sha256": file_sha(root / "date_responses.json"),
            "spec": {
                "protected_files": {str(source): file_sha(source)},
                "protected_before": protected_digest([source])[0],
            },
            "evidence_rows": count,
            "signal_dates": len(mature_indices(days)),
            "first_signal": days[0].date,
            "last_signal": days[mature_indices(days)[-1]].date,
            "summary": summary,
            "strong_responses": strong_responses(summary),
        },
    )
    mod.audit(root, inputs)
    report = json.loads((root / "INDEPENDENT_AUDIT.json").read_text())
    assert report["pass"]
    assert report["annual_rows"] == 180
    assert report["maximum_aggregate_difference"] < 1e-10
