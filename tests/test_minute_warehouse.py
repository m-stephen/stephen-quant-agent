from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pytest

from stephen_quant.qmt.minute_warehouse import (
    catalog_minute_archives,
    ensure_minute_range,
    ingest_minute_archives,
    sync_available_daily_minutes,
    verify_minute_snapshot,
)
from stephen_quant.qmt.models import QmtDataError

HEADER = "日期,时间,开盘,最高,最低,收盘,成交量,成交额\n"


def _minute_csv(day: str, interval: int, offset: float) -> bytes:
    clocks = ("09:31", "09:32") if interval == 1 else ("09:35", "09:40")
    rows = [HEADER]
    for index, clock in enumerate(clocks):
        close = 10 + offset + index * 0.01
        rows.append(
            f"{day},{clock},{close},{close + 0.02},{close - 0.02},{close},100,100000\n"
        )
    return "".join(rows).encode("utf-8-sig")


def test_minute_archive_ingest_verify_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "source" / "分钟K线合集" / "2024" / "最新更新"
    source.mkdir(parents=True)
    archive = source / "20240102.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for instrument, offset in (("sz000001", 0.0), ("sh600000", 1.0)):
            handle.writestr(f"1min/{instrument}.csv", _minute_csv("2024-01-02", 1, offset))
            handle.writestr(f"5min/{instrument}.csv", _minute_csv("2024-01-02", 5, offset))
    warehouse = tmp_path / "warehouse"

    first = ingest_minute_archives(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1, 5),
    )
    assert first["status"] == "COMPLETED"
    assert first["new_archives"] == 1
    assert first["new_members"] == 4
    assert first["new_revisions"] == 8
    assert first["partition_count"] == 2
    verification = verify_minute_snapshot(warehouse, str(first["snapshot_id"]))
    assert verification["passed"] is True
    assert verification["revision_rows"] == 8

    connection = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM qd_minute_current").fetchone()[0] == 8
        assert connection.execute(
            "SELECT count(*) FROM qd_minute_current WHERE available_at <= ingested_at"
        ).fetchone()[0] == 8
        expected_epoch = 1704159060.0  # 2024-01-02 09:31:00 Asia/Shanghai
        assert connection.execute(
            "SELECT epoch(min(bar_at)) FROM qd_minute_current WHERE interval_minutes=1"
        ).fetchone()[0] == expected_epoch
    finally:
        connection.close()

    replay = ingest_minute_archives(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1, 5),
    )
    assert replay["status"] == "REPLAY_NOOP"
    assert replay["snapshot_id"] == first["snapshot_id"]


def test_available_daily_sync_and_catalog_report_observed_coverage(tmp_path: Path) -> None:
    source = tmp_path / "source" / "分钟K线合集" / "2026" / "最新更新"
    source.mkdir(parents=True)
    for day in ("20260102", "20260106"):
        with zipfile.ZipFile(source / f"{day}.zip", "w") as handle:
            handle.writestr(
                "1min/sz000001.csv",
                _minute_csv(f"{day[:4]}-{day[4:6]}-{day[6:]}", 1, 0),
            )
    warehouse = tmp_path / "warehouse"

    synced = sync_available_daily_minutes(tmp_path / "source", warehouse, intervals=(1,))
    assert synced["observed_trade_days"] == 2
    assert synced["coverage_start"] == "2026-01-02"
    assert synced["coverage_end"] == "2026-01-06"
    assert synced["new_revisions"] == 4
    assert "gaps are not synthesized" in str(synced["coverage_semantics"])

    catalog = catalog_minute_archives(tmp_path / "source", warehouse, intervals=(1,))
    assert catalog["archive_count"] == 2
    assert catalog["summaries"] == [
        {
            "status": "MATERIALIZED",
            "archive_count": 2,
            "selected_member_count": 2,
            "uncompressed_bytes": 330,
        }
    ]

    replay = sync_available_daily_minutes(tmp_path / "source", warehouse, intervals=(1,))
    assert replay["completed_batches"] == 0
    assert replay["replay_noop_batches"] == 2
    assert replay["snapshot_id"] == synced["snapshot_id"]

    ensured = ensure_minute_range(
        tmp_path / "source",
        warehouse,
        start_date=date(2026, 1, 2),
        end_date=date(2026, 1, 6),
        intervals=(1,),
    )
    assert ensured["daily_archive_dates"] == ["2026-01-02", "2026-01-06"]
    assert ensured["coverage"][0]["rows"] == 4
    assert all(batch["status"] == "REPLAY_NOOP" for batch in ensured["daily_batches"])


def test_ensure_historical_minute_range_extracts_only_requested_scope(tmp_path: Path) -> None:
    source = tmp_path / "source" / "分钟K线合集" / "2000-2025"
    source.mkdir(parents=True)
    older = _minute_csv("2023-12-29", 1, 0).decode("utf-8-sig")
    requested = _minute_csv("2024-01-02", 1, 1).decode("utf-8-sig")
    next_day = _minute_csv("2024-01-03", 1, 2).decode("utf-8-sig")
    combined = (
        older
        + "\n".join(requested.splitlines()[1:])
        + "\n"
        + "\n".join(next_day.splitlines()[1:])
        + "\n"
    ).encode("utf-8-sig")
    archive = source / "1分钟.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("1min/sz000001.csv", combined)
        handle.writestr("1min/sh600000.csv", _minute_csv("2024-01-02", 1, 2))
    warehouse = tmp_path / "warehouse"

    result = ensure_minute_range(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1,),
        instruments=("000001.SZ",),
    )
    assert result["status"] == "READY"
    assert result["historical_batch"]["new_members"] == 1
    assert result["historical_batch"]["new_revisions"] == 2
    assert result["coverage"] == [
        {
            "interval_minutes": 1,
            "rows": 2,
            "instruments": 1,
            "trade_days": 1,
            "min_date": "2024-01-02",
            "max_date": "2024-01-02",
        }
    ]

    replay = ensure_minute_range(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1,),
        instruments=("000001.SZ",),
    )
    assert replay["historical_batch"]["status"] == "REPLAY_NOOP"
    assert replay["historical_batch"]["new_revisions"] == 0

    overlap = ensure_minute_range(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 3),
        intervals=(1,),
        instruments=("000001.SZ",),
    )
    assert overlap["historical_batch"]["new_revisions"] == 2
    assert overlap["coverage"][0]["rows"] == 4
    assert overlap["coverage"][0]["trade_days"] == 2
    scoped_catalog = catalog_minute_archives(tmp_path / "source", warehouse, intervals=(1,))
    assert scoped_catalog["summaries"][0]["status"] == "PARTIAL"

    missing = ensure_minute_range(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1,),
        instruments=("000002.SZ",),
    )
    assert missing["coverage"] == []
    assert missing["source_gaps"][0]["reason"] == "source member is absent"

    with pytest.raises(QmtDataError, match="source bytes"):
        ensure_minute_range(
            tmp_path / "source",
            warehouse,
            start_date=date(2024, 1, 3),
            end_date=date(2024, 1, 3),
            intervals=(1,),
            instruments=("000001.SZ",),
            max_source_bytes=1,
        )
