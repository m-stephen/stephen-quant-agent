"""Synthetic bounded Parquet lookup and full calendar identity checks."""

from datetime import date, timedelta

import duckdb
import pytest

from stephen_quant.discovery.account_forensics_inputs import (
    event_source_keys,
    execution_calendar,
    read_daily_lookups,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def parquet(tmp_path, duplicate=False):
    path = tmp_path / "daily.parquet"
    with duckdb.connect(":memory:") as db:
        db.execute("CREATE TABLE daily(trade_date DATE,instrument VARCHAR,name VARCHAR,"
                   "open DOUBLE,close DOUBLE,amount DOUBLE,volume DOUBLE,"
                   "adjustment_factor DOUBLE,available_at TIMESTAMPTZ)")
        db.execute("INSERT INTO daily VALUES ('2023-01-04','S1','synthetic',9,10,100,100,2,"
                   "'2023-01-04T18:00:00+08:00'),"
                   "('2026-01-05','SEALED','not_requested',99,99,99,99,1,"
                   "'2026-01-05T18:00:00+08:00')")
        if duplicate:
            db.execute("INSERT INTO daily SELECT * FROM daily WHERE instrument='S1'")
        db.execute("COPY daily TO ? (FORMAT PARQUET)", [str(path)])
    (tmp_path / "fund_flow.parquet").write_bytes(b"SYNTHETIC_DO_NOT_PROJECT")
    (tmp_path / "manifest.json").write_text('{"synthetic":true}')
    return {"root": str(tmp_path), "files": {
        n: file_sha(tmp_path / n) for n in ("daily.parquet", "fund_flow.parquet", "manifest.json")}}


def test_only_requested_rows_projected_and_absence_explicit(tmp_path):
    binding = parquet(tmp_path)
    keys = [("2023-01-04", "S1"), ("2023-01-05", "S1")]
    rows, proof = read_daily_lookups(binding, keys)
    assert set(rows) == set(keys)
    assert rows[keys[0]]["open"] == 9 and rows[keys[1]] is None
    assert proof["matched_rows"] == proof["absent_keys"] == 1
    assert proof["input_bytes_unchanged"]
    assert "SEALED" not in str(rows)


def test_duplicate_source_key_refused(tmp_path):
    binding = parquet(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match="duplicate frozen"):
        read_daily_lookups(binding, [("2023-01-04", "S1")])


@pytest.mark.parametrize("keys", [[("2025-01-02", "S1")], [("2023-01-04", " S1")],
                                  [("2023-01-04", "S1")] * 2])
def test_invalid_keys_rejected_before_file_access(keys):
    with pytest.raises(ValueError):
        read_daily_lookups({"root": "nonexistent", "files": {}}, keys)


def test_tampered_file_prevents_query(tmp_path):
    binding = parquet(tmp_path)
    (tmp_path / "daily.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError):
        read_daily_lookups(binding, [("2023-01-04", "S1")])


def synthetic_calendar():
    days = []
    for year in (2022, 2023, 2024):
        start = date(year, 1, 3)
        eligible = [(start + timedelta(days=i)).isoformat() for i in range(360)
                    if (start + timedelta(days=i)).weekday() < 5]
        days.extend(eligible[:241] + [f"{year}-12-31"])
    return days


def test_exact_full_calendar_bound_not_just_endpoints():
    days = synthetic_calendar()
    frozen = {"count": 726, "sha256": sha256_json(days)}
    assert len(execution_calendar(days, frozen=frozen)) == 484
    days[20] = "2022-02-01"
    with pytest.raises(ValueError):
        execution_calendar(days, frozen=frozen)


def test_source_query_dedup_keeps_event_objects():
    chain = {"last_marked_date": "2023-01-03", "missing_sessions": [{"date": "2023-01-04"}]}
    a = {"events": [{"account": "A", "instrument": "S1", "event_type": "recovery",
                     "date": "2023-01-05", "stale_chain": chain}]}
    b = {"events": [{**a["events"][0], "account": "B"}]}
    assert event_source_keys([a, b]) == [(d, "S1") for d in
                                       ("2023-01-03", "2023-01-04", "2023-01-05")]
    assert a["events"][0]["account"] != b["events"][0]["account"]
