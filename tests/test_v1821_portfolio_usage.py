from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import (
    ScreeningWindow,
    flow_stress_generation_plan,
    frozen_portfolio_usage_config,
    register_portfolio_usage_trials,
    run_portfolio_usage,
)
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.workflows.automated_discovery import load_automated_discovery_config


def _registry(tmp_path: Path) -> tuple[ExperimentRegistry, str, str]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    (source / "fixture.csv").write_text("frozen fixture\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(source))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.21 portfolio usage fixture",
            hypothesis="preregistered avoidance mappings can be compared without sealed data",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    return registry, snapshot_id, experiment_id


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
    start = date(2023, 1, 2)
    for day_index in range(121):
        execution = start + timedelta(days=day_index)
        signal_day = execution - timedelta(days=1)
        return_end = execution + timedelta(days=19)
        regime = -1.0 if day_index % 3 == 0 else 1.0
        for instrument_index in range(40):
            instrument = f"{instrument_index + 1:06d}.SZ"
            control = float(instrument_index - 20)
            incremental = math.sin(instrument_index * 1.37 + day_index * 0.11)
            forward_return = 0.003 * regime + incremental * 0.006
            common = {
                "instrument": instrument,
                "signal_at": f"{signal_day.isoformat()}T15:00:00+08:00",
                "signal_available_at": f"{signal_day.isoformat()}T15:01:00+08:00",
                "average_daily_value": 5_000_000.0 + instrument_index**2 * 50_000.0,
                "liquidity_available_at": f"{signal_day.isoformat()}T15:01:00+08:00",
                "execution_at": f"{execution.isoformat()}T09:30:00+08:00",
                "return_end_at": f"{return_end.isoformat()}T09:30:00+08:00",
                "forward_return": forward_return,
            }
            targets.append(BaselineObservation(signal=2 * control + incremental, **common))
            controls.append(BaselineObservation(signal=control, **common))
    return tuple(targets), tuple(controls)


def _window() -> ScreeningWindow:
    return ScreeningWindow(
        "2022-01-04",
        "2024-12-31",
        "2025-01-03",
        "2025-12-31",
        "2026-01-05",
        "2026-08-14",
    )


def test_v1821_manifest_matches_frozen_contract() -> None:
    raw = json.loads(Path("configs/v1.8.21-portfolio-usage.json").read_text(encoding="utf-8"))
    config = frozen_portfolio_usage_config()

    assert raw["research_only"] is True
    assert tuple(raw["initial_navs"]) == tuple(int(item) for item in config.initial_navs)
    assert raw["reference_nav"] == config.reference_nav == 3_000_000.0
    assert raw["reference_mapping"] == config.reference_mapping == "exclude_bottom_decile"
    assert raw["benchmark_mapping"] == config.benchmark_mapping == "all_eligible_benchmark"
    assert [item["name"] for item in raw["mappings"]] == [
        item.name for item in config.mappings
    ]
    assert len(config.manifest_sha256) == 64
    search = load_automated_discovery_config("configs/v1.8.21-search.json")
    assert search.search_profile == "v1.8.21"
    assert search.research_end == "2024-12-31"
    assert search.validation_start == "2025-01-03"
    assert search.initial_nav == 3_000_000.0


def test_portfolio_usage_registers_every_mapping_and_nav_as_trial(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    target, control = _schemas()
    target_rows, control_rows = _panels()
    config = frozen_portfolio_usage_config()
    registrations = register_portfolio_usage_trials(
        registry,
        experiment_id=experiment_id,
        window=_window(),
        target=target,
        config=config,
        seed=42,
    )

    report = run_portfolio_usage(
        registry,
        registrations=registrations,
        target_schema=target,
        target_rows=target_rows,
        control_schemas=(control,),
        control_rows=(control_rows,),
        snapshot_id=snapshot_id,
        experiment_id=experiment_id,
        code_version="test",
        config=config,
    )

    assert len(registrations) == len(config.mappings) * len(config.initial_navs) == 30
    assert registry.trial_count(experiment_id) == 30
    assert len(report.scores) == 30
    assert all(registry.trial_result(item.trial_id) for item in registrations)
    assert report.research_only is True
    assert report.validation_window_opened is False
    assert report.test_window_opened is False
    assert report.reference_portfolio.mapping_name == "exclude_bottom_decile"
    assert report.reference_portfolio.initial_nav == 3_000_000.0
    benchmark = next(
        item
        for item in report.scores
        if item.mapping_name == "all_eligible_benchmark" and item.initial_nav == 3_000_000.0
    )
    assert benchmark.incremental_net_return == 0.0
    assert benchmark.incremental_net_sharpe == 0.0
    assert "不构成新的样本外证据" in report.to_markdown("zh")
    assert "not fresh out-of-sample evidence" in report.to_markdown("en")


def test_portfolio_usage_is_deterministic_for_same_frozen_manifest(tmp_path: Path) -> None:
    target, control = _schemas()
    target_rows, control_rows = _panels()
    config = frozen_portfolio_usage_config()
    metric_sets = []
    for name in ("first", "second"):
        registry, snapshot_id, experiment_id = _registry(tmp_path / name)
        registrations = register_portfolio_usage_trials(
            registry,
            experiment_id=experiment_id,
            window=_window(),
            target=target,
            config=config,
            seed=42,
        )
        report = run_portfolio_usage(
            registry,
            registrations=registrations,
            target_schema=target,
            target_rows=target_rows,
            control_schemas=(control,),
            control_rows=(control_rows,),
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            code_version="test",
            config=config,
        )
        metric_sets.append(
            tuple(
                (
                    item.mapping_name,
                    item.initial_nav,
                    item.net_total_return,
                    item.annualized_net_sharpe,
                    item.max_drawdown,
                    item.total_turnover,
                    item.total_cost,
                )
                for item in report.scores
            )
        )
    assert metric_sets[0] == metric_sets[1]


def test_portfolio_usage_fails_closed_on_decision_time_leakage(tmp_path: Path) -> None:
    registry, snapshot_id, experiment_id = _registry(tmp_path)
    target, control = _schemas()
    target_rows, control_rows = _panels()
    config = frozen_portfolio_usage_config()
    registrations = register_portfolio_usage_trials(
        registry,
        experiment_id=experiment_id,
        window=_window(),
        target=target,
        config=config,
        seed=42,
    )
    leaked = (replace(target_rows[0], signal_available_at=target_rows[0].execution_at), *target_rows[1:])

    with pytest.raises(ValueError, match="not point-in-time visible"):
        run_portfolio_usage(
            registry,
            registrations=registrations,
            target_schema=target,
            target_rows=leaked,
            control_schemas=(control,),
            control_rows=(control_rows,),
            snapshot_id=snapshot_id,
            experiment_id=experiment_id,
            code_version="test",
            config=config,
        )
