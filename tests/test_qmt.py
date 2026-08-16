from __future__ import annotations

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineConfig
from stephen_quant.cli import main
from stephen_quant.factors import build_seed_registry
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.qmt import QmtDataError, build_qmt_factor_observations, load_qmt_daily_csv
from stephen_quant.workflows import QmtBacktestRunConfig, run_qmt_backtest_workflow


def _trading_dates(count: int = 10) -> list[date]:
    days: list[date] = []
    current = date(2025, 1, 2)
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _write_qmt_csv(path: Path, *, chinese: bool = False, omit: tuple[str, date] | None = None) -> None:
    headers = (
        ["日期", "股票代码", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]
        if chinese
        else ["time", "stock_code", "open", "high", "low", "close", "volume", "amount"]
    )
    growth = {"000001.SZ": 1.02, "000002.SZ": 1.01, "600000.SH": 1.0, "600001.SH": 0.995}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for index, day in enumerate(_trading_dates()):
            for instrument, rate in growth.items():
                if omit == (instrument, day):
                    continue
                value = 10.0 * rate**index
                writer.writerow(
                    [
                        day.strftime("%Y%m%d"),
                        instrument,
                        f"{value:.8f}",
                        f"{value * 1.01:.8f}",
                        f"{value * 0.99:.8f}",
                        f"{value:.8f}",
                        1_000_000,
                        f"{100_000_000 + index * 1_000_000:.2f}",
                    ]
                )


def _config() -> QmtBacktestRunConfig:
    dates = _trading_dates()
    return QmtBacktestRunConfig(
        factor_id="ret_5",
        factor_version="1.0.0",
        adjustment="front_ratio",
        train_start="2023-01-01",
        train_end="2023-12-31",
        validation_start="2024-01-01",
        validation_end="2024-12-31",
        test_start=dates[6].isoformat(),
        test_end=dates[8].isoformat(),
        adv_lookback=3,
        initial_nav=1_000_000.0,
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


@pytest.mark.parametrize("chinese", [False, True])
def test_qmt_adapter_supports_standard_and_chinese_headers(tmp_path: Path, chinese: bool) -> None:
    source = tmp_path / "daily.csv"
    _write_qmt_csv(source, chinese=chinese)

    dataset = load_qmt_daily_csv(source, adjustment="front_ratio")

    assert len(dataset.bars) == 40
    assert dataset.audit.instruments == 4
    assert dataset.audit.rows == 40
    assert dataset.audit.source_sha256
    assert dataset.audit.adjustment == "front_ratio"


def test_qmt_adapter_rejects_bad_ohlc_and_duplicate_bars(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "time,stock_code,open,high,low,close,volume,amount\n"
        "20250102,000001.SZ,10,9,8,10,1,10\n",
        encoding="utf-8",
    )
    with pytest.raises(QmtDataError, match="inconsistent OHLC"):
        load_qmt_daily_csv(source, adjustment="none")

    source.write_text(
        "time,stock_code,open,high,low,close,volume,amount\n"
        "20250102,000001.SZ,10,11,9,10,1,10\n"
        "20250102,000001.SZ,10,11,9,10,1,10\n",
        encoding="utf-8",
    )
    with pytest.raises(QmtDataError, match="duplicate daily bar"):
        load_qmt_daily_csv(source, adjustment="none")


def test_observations_use_prior_close_and_next_open(tmp_path: Path) -> None:
    source = tmp_path / "daily.csv"
    _write_qmt_csv(source)
    dataset = load_qmt_daily_csv(source, adjustment="front_ratio")
    dates = _trading_dates()

    observations = build_qmt_factor_observations(
        dataset.bars,
        build_seed_registry().get("ret_5"),
        test_start=dates[6].isoformat(),
        test_end=dates[8].isoformat(),
        adv_lookback=3,
    )

    assert len(observations) == 12
    first = observations[0]
    assert first.signal_at.startswith(dates[5].isoformat())
    assert first.signal_available_at < first.execution_at
    assert first.execution_at.startswith(dates[6].isoformat())
    assert first.return_end_at.startswith(dates[7].isoformat())

    three_session = build_qmt_factor_observations(
        dataset.bars,
        build_seed_registry().get("ret_5"),
        test_start=dates[6].isoformat(),
        test_end=dates[6].isoformat(),
        adv_lookback=3,
        horizon_sessions=3,
    )
    assert three_session[0].execution_at.startswith(dates[6].isoformat())
    assert three_session[0].return_end_at.startswith(dates[9].isoformat())

    with pytest.raises(QmtDataError, match="horizon_sessions"):
        build_qmt_factor_observations(
            dataset.bars,
            build_seed_registry().get("ret_5"),
            test_start=dates[6].isoformat(),
            test_end=dates[6].isoformat(),
            adv_lookback=3,
            horizon_sessions=0,
        )


def test_observation_builder_rejects_incomplete_panel(tmp_path: Path) -> None:
    source = tmp_path / "daily.csv"
    dates = _trading_dates()
    _write_qmt_csv(source, omit=("000001.SZ", dates[4]))
    dataset = load_qmt_daily_csv(source, adjustment="front_ratio")

    with pytest.raises(QmtDataError, match="incomplete QMT panel"):
        build_qmt_factor_observations(
            dataset.bars,
            build_seed_registry().get("ret_5"),
            test_start=dates[6].isoformat(),
            test_end=dates[8].isoformat(),
            adv_lookback=3,
        )


def test_qmt_workflow_runs_end_to_end_and_counts_repeated_trials(tmp_path: Path) -> None:
    source = tmp_path / "daily.csv"
    _write_qmt_csv(source, chinese=True)
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")

    first = run_qmt_backtest_workflow(
        source,
        registry=registry,
        output_dir=tmp_path / "reports",
        config=_config(),
        code_version="test-sha",
    )
    second = run_qmt_backtest_workflow(
        source,
        registry=registry,
        output_dir=tmp_path / "reports",
        config=_config(),
        code_version="test-sha",
        experiment_id=first.experiment_id,
    )

    assert (first.trial_number, second.trial_number) == (1, 2)
    assert registry.trial_count(first.experiment_id) == 2
    assert registry.artifact_count(first.trial_id) == 3
    assert json.loads(registry.trial_result(first.trial_id) or "{}")["status"] == "accepted"
    assert first.report.metrics.periods == 3
    assert first.report.metrics.total_cost > 0
    assert first.data_audit_path.exists()
    assert first.report.lineage.snapshot_id == first.snapshot_id


def test_rejected_qmt_attempt_remains_in_trial_ledger(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text(
        "time,stock_code,open,high,low,close,volume,amount\n"
        "20250102,000001.SZ,-1,1,1,1,1,1\n",
        encoding="utf-8",
    )
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")

    with pytest.raises(QmtDataError):
        run_qmt_backtest_workflow(
            source,
            registry=registry,
            output_dir=tmp_path / "reports",
            config=_config(),
            code_version="test-sha",
        )

    assert registry.counts()["trials"] == 1
    with registry.connect() as conn:
        result = conn.execute("SELECT result_json FROM trials").fetchone()[0]
    assert json.loads(result)["status"] == "rejected"


def test_qmt_cli_runs_the_complete_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "daily.csv"
    database = tmp_path / "registry.sqlite3"
    reports = tmp_path / "reports"
    _write_qmt_csv(source)
    dates = _trading_dates()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(database),
            "qmt-backtest",
            "--csv",
            str(source),
            "--output",
            str(reports),
            "--adjustment",
            "front_ratio",
            "--factor",
            "ret_5",
            "--train-start",
            "2023-01-01",
            "--train-end",
            "2023-12-31",
            "--validation-start",
            "2024-01-01",
            "--validation-end",
            "2024-12-31",
            "--test-start",
            dates[6].isoformat(),
            "--test-end",
            dates[8].isoformat(),
            "--adv-lookback",
            "3",
            "--top-k",
            "2",
            "--max-position-weight",
            "0.5",
            "--sell-tax-bps",
            "5",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["trial_number"] == 1
    assert payload["metrics"]["periods"] == 3
    assert Path(payload["data_audit_path"]).exists()
