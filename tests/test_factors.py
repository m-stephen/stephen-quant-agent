from __future__ import annotations

from datetime import date, timedelta

import pytest

from stephen_quant.factors import (
    SEED_FACTORS,
    FactorRegistry,
    FutureDataError,
    InsufficientHistoryError,
    MissingDataError,
    build_seed_registry,
    compute_factor,
)


def _dates(count: int) -> list[str]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _availability(fields: tuple[str, ...], timestamps: list[str]) -> dict[str, list[str]]:
    return {field: timestamps.copy() for field in fields}


def test_seed_registry_contains_versioned_factor_contracts() -> None:
    registry = build_seed_registry()

    assert len(registry.list()) == 15
    assert len({definition.key for definition in registry.list()}) == 15
    assert registry.get("ret_60").minimum_observations == 61
    assert all(definition.availability_lag_days == 0 for definition in registry.list())


def test_registry_rejects_duplicate_definition() -> None:
    definition = SEED_FACTORS[0]
    with pytest.raises(ValueError, match="already registered"):
        FactorRegistry((definition, definition))


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

    assert len(results) == 15
    assert all(result.as_of == timestamps[-1] for result in results)
