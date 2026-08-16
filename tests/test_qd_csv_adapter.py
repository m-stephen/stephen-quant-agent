from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineConfig
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.qmt import (
    QmtDataError,
    load_qd_daily_directory,
    select_qd_training_universe,
    write_qd_universe,
)
from stephen_quant.workflows import QmtBacktestRunConfig, run_qmt_backtest_workflow

INSTRUMENTS = ("000001.SZ", "000002.SZ", "600000.SH", "600001.SH")


def _trading_dates(count: int = 10) -> list[date]:
    result: list[date] = []
    current = date(2025, 1, 2)
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _write_partition(
    root: Path,
    day: date,
    index: int,
    *,
    row_day: date | None = None,
) -> None:
    growth = {"000001.SZ": 1.02, "000002.SZ": 1.01, "600000.SH": 1.0, "600001.SH": 0.995}
    with (root / f"{day:%Y%m%d}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
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
                "成交量(手)",
                "成交额(千元)",
                "复权因子",
            ]
        )
        for instrument, rate in growth.items():
            value = 10.0 * rate**index
            writer.writerow(
                [
                    (row_day or day).strftime("%Y%m%d"),
                    instrument,
                    instrument,
                    f"{value:.8f}",
                    f"{value * 1.01:.8f}",
                    f"{value * 0.99:.8f}",
                    f"{value:.8f}",
                    "10000.5",
                    "100000.25",
                    "2.5",
                ]
            )


def _write_directory(root: Path) -> list[date]:
    dates = _trading_dates()
    for index, day in enumerate(dates):
        _write_partition(root, day, index)
    return dates


def test_qd_directory_adapter_converts_units_and_freezes_selected_files(tmp_path: Path) -> None:
    dates = _write_directory(tmp_path)

    dataset = load_qd_daily_directory(
        tmp_path,
        start_date=dates[0].isoformat(),
        end_date=dates[1].isoformat(),
        instruments=INSTRUMENTS,
        adjustment="back_ratio",
        include_next_after_end=True,
    )

    assert len(dataset.bars) == 12
    assert dataset.bars[0].open == 25.0
    assert dataset.bars[0].volume == 1_000_050
    assert dataset.bars[0].amount == 100_000_250
    assert dataset.audit.source_files == 3
    assert dataset.audit.instruments == 4
    assert dataset.audit.adjustment == "back_ratio"
    assert dataset.audit.source_sha256
    assert dataset.audit.unit_conversions == {
        "volume_lot_to_share": 100.0,
        "amount_thousand_cny_to_cny": 1000.0,
    }


def test_qd_directory_adapter_rejects_row_date_filename_mismatch(tmp_path: Path) -> None:
    day = date(2025, 1, 2)
    _write_partition(tmp_path, day, 0, row_day=date(2025, 1, 3))

    with pytest.raises(QmtDataError, match="does not match filename"):
        load_qd_daily_directory(
            tmp_path,
            start_date=day.isoformat(),
            end_date=day.isoformat(),
            instruments=INSTRUMENTS,
        )


def test_qd_directory_runs_existing_trial_first_backtest_workflow(tmp_path: Path) -> None:
    source = tmp_path / "daily"
    source.mkdir()
    dates = _write_directory(source)
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    config = QmtBacktestRunConfig(
        factor_id="ret_5",
        factor_version="1.0.0",
        adjustment="none",
        train_start="2023-01-01",
        train_end="2023-12-31",
        validation_start="2024-01-01",
        validation_end="2024-12-31",
        test_start=dates[6].isoformat(),
        test_end=dates[8].isoformat(),
        adv_lookback=3,
        instruments=INSTRUMENTS,
        portfolio=BaselineConfig(
            top_k=2,
            rebalance_every=1,
            max_position_weight=0.5,
            commission_bps=3.0,
            sell_tax_bps=5.0,
            slippage_bps=5.0,
            impact_coefficient_bps=10.0,
            max_participation_rate=0.05,
        ),
    )

    run = run_qmt_backtest_workflow(
        source,
        registry=registry,
        output_dir=tmp_path / "reports",
        config=config,
        code_version="test-sha",
    )

    assert run.report.metrics.periods == 3
    assert registry.trial_count(run.experiment_id) == 1
    assert run.report.lineage.snapshot_id == run.snapshot_id
    assert run.data_audit_path.exists()


def test_qd_universe_uses_training_only_metadata_and_liquidity(tmp_path: Path) -> None:
    daily = tmp_path / "股票日K_按日期"
    fundamental = tmp_path / "基本面指标"
    daily.mkdir()
    fundamental.mkdir()
    dates = _trading_dates(3)
    instruments = (
        ("000001.SZ", "正常一", "20200101", 1000),
        ("000002.SZ", "正常二", "20200101", 900),
        ("000003.SZ", "ST风险", "20200101", 5000),
        ("000004.SZ", "新股", dates[1].strftime("%Y%m%d"), 4000),
        ("000005.SZ", "日期未知", "0", 6000),
    )
    for day_index, day in enumerate(dates):
        with (daily / f"{day:%Y%m%d}.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["日期", "代码", "成交额(千元)"])
            for instrument, _, _, amount in instruments:
                if instrument == "000002.SZ" and day_index == 1:
                    continue
                writer.writerow([day.strftime("%Y%m%d"), instrument, amount])
    with (fundamental / f"{dates[-1]:%Y%m%d}.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "代码", "名称", "上市日期"])
        for instrument, name, listed, _ in instruments:
            writer.writerow([dates[-1].strftime("%Y%m%d"), instrument, name, listed])

    selection = select_qd_training_universe(
        daily,
        fundamental,
        train_start=dates[0].isoformat(),
        train_end=dates[-1].isoformat(),
        top_n=1,
    )
    artifacts = write_qd_universe(selection, tmp_path / "universe")

    assert selection.instruments == ("000001.SZ",)
    assert selection.candidates_seen == 5
    assert selection.complete_history_candidates == 4
    assert selection.unknown_listing_date_records == 1
    assert selection.eligible_candidates == 1
    assert artifacts.stock_file_path.read_text(encoding="utf-8") == "000001.SZ\n"
    assert json.loads(artifacts.json_path.read_text(encoding="utf-8"))["exclude_st"]


def test_qd_workflow_writes_benchmark_and_placebo_audits(tmp_path: Path) -> None:
    source = tmp_path / "daily"
    source.mkdir()
    dates = _write_directory(source)
    benchmark = tmp_path / "benchmark.csv"
    with benchmark.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "开盘价"])
        writer.writerow(["19900101", ""])
        for index, day in enumerate(dates):
            writer.writerow([day.strftime("%Y%m%d"), 100 + index])
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    config = QmtBacktestRunConfig(
        factor_id="ret_5",
        factor_version="1.0.0",
        adjustment="none",
        train_start="2023-01-01",
        train_end="2023-12-31",
        validation_start="2024-01-01",
        validation_end="2024-12-31",
        test_start=dates[6].isoformat(),
        test_end=dates[8].isoformat(),
        adv_lookback=3,
        instruments=INSTRUMENTS,
        benchmark_csv=str(benchmark),
        benchmark_name="fixture",
        placebo_repetitions=9,
        portfolio=BaselineConfig(
            top_k=2,
            rebalance_every=1,
            max_position_weight=0.5,
        ),
    )

    run = run_qmt_backtest_workflow(
        source,
        registry=registry,
        output_dir=tmp_path / "reports",
        config=config,
        code_version="test-sha",
    )

    assert run.benchmark_comparison_path is not None
    assert run.benchmark_comparison_path.exists()
    comparison = json.loads(run.benchmark_comparison_path.read_text(encoding="utf-8"))
    assert comparison["skipped_missing_open_rows"] == 1
    assert run.placebo_audit_path is not None
    assert run.placebo_audit_path.exists()
    assert registry.artifact_count(run.trial_id) == 7
