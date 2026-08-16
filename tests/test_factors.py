from __future__ import annotations

from datetime import date, timedelta

import pytest

from stephen_quant.factors import (
    SEED_FACTORS,
    FactorRegistry,
    FutureDataError,
    InsufficientHistoryError,
    MissingDataError,
    build_factor_catalog,
    build_seed_registry,
    compute_factor,
    write_factor_catalog,
)


def _dates(count: int) -> list[str]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _availability(fields: tuple[str, ...], timestamps: list[str]) -> dict[str, list[str]]:
    return {field: timestamps.copy() for field in fields}


def test_seed_registry_contains_versioned_factor_contracts() -> None:
    registry = build_seed_registry()

    assert len(registry.list()) == 25
    assert len({definition.key for definition in registry.list()}) == 25
    assert registry.get("ret_60").minimum_observations == 61
    assert all(definition.availability_lag_days == 0 for definition in registry.list())


def test_registry_rejects_duplicate_definition() -> None:
    definition = SEED_FACTORS[0]
    with pytest.raises(ValueError, match="already registered"):
        FactorRegistry((definition, definition))


def test_factor_catalog_marks_compatibility_and_frozen_status(tmp_path) -> None:
    catalog = build_factor_catalog()
    entries = {entry.definition.factor_id: entry for entry in catalog.entries}
    artifacts = write_factor_catalog(catalog, tmp_path)

    assert len(catalog.entries) == 25
    assert entries["ret_60"].research_status == "rejected_validation"
    assert entries["mom_120_skip_20"].research_status == "predeclared_unvalidated"
    assert entries["mom_120_skip_20"].qd_compatible
    assert entries["overnight_gap_reversal_20"].research_status == (
        "rejected_v1_8_14_signal_gate"
    )
    assert entries["close_location_20"].research_status == "rejected_v1_8_14_signal_gate"
    assert not entries["rs_index_60"].qd_compatible
    assert artifacts.json_sha256
    assert artifacts.markdown_sha256
    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()


def test_return_factor_is_deterministic_and_correct() -> None:
    timestamps = _dates(61)
    close = [100.0 + index for index in range(61)]
    definition = build_seed_registry().get("ret_60")

    first = compute_factor(
        definition,
        {"close": close},
        _availability(("close",), timestamps),
        as_of_index=60,
        observation_times=timestamps,
        decision_at=timestamps[-1],
    )
    second = compute_factor(
        definition,
        {"close": close},
        _availability(("close",), timestamps),
        as_of_index=60,
        observation_times=timestamps,
        decision_at=timestamps[-1],
    )

    assert first == second
    assert first.value == pytest.approx(0.6)


def test_relative_strength_subtracts_benchmark_return() -> None:
    timestamps = _dates(61)
    definition = build_seed_registry().get("rs_index_60")
    value = compute_factor(
        definition,
        {
            "close": [100.0 + index for index in range(61)],
            "benchmark_close": [100.0 + index / 2 for index in range(61)],
        },
        _availability(definition.required_fields, timestamps),
        as_of_index=60,
        observation_times=timestamps,
        decision_at=timestamps[-1],
    )

    assert value.value == pytest.approx(0.3)


def test_new_factor_family_has_predeclared_deterministic_formulas() -> None:
    count = 121
    timestamps = _dates(count)
    close = [100.0 + index for index in range(count)]
    fields = {
        "open": [value - 0.5 for value in close],
        "high": [value + 1.0 for value in close],
        "low": [value - 1.0 for value in close],
        "close": close,
        "volume": [1_000.0 + index * 10 for index in range(count)],
        "amount": [1_000_000.0 + index * 1_000 for index in range(count)],
    }
    registry = build_seed_registry()
    factor_ids = (
        "mom_120_skip_20",
        "trend_efficiency_20",
        "range_position_20",
        "intraday_strength_20",
        "volume_surprise_5_20",
        "signed_volume_mom_20",
        "dollar_liquidity_20",
        "parkinson_vol_20",
    )

    results = {
        factor_id: compute_factor(
            registry.get(factor_id),
            fields,
            _availability(tuple(fields), timestamps),
            as_of_index=count - 1,
            observation_times=timestamps,
            decision_at=timestamps[-1],
        ).value
        for factor_id in factor_ids
    }

    assert results["mom_120_skip_20"] == pytest.approx(1.0)
    assert results["trend_efficiency_20"] == pytest.approx(1.0)
    assert 0 <= results["range_position_20"] <= 1
    assert results["intraday_strength_20"] > 0
    assert results["volume_surprise_5_20"] > 0
    assert results["signed_volume_mom_20"] > 0
    assert results["dollar_liquidity_20"] > 0
    assert results["parkinson_vol_20"] > 0


def test_v1_8_14_microstructure_factors_are_predeclared_and_deterministic() -> None:
    count = 21
    timestamps = _dates(count)
    close = [100.0 + index for index in range(count)]
    opening = [close[0]] + [close[index - 1] * 1.01 for index in range(1, count)]
    fields = {
        "open": opening,
        "high": [value + 2.0 for value in close],
        "low": [value - 1.0 for value in close],
        "close": close,
    }
    registry = build_seed_registry()

    gap = compute_factor(
        registry.get("overnight_gap_reversal_20"),
        fields,
        _availability(tuple(fields), timestamps),
        as_of_index=count - 1,
        observation_times=timestamps,
        decision_at=timestamps[-1],
    )
    location = compute_factor(
        registry.get("close_location_20"),
        fields,
        _availability(tuple(fields), timestamps),
        as_of_index=count - 1,
        observation_times=timestamps,
        decision_at=timestamps[-1],
    )

    assert gap.value == pytest.approx(0.01)
    assert location.value == pytest.approx(-1 / 3)
    assert registry.get("overnight_gap_reversal_20").direction == -1
    assert registry.get("close_location_20").direction == 1


def test_future_available_input_is_rejected() -> None:
    timestamps = _dates(21)
    definition = build_seed_registry().get("ret_20")
    availability = _availability(("close",), timestamps)
    availability["close"][-1] = "2026-12-31"

    with pytest.raises(FutureDataError, match="unavailable"):
        compute_factor(
            definition,
            {"close": list(range(100, 121))},
            availability,
            as_of_index=20,
            observation_times=timestamps,
            decision_at=timestamps[-1],
        )


def test_insufficient_history_and_missing_values_fail_explicitly() -> None:
    timestamps = _dates(20)
    definition = build_seed_registry().get("ret_20")

    with pytest.raises(InsufficientHistoryError):
        compute_factor(
            definition,
            {"close": list(range(100, 120))},
            _availability(("close",), timestamps),
            as_of_index=19,
            observation_times=timestamps,
            decision_at=timestamps[-1],
        )

    timestamps = _dates(21)
    close: list[float | None] = [float(value) for value in range(100, 121)]
    close[10] = None
    with pytest.raises(MissingDataError, match="missing"):
        compute_factor(
            definition,
            {"close": close},
            _availability(("close",), timestamps),
            as_of_index=20,
            observation_times=timestamps,
            decision_at=timestamps[-1],
        )


def test_all_seed_formulas_compute_on_valid_inputs() -> None:
    count = 121
    timestamps = _dates(count)
    fields = {
        "close": [100.0 + index * 0.2 for index in range(count)],
        "open": [99.8 + index * 0.2 for index in range(count)],
        "benchmark_close": [100.0 + index * 0.1 for index in range(count)],
        "high": [101.0 + index * 0.2 for index in range(count)],
        "low": [99.0 + index * 0.2 for index in range(count)],
        "volume": [1_000.0 + index for index in range(count)],
        "turnover": [0.01 + index / 100_000 for index in range(count)],
        "amount": [1_000_000.0 + index * 100 for index in range(count)],
    }
    availability = _availability(tuple(fields), timestamps)

    results = [
        compute_factor(
            definition,
            fields,
            availability,
            as_of_index=count - 1,
            observation_times=timestamps,
            decision_at=timestamps[-1],
        )
        for definition in SEED_FACTORS
    ]

    assert len(results) == 25
    assert all(result.as_of == timestamps[-1] for result in results)
