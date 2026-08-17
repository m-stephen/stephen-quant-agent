from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import (
    DiscoveryExecutionConfig,
    ScreeningWindow,
    flow_stress_generation_plan,
    register_capacity_stress_trials,
    run_stability_diagnostics,
)
from stephen_quant.discovery.execution import _non_overlapping
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.automated_discovery import load_automated_discovery_config

NAVS = (1_000_000.0, 3_000_000.0, 5_000_000.0, 10_000_000.0, 20_000_000.0)
RATES = (0.01, 0.05, 0.10)


def _registry(tmp_path: Path) -> tuple[ExperimentRegistry, str]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.csv").write_text("fixture\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(source))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.19 fixture",
            hypothesis="fixed NAV capacity frontier",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    return registry, experiment_id


def _fixture_panel() -> tuple[tuple[QmtDailyBar, ...], tuple[BaselineObservation, ...]]:
    instruments = tuple(f"{index:06d}.SZ" for index in range(1, 10))
    days = [(date(2024, 1, 1) + timedelta(days=index)).isoformat() for index in range(45)]
    bars = tuple(
        QmtDailyBar(
            instrument,
            day,
            10.0 * (1.001 + instrument_index * 0.0001) ** day_index,
            11.0,
            9.0,
            10.0 * (1.001 + instrument_index * 0.0001) ** day_index,
            100_000.0,
            2_000_000.0 + instrument_index * 250_000.0,
        )
        for day_index, day in enumerate(days)
        for instrument_index, instrument in enumerate(instruments)
    )
    observations = tuple(
        BaselineObservation(
            instrument=instrument,
            signal=float(instrument_index),
            signal_at=f"{days[day_index - 1]}T15:00:00+08:00",
            signal_available_at=f"{days[day_index - 1]}T15:01:00+08:00",
            average_daily_value=2_000_000.0 + instrument_index * 250_000.0,
            liquidity_available_at=f"{days[day_index - 1]}T15:01:00+08:00",
            execution_at=f"{days[day_index]}T09:30:00+08:00",
            return_end_at=f"{days[day_index + 2]}T09:30:00+08:00",
            forward_return=instrument_index * 0.001,
        )
        for day_index in range(10, 40)
        for instrument_index, instrument in enumerate(instruments)
    )
    return bars, observations


def test_v1819_manifest_freezes_user_nav_ceiling() -> None:
    config = load_automated_discovery_config("configs/v1.8.19-capacity-frontier.json")

    assert config.initial_nav == 3_000_000.0
    assert config.capacity_reference_nav == 3_000_000.0
    assert config.capacity_stress_navs == NAVS
    assert max(config.capacity_stress_navs) == 20_000_000.0
    assert config.capacity_stress_rates == RATES


def test_execution_schedule_skips_cross_sections_below_frozen_top_k() -> None:
    _, observations = _fixture_panel()
    first_day = min(row.execution_at for row in observations)
    rows = tuple(
        BaselineObservation(**{**row.__dict__, "eligible": False})
        if row.execution_at == first_day
        else row
        for row in observations
    )

    selected = _non_overlapping(rows, horizon_sessions=2, minimum_eligible=5)

    assert first_day not in {row.execution_at for row in selected}
    assert all(
        sum(row.eligible for row in selected if row.execution_at == day) >= 5
        for day in {row.execution_at for row in selected}
    )


def test_nav_frontier_preregisters_15_trials_and_measures_reference_degradation(
    tmp_path: Path,
) -> None:
    registry, experiment_id = _registry(tmp_path)
    window = ScreeningWindow(
        "2024-01-01",
        "2024-12-31",
        "2025-01-01",
        "2025-12-31",
        "2026-01-01",
        "2026-12-31",
    )
    registrations = register_capacity_stress_trials(
        registry,
        experiment_id=experiment_id,
        window=window,
        initial_navs=NAVS,
        participation_rates=RATES,
        seed=42,
    )

    assert len(registrations) == 15
    assert registry.trial_count(experiment_id) == 15
    with registry.connect() as connection:
        payloads = [
            json.loads(
                connection.execute(
                    "SELECT hyperparams FROM trials WHERE trial_id = ?", (item.trial_id,)
                ).fetchone()[0]
            )
            for item in registrations
        ]
    assert {(item["initial_nav"], item["max_participation_rate"]) for item in payloads} == {
        (nav, rate) for nav in NAVS for rate in RATES
    }

    bars, observations = _fixture_panel()
    schema = flow_stress_generation_plan().templates[0].render(window=60, horizon="20d")
    report = run_stability_diagnostics(
        registry,
        schema=schema,
        rows=observations,
        bars=bars,
        registrations=registrations,
        snapshot_id="snap_fixture",
        experiment_id=experiment_id,
        code_version="test",
        horizon_sessions=2,
        regime_lookback=5,
        execution_config=DiscoveryExecutionConfig(
            top_k=2,
            initial_nav=3_000_000.0,
            placebo_repetitions=9,
        ),
        capacity_reference_nav=3_000_000.0,
    )

    assert len(report.capacity_stress) == 15
    assert report.capacity_reference_nav == 3_000_000.0
    references = [item for item in report.capacity_stress if item.initial_nav == 3_000_000.0]
    assert all(item.net_return_delta_vs_reference == pytest.approx(0.0) for item in references)
    low_rate = {
        item.initial_nav: item
        for item in report.capacity_stress
        if item.participation_rate == 0.01
    }
    assert low_rate[20_000_000.0].capacity_clipped_trade_ratio > low_rate[3_000_000.0].capacity_clipped_trade_ratio
    assert all(item.eligible_observations > 0 for item in report.capacity_stress)
    assert all(item.executed_orders > 0 for item in report.capacity_stress)
    assert all(registry.trial_result(item.trial_id) for item in registrations)
    assert report.validation_window_opened is False
    assert report.test_window_opened is False
