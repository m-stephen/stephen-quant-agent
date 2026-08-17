from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import normalized_generation_plan
from stephen_quant.factors import FactorDefinition
from stephen_quant.qmt import (
    AlternativeObservation,
    QmtDailyBar,
    build_multisource_factor_observations,
    normalize_cross_sectional_observations,
)


def _bar(day: str, amount: float) -> QmtDailyBar:
    return QmtDailyBar("000001.SZ", day, 10.0, 11.0, 9.0, 10.0, 100.0, amount)


def _flow(day: str, value: float, available_clock: str = "18:00:00") -> AlternativeObservation:
    return AlternativeObservation(
        source_kind="fund_flow",
        instrument="000001.SZ",
        name="fixture",
        trade_date=day,
        effective_at=f"{day}T15:00:00+08:00",
        available_at=f"{day}T{available_clock}+08:00",
        ingested_at="2025-01-01T00:00:00+08:00",
        values=(("net_inflow_amount", value),),
    )


def _anchor() -> BaselineObservation:
    return BaselineObservation(
        instrument="000001.SZ",
        signal=0.0,
        signal_at="2024-01-03T15:00:00+08:00",
        signal_available_at="2024-01-03T15:01:00+08:00",
        average_daily_value=250.0,
        liquidity_available_at="2024-01-03T15:01:00+08:00",
        execution_at="2024-01-04T09:30:00+08:00",
        return_end_at="2024-01-05T09:30:00+08:00",
        forward_return=0.01,
    )


def _definition() -> FactorDefinition:
    return FactorDefinition(
        factor_id="fund_flow_intensity_2_5d",
        version="1.0.0",
        name="flow intensity",
        category="fund_flow",
        formula="mean(net_inflow_amount, 2) / (mean(amount, 2) + 1.0)",
        required_fields=("amount", "net_inflow_amount"),
        lookback_periods=2,
        minimum_observations=2,
        availability_lag_days=0,
        direction=1,
        description="fixture",
    )


def test_normalized_plan_contains_valid_multisource_families() -> None:
    plan = normalized_generation_plan()
    schemas = [template.render(window=5, horizon="5d") for template in plan.templates]

    assert any(len(schema.data_sources) > 1 for schema in schemas)
    assert {"fund_flow_intensity", "margin_buy_intensity", "auction_amount_intensity"} <= {
        template.template_id for template in plan.templates
    }
    assert all(schema.fingerprint for schema in schemas)


def test_multisource_builder_scales_flow_by_prior_daily_amount() -> None:
    bars = tuple(
        _bar(day, amount)
        for day, amount in (
            ("2024-01-01", 100.0),
            ("2024-01-02", 200.0),
            ("2024-01-03", 300.0),
            ("2024-01-04", 400.0),
            ("2024-01-05", 500.0),
        )
    )
    flows = tuple(
        _flow(day, value)
        for day, value in (
            ("2024-01-01", 10.0),
            ("2024-01-02", 20.0),
            ("2024-01-03", 30.0),
        )
    )

    rows = build_multisource_factor_observations(
        bars, {"qd_fund_flow": flows}, _definition(), (_anchor(),)
    )

    assert rows[0].eligible is True
    assert rows[0].signal == pytest.approx(25.0 / 251.0)
    assert rows[0].signal_available_at == "2024-01-03T18:00:00+08:00"


def test_multisource_builder_rejects_stale_or_future_source_without_leakage() -> None:
    bars = tuple(_bar(f"2024-01-0{day}", day * 100.0) for day in range(1, 6))
    flows = (
        _flow("2024-01-01", 10.0),
        _flow("2024-01-02", 20.0),
        replace(_flow("2024-01-03", 30.0), available_at="2024-01-04T10:00:00+08:00"),
    )

    rows = build_multisource_factor_observations(
        bars, {"qd_fund_flow": flows}, _definition(), (_anchor(),)
    )

    assert rows[0].eligible is False
    assert rows[0].signal == 0.0


def test_cross_sectional_normalization_is_centered_and_bounded() -> None:
    rows = tuple(
        replace(
            _anchor(),
            instrument=f"00000{index}.SZ",
            signal=signal,
        )
        for index, signal in enumerate((0.0, 1.0, 100.0), start=1)
    )

    normalized = normalize_cross_sectional_observations(rows, winsor_fraction=0.25)
    signals = [row.signal for row in normalized]

    assert sum(signals) == pytest.approx(0.0)
    assert sum(value**2 for value in signals) / len(signals) == pytest.approx(1.0)
    assert signals == sorted(signals)
