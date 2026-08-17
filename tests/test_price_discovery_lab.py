from __future__ import annotations

from datetime import date, timedelta

import pytest

from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.price_discovery_lab import (
    _cpcv,
    _panel,
    _signal,
    generate_price_candidates,
)


def _bar(instrument: str, day: str, value: float) -> QmtDailyBar:
    return QmtDailyBar(
        instrument=instrument,
        trade_date=day,
        open=value,
        high=value * 1.01,
        low=value * 0.99,
        close=value,
        volume=1_000_000 + value * 10,
        amount=10_000_000 + value * 100,
    )


def test_price_grammar_is_frozen_unique_and_bidirectional() -> None:
    candidates = generate_price_candidates()

    assert len(candidates) == 630
    assert len({item.fingerprint for item in candidates}) == 630
    assert {item.lookback for item in candidates if item.family == "ohlc_return"} == {
        2,
        3,
        5,
        10,
        20,
        40,
        60,
        120,
        240,
    }
    assert {item.horizon for item in candidates} == {1, 3, 5, 10, 20}
    identities = {
        (item.family, item.field, item.lookback, item.horizon): set()
        for item in candidates
    }
    for item in candidates:
        identities[(item.family, item.field, item.lookback, item.horizon)].add(item.direction)
    assert all(signs == {-1, 1} for signs in identities.values())


def test_signal_uses_only_supplied_history_and_respects_direction_outside_formula() -> None:
    candidate = next(
        item
        for item in generate_price_candidates()
        if item.family == "ohlc_return"
        and item.field == "close"
        and item.lookback == 5
        and item.horizon == 1
        and item.direction == 1
    )
    history = [_bar("A", f"2021-12-{day:02d}", float(day)) for day in range(1, 7)]

    assert _signal(candidate, history) == pytest.approx(5.0)
    assert _signal(candidate, history[:-1]) is None


def test_panel_uses_previous_close_information_and_open_to_open_label() -> None:
    candidates = generate_price_candidates()
    candidate = next(
        item
        for item in candidates
        if item.family == "ohlc_return"
        and item.field == "close"
        and item.lookback == 2
        and item.horizon == 1
        and item.direction == 1
    )
    start = date(2021, 12, 28)
    calendar = tuple((start + timedelta(days=offset)).isoformat() for offset in range(10))
    instruments = tuple(f"S{offset}" for offset in range(10))
    bars = {
        instrument: {
            day: _bar(instrument, day, 10 + index + instrument_index)
            for index, day in enumerate(calendar)
        }
        for instrument_index, instrument in enumerate(instruments)
    }
    memberships = {day: instruments for day in calendar}

    rows, metrics = _panel(
        candidate,
        year=2022,
        calendar=calendar,
        bars=bars,
        execution_members=memberships,
        minimum_cross_section=10,
    )

    assert metrics
    assert rows
    assert all(row.factor_available_at[:10] < row.label_start_at[:10] for row in rows)
    assert all(row.label_start_at[:10] < row.label_end_at[:10] for row in rows)


def test_cpcv_supports_a_single_survivor_with_pbo_not_applicable() -> None:
    candidate = generate_price_candidates()[0]
    metric_type = __import__(
        "stephen_quant.workflows.price_discovery_lab", fromlist=["_DailyMetric"]
    )._DailyMetric
    daily = tuple(
        metric_type(
            day=(date(2022, 1, 1) + timedelta(days=offset)).isoformat(),
            rank_ic=0.01 + offset / 100_000,
            top_bottom=0.001,
            top_excess=0.0005,
            observations=20,
        )
        for offset in range(180)
    )

    result = _cpcv((candidate,), {candidate.fingerprint: daily}, groups=6, test_groups=3)

    assert result.configurations == 1
    assert result.paths == 10
    assert result.pbo is None
    assert result.selected_positive_paths == 10
