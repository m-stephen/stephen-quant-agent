from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.v41_semantic_alpha import (
    UsageSpec,
    V41Config,
    _percentiles,
    classify_prior_regimes,
    economic_shape,
    evaluate_usage,
    generate_v41_candidates,
)


def _row(day: str, instrument: str, signal: float, forward: float) -> EvaluationObservation:
    return EvaluationObservation(
        timestamp=f"{day}T09:30:00+08:00",
        instrument=instrument,
        factor_value=signal,
        factor_available_at=f"{day}T09:29:00+08:00",
        label_start_at=f"{day}T09:30:00+08:00",
        label_end_at=f"{day}T15:00:00+08:00",
        forward_return=forward,
        horizon="1d",
        subperiod="synthetic",
        regime="synthetic",
    )


def _bar(instrument: str, day: str, close: float, amount: float = 1_000_000_000) -> QmtDailyBar:
    return QmtDailyBar(
        instrument,
        day,
        close,
        close * 1.01,
        close * 0.99,
        close,
        10_000_000,
        amount,
    )


def test_v41_semantic_grammar_is_frozen_unique_and_unassigned() -> None:
    candidates = generate_v41_candidates()

    assert len(candidates) == 288
    assert len({item.candidate_id for item in candidates}) == 288
    assert len({item.fingerprint for item in candidates}) == 288
    assert {item.output for item in candidates} == {"UNASSIGNED"}
    assert {item.direction for item in candidates} == {-1, 1}
    assert {item.source_kind for item in candidates} == {
        "daily",
        "auction",
        "fund_flow",
        "margin",
        "limit_event",
    }


def test_v41_windows_and_usage_identities_are_not_tunable() -> None:
    with pytest.raises(ValueError, match="windows are frozen"):
        replace(V41Config(), shadow_year=2025).validate()
    with pytest.raises(ValueError, match="usage identities are frozen"):
        replace(V41Config(), usages=("BUY",)).validate()


def test_tie_aware_percentiles_do_not_create_identity_based_edge() -> None:
    assert _percentiles({"a": 1.0, "b": 1.0, "c": 2.0}) == {
        "a": 0.0,
        "b": 0.0,
        "c": 1.0,
    }


def test_shape_flags_positive_ic_with_negative_long_leg() -> None:
    returns = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 100.0, 8.0)
    rows = tuple(
        _row("2022-01-04", f"S{index:02d}", float(index), value)
        for index, value in enumerate(returns)
    )

    shape = economic_shape("synthetic", rows, year=2022, regimes={})

    assert shape.rank_ic is not None and shape.rank_ic > 0
    assert shape.top_excess_return is not None and shape.top_excess_return < 0
    assert shape.positive_ic_negative_long_leg
    assert shape.regimes[0].dates == 1


def test_regime_for_decision_day_uses_prior_sessions_only() -> None:
    calendar = tuple((date(2022, 1, 1) + timedelta(days=index)).isoformat() for index in range(30))
    instruments = tuple(f"S{index:02d}" for index in range(12))
    members = {day: instruments for day in calendar}
    bars = {
        instrument: {
            day: _bar(
                instrument,
                day,
                10.0 * (1 + 0.001 * (index + 1)) ** position,
                1_000_000_000 + position * 1_000_000,
            )
            for position, day in enumerate(calendar)
        }
        for index, instrument in enumerate(instruments)
    }
    config = V41Config()
    original = classify_prior_regimes(
        calendar=calendar, bars=bars, execution_members=members, config=config
    )
    decision_day = calendar[-1]
    mutated = {instrument: dict(series) for instrument, series in bars.items()}
    for instrument in instruments:
        mutated[instrument][decision_day] = _bar(instrument, decision_day, 1_000_000.0, 1.0)
    changed = classify_prior_regimes(
        calendar=calendar, bars=mutated, execution_members=members, config=config
    )

    assert original[decision_day] == changed[decision_day]
    assert original[decision_day].information_end_date == calendar[-2]


def test_avoid_mapping_can_convert_bottom_tail_better_than_buy_mapping() -> None:
    calendar = ("2022-12-30", "2023-01-03")
    instruments = tuple(f"S{index:02d}" for index in range(10))
    forwards = (-0.20, -0.20, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.0, 0.0)
    rows = tuple(
        _row(calendar[1], instrument, float(index), forwards[index])
        for index, instrument in enumerate(instruments)
    )
    bars = {
        instrument: {day: _bar(instrument, day, 10.0) for day in calendar}
        for instrument in instruments
    }
    config = replace(
        V41Config(),
        commission_bps=0.0,
        sell_tax_bps=0.0,
        slippage_bps=0.0,
        impact_bps=0.0,
    )
    buy, _ = evaluate_usage(
        "synthetic",
        rows,
        rows,
        UsageSpec("BUY", 2, "all"),
        year=2023,
        horizon=1,
        nav=3_000_000,
        bars=bars,
        calendar=calendar,
        regimes={},
        config=config,
    )
    avoid, _ = evaluate_usage(
        "synthetic",
        rows,
        rows,
        UsageSpec("AVOID", 2, "all"),
        year=2023,
        horizon=1,
        nav=3_000_000,
        bars=bars,
        calendar=calendar,
        regimes={},
        config=config,
    )

    assert avoid.cumulative_excess_return > buy.cumulative_excess_return
