from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.workflows import (
    DynamicBacktestConfig,
    run_dynamic_stateful_backtest,
)


def _weekdays(start: date, count: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _write_fixture(root: Path, benchmark: Path, days: list[date]) -> None:
    instruments = ("000001.SZ", "000002.SZ", "600001.SH")
    for day_index, day in enumerate(days):
        with (root / f"{day:%Y%m%d}.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "日期",
                    "代码",
                    "名称",
                    "开盘价",
                    "最高价",
                    "最低价",
                    "收盘价",
                    "昨日收盘价",
                    "成交量(手)",
                    "成交额(千元)",
                    "复权因子",
                ]
            )
            for instrument_index, instrument in enumerate(instruments, start=1):
                value = 10 + instrument_index + day_index * instrument_index * 0.01
                previous = value - instrument_index * 0.01
                writer.writerow(
                    [
                        f"{day:%Y%m%d}",
                        instrument,
                        instrument,
                        value,
                        value * 1.01,
                        value * 0.99,
                        value,
                        previous,
                        100_000,
                        100_000,
                        1,
                    ]
                )
    with benchmark.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["代码", "日期", "收盘价", "开盘价"])
        for index, day in enumerate(days):
            writer.writerow(["000300.SH", f"{day:%Y%m%d}", 1000 + index, 1000 + index])


def test_dynamic_membership_factor_and_stateful_execution_connect(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    daily.mkdir()
    benchmark = tmp_path / "benchmark.csv"
    days = _weekdays(date(2023, 1, 2), 126)
    _write_fixture(daily, benchmark, days)
    membership = tmp_path / "membership.jsonl"
    members = ["000001.SZ", "000002.SZ", "600001.SH"]
    membership.write_text(
        "".join(
            json.dumps(
                {
                    "decision_date": day.isoformat(),
                    "decision_at": f"{day.isoformat()}T15:01:00+08:00",
                    "members": members,
                }
            )
            + "\n"
            for day in days[120:]
        ),
        encoding="utf-8",
    )
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")

    run = run_dynamic_stateful_backtest(
        daily,
        membership,
        benchmark,
        registry=registry,
        output_dir=tmp_path / "report",
        code_version="test-sha",
        config=DynamicBacktestConfig(
            data_start=days[0].isoformat(),
            research_start=days[120].isoformat(),
            research_end=days[-1].isoformat(),
            validation_start="2024-01-02",
            validation_end="2024-12-31",
            test_start="2025-01-02",
            test_end="2025-12-31",
            top_k=2,
            rebalance_every=2,
            cash_reserve=0.0,
            maximum_position_weight=0.5,
            commission_bps=0,
            sell_tax_bps=0,
            slippage_bps=0,
        ),
    )

    assert run.report.membership_sessions == 6
    assert run.report.execution_sessions == 5
    assert run.report.signal_failures == 0
    assert run.report.execution.metrics.periods == 5
    assert run.report.benchmark.periods == 5
    assert run.report.decision == "ENGINEERING_COMPLETE_NO_ALPHA_CLAIM"
    assert registry.trial_count(run.report.experiment_id) == 1
    assert run.report_json_path.exists()
