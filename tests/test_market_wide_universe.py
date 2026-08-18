from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.qmt import (
    MarketWideUniverseConfig,
    build_market_wide_universe,
    write_market_wide_universe,
)
from stephen_quant.qmt.models import QmtDataError
from stephen_quant.workflows.price_discovery_lab import (
    _execution_memberships,
    _load_memberships,
)


def _write_market_day(
    daily: Path,
    fundamental: Path,
    day: date,
    *,
    st_code: str | None = None,
    invalid_cap_code: str | None = None,
) -> None:
    instruments = tuple(f"00000{index}.SZ" for index in range(1, 7))
    with (daily / f"{day:%Y%m%d}.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["日期", "代码", "名称", "成交量(手)", "成交额(千元)", "总市值(万元)"]
        )
        for index, instrument in enumerate(instruments, start=1):
            name = f"公司{index}" if instrument != st_code else f"ST公司{index}"
            cap = 0 if instrument == invalid_cap_code else index * 10_000
            writer.writerow([f"{day:%Y%m%d}", instrument, name, 100, index * 1000, cap])
    with (fundamental / f"{day:%Y%m%d}.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "代码", "名称", "上市日期"])
        for index, instrument in enumerate(instruments, start=1):
            name = f"公司{index}" if instrument != st_code else f"ST公司{index}"
            writer.writerow([f"{day:%Y%m%d}", instrument, name, "20200101"])


def test_market_wide_universe_keeps_all_eligible_and_builds_buckets(tmp_path: Path) -> None:
    daily, fundamental = tmp_path / "daily", tmp_path / "fundamental"
    daily.mkdir()
    fundamental.mkdir()
    start = date(2024, 1, 2)
    days = [start + timedelta(days=index) for index in range(3)]
    for day in days:
        _write_market_day(daily, fundamental, day)

    report = build_market_wide_universe(
        daily,
        fundamental,
        MarketWideUniverseConfig(
            research_start=days[1].isoformat(),
            research_end=days[2].isoformat(),
            minimum_history_sessions=2,
            liquidity_lookback=2,
            minimum_mean_amount_cny=1,
        ),
    )
    artifacts = write_market_wide_universe(report, tmp_path / "output")

    first = report.memberships[0]
    assert first.eligible_candidates == 6
    assert len(first.members) == 6
    assert first.members[0] == "000006.SZ"
    assert set().union(*map(set, first.size_buckets.values())) == set(first.members)
    assert set().union(*map(set, first.liquidity_buckets.values())) == set(first.members)
    assert first.size_buckets["small"] == ("000001.SZ",)
    assert first.size_buckets["large"] == ("000005.SZ", "000006.SZ")
    assert set(first.research_members) == set(first.members)
    assert set(first.screening_members) == set(first.members)
    assert artifacts.membership_jsonl_sha256
    assert artifacts.research_membership_jsonl_sha256
    assert artifacts.research_tiers_jsonl_sha256
    assert artifacts.screening_membership_jsonl_sha256

    memberships, _ = _load_memberships(
        artifacts.research_membership_jsonl_path, 10_000
    )
    execution = _execution_memberships(
        memberships,
        (days[1].isoformat(), days[2].isoformat()),
    )
    assert execution[days[1].isoformat()] == ()
    assert set(execution[days[2].isoformat()]) == set(first.members)


def test_market_wide_universe_fails_closed_on_unapproved_metadata_gap(
    tmp_path: Path,
) -> None:
    daily, fundamental = tmp_path / "daily", tmp_path / "fundamental"
    daily.mkdir()
    fundamental.mkdir()
    day = date(2024, 1, 2)
    _write_market_day(daily, fundamental, day)
    (fundamental / f"{day:%Y%m%d}.csv").unlink()

    with pytest.raises(QmtDataError, match="missing exact same-day"):
        build_market_wide_universe(
            daily,
            fundamental,
            MarketWideUniverseConfig(
                research_start=day.isoformat(),
                research_end=day.isoformat(),
                minimum_history_sessions=1,
                liquidity_lookback=1,
                minimum_mean_amount_cny=1,
            ),
        )


def test_market_wide_universe_excludes_st_and_invalid_market_cap(tmp_path: Path) -> None:
    daily, fundamental = tmp_path / "daily", tmp_path / "fundamental"
    daily.mkdir()
    fundamental.mkdir()
    day = date(2024, 1, 2)
    _write_market_day(
        daily,
        fundamental,
        day,
        st_code="000002.SZ",
        invalid_cap_code="000003.SZ",
    )

    report = build_market_wide_universe(
        daily,
        fundamental,
        MarketWideUniverseConfig(
            research_start=day.isoformat(),
            research_end=day.isoformat(),
            minimum_history_sessions=1,
            liquidity_lookback=1,
            minimum_mean_amount_cny=1,
        ),
    )
    membership = report.memberships[0]
    assert "000002.SZ" not in membership.members
    assert "000003.SZ" not in membership.members
    assert membership.exclusions["risk_warning_or_delisting"] == 1
    assert membership.exclusions["invalid_market_cap"] == 1
