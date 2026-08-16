from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

from stephen_quant.qmt import (
    DynamicUniverseConfig,
    build_dynamic_universe,
    write_dynamic_universe,
)


def _write_day(daily: Path, fundamental: Path, day: date, index: int) -> None:
    names = {"000001.SZ": "甲公司", "000002.SZ": "乙公司", "600001.SH": "丙公司"}
    if index == 4:
        names["000002.SZ"] = "ST乙公司"
    with (daily / f"{day:%Y%m%d}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "代码", "名称", "成交量(手)", "成交额(千元)"])
        writer.writerow([f"{day:%Y%m%d}", "000001.SZ", names["000001.SZ"], 100, 1000])
        writer.writerow([f"{day:%Y%m%d}", "000002.SZ", names["000002.SZ"], 100, 800])
        writer.writerow([f"{day:%Y%m%d}", "600001.SH", names["600001.SH"], 100, 500])
    with (fundamental / f"{day:%Y%m%d}.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "代码", "名称", "上市日期"])
        writer.writerow([f"{day:%Y%m%d}", "000001.SZ", names["000001.SZ"], "20200101"])
        writer.writerow([f"{day:%Y%m%d}", "000002.SZ", names["000002.SZ"], "20200101"])
        writer.writerow([f"{day:%Y%m%d}", "600001.SH", names["600001.SH"], "20250101"])


def test_dynamic_universe_uses_daily_point_in_time_membership(tmp_path: Path) -> None:
    daily, fundamental = tmp_path / "daily", tmp_path / "fundamental"
    daily.mkdir()
    fundamental.mkdir()
    start = date(2024, 1, 2)
    days = [start + timedelta(days=index) for index in range(5)]
    for index, day in enumerate(days):
        _write_day(daily, fundamental, day, index)

    report = build_dynamic_universe(
        daily,
        fundamental,
        DynamicUniverseConfig(
            research_start=days[2].isoformat(),
            research_end=days[4].isoformat(),
            top_n=2,
            minimum_history_sessions=3,
            liquidity_lookback=2,
            minimum_mean_amount_cny=1,
        ),
    )
    artifacts = write_dynamic_universe(report, tmp_path / "output")

    assert report.sessions == 3
    assert report.memberships[0].members == ("000001.SZ", "000002.SZ")
    assert report.memberships[-1].members == ("000001.SZ",)
    assert report.memberships[-1].exits == ("000002.SZ",)
    assert report.memberships[-1].exclusions["risk_warning_or_delisting"] == 1
    assert report.memberships[-1].exclusions["unknown_or_future_listing_date"] == 1
    assert artifacts.membership_jsonl_path.exists()
    assert report.source_snapshot_sha256
