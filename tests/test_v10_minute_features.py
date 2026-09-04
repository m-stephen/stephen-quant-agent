from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import duckdb

from stephen_quant.qmt.minute_features import (
    FEATURE_REGISTRY,
    build_minute_feature_mart,
    verify_minute_feature_snapshot,
)
from stephen_quant.qmt.minute_warehouse import ingest_minute_archives


def _csv(day: str, interval: int) -> bytes:
    rows = ["日期,时间,开盘,最高,最低,收盘,成交量,成交额\n"]
    clocks = ["09:31", "10:00", "14:30", "15:00"]
    for index, clock in enumerate(clocks):
        price = 10.0 + index * interval * 0.001
        rows.append(f"{day},{clock},{price},{price+0.02},{price-0.02},{price+0.01},{100+index},{(100+index)*price}\n")
    return "".join(rows).encode("utf-8-sig")


def test_v10_minute_feature_truth_timing_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "source" / "分钟K线合集" / "2024" / "最新更新"
    source.mkdir(parents=True)
    archive = source / "20240102.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for interval in (1, 5, 15, 30, 60):
            handle.writestr(f"{interval}min/sz000001.csv", _csv("2024-01-02", interval))
    warehouse = tmp_path / "warehouse"
    minute = ingest_minute_archives(
        tmp_path / "source",
        warehouse,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        intervals=(1, 5, 15, 30, 60),
    )
    result = build_minute_feature_mart(
        warehouse,
        minute_snapshot_id=str(minute["snapshot_id"]),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
    )
    assert result["status"] == "COMPLETED"
    assert result["row_count"] == 1
    assert len(FEATURE_REGISTRY) >= 12
    connection = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        row = connection.execute(
            "SELECT intraday_return,realized_volatility,multiscale_intervals,quality_state,"
            "effective_at<available_at,sealed FROM qd_minute_features_current"
        ).fetchone()
    finally:
        connection.close()
    assert row[0] > 0
    assert row[1] > 0
    assert row[2] == 5
    assert row[3] == "SPARSE"
    assert row[4] is True
    assert row[5] is False
    assert verify_minute_feature_snapshot(
        warehouse, str(result["feature_snapshot_id"])
    )["passed"] is True

    replay = build_minute_feature_mart(
        warehouse,
        minute_snapshot_id=str(minute["snapshot_id"]),
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
    )
    assert replay["status"] == "REPLAY_NOOP"
    assert replay["feature_snapshot_id"] == result["feature_snapshot_id"]
