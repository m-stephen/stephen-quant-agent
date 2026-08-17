from __future__ import annotations

import math
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import (
    AttributionThresholds,
    ScreeningWindow,
    flow_stress_generation_plan,
    register_attribution_trial,
    run_factor_attribution,
)
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.workflows.automated_discovery import load_automated_discovery_config


def _registry(tmp_path: Path) -> tuple[ExperimentRegistry, str]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.csv").write_text("fixture\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(source))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.20 fixture",
            hypothesis="incremental attribution fixture",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    return registry, experiment_id


def _schemas():
    schemas = [
        template.render(window=60, horizon="20d")
        for template in flow_stress_generation_plan().templates
    ]
    target = next(item for item in schemas if item.schema_id.startswith("flow_price_divergence"))
    control = next(item for item in schemas if item.schema_id.startswith("price_reversal_control"))
    return target, control


def _panels() -> tuple[tuple[BaselineObservation, ...], tuple[BaselineObservation, ...]]:
    targets = []
    controls = []
    start = date(2024, 1, 2)
    for day_index in range(12):
        execution = start + timedelta(days=day_index * 3)
        signal_day = execution - timedelta(days=1)
        return_end = execution + timedelta(days=2)
        for instrument_index in range(20):
            instrument = f"{instrument_index + 1:06d}.SZ"
            control = float(instrument_index - 10)
            incremental = math.sin(instrument_index * 1.7) + day_index * 0.001
            forward_return = incremental * 0.01
            common = {
                "instrument": instrument,
                "signal_at": f"{signal_day.isoformat()}T15:00:00+08:00",
                "signal_available_at": f"{signal_day.isoformat()}T15:01:00+08:00",
                "average_daily_value": 1_000_000.0 + instrument_index**2 * 100_000.0,
                "liquidity_available_at": f"{signal_day.isoformat()}T15:01:00+08:00",
                "execution_at": f"{execution.isoformat()}T09:30:00+08:00",
                "return_end_at": f"{return_end.isoformat()}T09:30:00+08:00",
                "forward_return": forward_return,
            }
            targets.append(BaselineObservation(signal=2 * control + incremental, **common))
            controls.append(BaselineObservation(signal=-control, **common))
    return tuple(targets), tuple(controls)


def test_v1820_manifest_freezes_diagnostics_without_capacity_research() -> None:
    config = load_automated_discovery_config("configs/v1.8.20-factor-attribution.json")

    assert config.search_profile == "v1.8.20"
    assert config.initial_nav == 3_000_000.0
    assert config.capacity_stress_rates == ()
    assert config.attribution_minimum_residual_rank_ic == 0.02
    assert config.attribution_minimum_execution_sharpe == 0.50


def test_attribution_residualizes_controls_and_records_stop_reason(tmp_path: Path) -> None:
    registry, experiment_id = _registry(tmp_path)
    target_schema, control_schema = _schemas()
    target_rows, control_rows = _panels()
    window = ScreeningWindow(
        "2024-01-01",
        "2024-12-31",
        "2025-01-01",
        "2025-12-31",
        "2026-01-01",
        "2026-12-31",
    )
    thresholds = AttributionThresholds()
    registration = register_attribution_trial(
        registry,
        experiment_id=experiment_id,
        window=window,
        target=target_schema,
        controls=(control_schema,),
        thresholds=thresholds,
        seed=42,
    )

    report = run_factor_attribution(
        registry,
        registration=registration,
        target_schema=target_schema,
        target_rows=target_rows,
        controls=((control_schema, control_rows),),
        thresholds=thresholds,
        execution_net_return=0.03,
        execution_sharpe=0.18,
        execution_max_drawdown=-0.38,
    )

    assert report.residual_rank_ic > 0.95
    assert len(report.quantile_returns) == 10
    assert report.observations == 240
    assert "LOW_EXECUTION_SHARPE" in report.failure_labels
    assert "EXCESSIVE_DRAWDOWN" in report.failure_labels
    assert report.recommendation == "STOP_OR_REDESIGN"
    assert report.validation_window_opened is False
    assert report.test_window_opened is False
    assert registry.trial_count(experiment_id) == 1
    assert registry.trial_result(registration.trial_id)


def test_attribution_fails_closed_when_control_panel_is_missing(tmp_path: Path) -> None:
    registry, experiment_id = _registry(tmp_path)
    target_schema, control_schema = _schemas()
    target_rows, control_rows = _panels()
    window = ScreeningWindow(
        "2024-01-01",
        "2024-12-31",
        "2025-01-01",
        "2025-12-31",
        "2026-01-01",
        "2026-12-31",
    )
    registration = register_attribution_trial(
        registry,
        experiment_id=experiment_id,
        window=window,
        target=target_schema,
        controls=(control_schema,),
        thresholds=AttributionThresholds(),
        seed=42,
    )

    with pytest.raises(ValueError, match="missing 1 target observations"):
        run_factor_attribution(
            registry,
            registration=registration,
            target_schema=target_schema,
            target_rows=target_rows,
            controls=((control_schema, control_rows[:-1]),),
            thresholds=AttributionThresholds(),
            execution_net_return=0.0,
            execution_sharpe=0.0,
            execution_max_drawdown=0.0,
        )


def test_attribution_fails_closed_on_decision_time_leakage(tmp_path: Path) -> None:
    registry, experiment_id = _registry(tmp_path)
    target_schema, control_schema = _schemas()
    target_rows, control_rows = _panels()
    window = ScreeningWindow(
        "2024-01-01",
        "2024-12-31",
        "2025-01-01",
        "2025-12-31",
        "2026-01-01",
        "2026-12-31",
    )
    registration = register_attribution_trial(
        registry,
        experiment_id=experiment_id,
        window=window,
        target=target_schema,
        controls=(control_schema,),
        thresholds=AttributionThresholds(),
        seed=42,
    )
    leaked = (
        replace(control_rows[0], signal_available_at=control_rows[0].execution_at),
        *control_rows[1:],
    )

    with pytest.raises(ValueError, match="not point-in-time visible"):
        run_factor_attribution(
            registry,
            registration=registration,
            target_schema=target_schema,
            target_rows=target_rows,
            controls=((control_schema, leaked),),
            thresholds=AttributionThresholds(),
            execution_net_return=0.0,
            execution_sharpe=0.0,
            execution_max_drawdown=0.0,
        )
