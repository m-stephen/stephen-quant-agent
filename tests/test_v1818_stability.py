from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import (
    DiscoveryExecutionConfig,
    FactorSchema,
    ScreeningWindow,
    flow_stress_generation_plan,
    point_in_time_industry_groups,
    register_capacity_stress_trials,
    run_stability_diagnostics,
)
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.qmt import PointInTimeMembership, QmtDailyBar, QmtDataError


def _schema() -> FactorSchema:
    return flow_stress_generation_plan().templates[0].render(window=60, horizon="20d")


def test_flow_stress_plan_is_bounded_and_deterministic() -> None:
    plan = flow_stress_generation_plan()
    schemas = [template.render(window=60, horizon="20d") for template in plan.templates]

    assert len(schemas) == 8
    assert len({schema.fingerprint for schema in schemas}) == 8
    assert all(schema.horizon == "20d" for schema in schemas)
    assert any("surprise" in schema.schema_id for schema in schemas)


def test_point_in_time_industry_mapping_fails_closed() -> None:
    rows = (
        PointInTimeMembership(
            "industry",
            "2024-01-01T00:00:00+08:00",
            "2024-01-02T18:00:00+08:00",
            "2026-01-01T00:00:00+08:00",
            "000001.SZ",
            "bank",
            "Bank",
        ),
        PointInTimeMembership(
            "industry",
            "2024-01-01T00:00:00+08:00",
            "2024-01-02T18:00:00+08:00",
            "2026-01-01T00:00:00+08:00",
            "000002.SZ",
            "property",
            "Property",
        ),
        PointInTimeMembership(
            "industry",
            "2024-02-01T00:00:00+08:00",
            "2024-02-01T18:00:00+08:00",
            "2026-01-01T00:00:00+08:00",
            "000001.SZ",
            "finance",
            "Finance",
        ),
    )

    groups = point_in_time_industry_groups(
        rows,
        instruments=("000001.SZ", "000002.SZ"),
        decision_at="2024-01-10T09:30:00+08:00",
    )
    assert groups == {"000001.SZ": "bank", "000002.SZ": "property"}

    with pytest.raises(QmtDataError, match="incomplete or ambiguous"):
        point_in_time_industry_groups(
            rows,
            instruments=("000001.SZ", "000002.SZ", "600000.SH"),
            decision_at="2024-01-10T09:30:00+08:00",
        )


def _registry(tmp_path: Path) -> tuple[ExperimentRegistry, str]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "fixture.csv").write_text("fixture\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(source))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.18 fixture",
            hypothesis="flow stability fixture",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    return registry, experiment_id


def test_stability_diagnostics_registers_capacity_trials_and_uses_prior_regimes(
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
        participation_rates=(0.01, 0.05, 0.10),
        seed=42,
    )
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
            1_000_000.0,
            50_000_000.0 + instrument_index * 10_000_000.0,
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
            average_daily_value=50_000_000.0 + instrument_index * 10_000_000.0,
            liquidity_available_at=f"{days[day_index - 1]}T15:01:00+08:00",
            execution_at=f"{days[day_index]}T09:30:00+08:00",
            return_end_at=f"{days[day_index + 2]}T09:30:00+08:00",
            forward_return=instrument_index * 0.001,
        )
        for day_index in range(10, 40)
        for instrument_index, instrument in enumerate(instruments)
    )

    report = run_stability_diagnostics(
        registry,
        schema=_schema(),
        rows=observations,
        bars=bars,
        registrations=registrations,
        snapshot_id="snap_fixture",
        experiment_id=experiment_id,
        code_version="test",
        horizon_sessions=2,
        regime_lookback=5,
        execution_config=DiscoveryExecutionConfig(top_k=2, placebo_repetitions=9),
    )

    assert len(report.capacity_stress) == 3
    assert {item.slice_name for item in report.adv_terciles} == {
        "low_adv",
        "mid_adv",
        "high_adv",
    }
    assert all(item.mean_rank_ic == pytest.approx(1.0) for item in report.adv_terciles)
    assert report.validation_window_opened is False
    assert report.test_window_opened is False
    assert registry.trial_count(experiment_id) == 3
    assert all(registry.trial_result(item.trial_id) for item in registrations)
