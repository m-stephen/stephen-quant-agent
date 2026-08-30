from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import duckdb

from stephen_quant.qmt.minute_warehouse import (
    ingest_minute_archives,
    verify_minute_snapshot,
)

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
