from __future__ import annotations

from datetime import date, timedelta

import pytest

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.price_discovery_lab import _DailyMetric
from stephen_quant.workflows.v4_ohlcv_platform import (
    PortfolioSpec,
    V4Config,
    _paper_replay,
    cluster_candidates,
    evaluate_portfolio,
    generate_v4_candidates,
    residualize_panel,
)


def _row(day: str, instrument: str, signal: float, forward: float) -> EvaluationObservation:
    return EvaluationObservation(
        instrument=instrument,
        timestamp=f"{day}T09:30:00+08:00",
        factor_value=signal,
        factor_available_at=f"{day}T09:29:00+08:00",
        label_start_at=f"{day}T09:30:00+08:00",
        label_end_at=f"{day}T15:00:00+08:00",
        forward_return=forward,
        horizon="1d",
        subperiod="synthetic",
        regime="synthetic",
    )


def test_v4_grammar_is_unique_and_adds_orthogonal_families() -> None:
    candidates = generate_v4_candidates()

    assert len(candidates) == 990
    assert len({item.fingerprint for item in candidates}) == 990
    assert {item.direction for item in candidates} == {-1, 1}
    assert {
        "trend_curvature",
        "breakout_position",
        "gap_mean",
        "intraday_mean",
        "overnight_momentum",
        "liquidity_change",
    } <= {item.family for item in candidates}


def test_clustering_collapses_correlated_variants_and_respects_family_quota() -> None:
    candidates = generate_v4_candidates()
    first = candidates[0]
    second = next(item for item in candidates[1:] if item.family == first.family)
    third = next(item for item in candidates if item.family != first.family)
    days = tuple(f"2022-01-{index:02d}" for index in range(1, 21))
    metrics = {
        first.fingerprint: tuple(_DailyMetric(day, index / 100, 0.0, 0.0, 20) for index, day in enumerate(days)),
        second.fingerprint: tuple(_DailyMetric(day, index / 100, 0.0, 0.0, 20) for index, day in enumerate(days)),
        third.fingerprint: tuple(_DailyMetric(day, (-1) ** index / 100, 0.0, 0.0, 20) for index, day in enumerate(days)),
    }

    clusters = cluster_candidates(
        (first, second, third), metrics, threshold=0.85, family_quota=1, limit=10
    )

    assert len(clusters) == 2
    assert len(clusters[0].members) == 2


def test_decision_local_residualization_removes_exact_control_exposure() -> None:
    instruments = tuple(f"S{index}" for index in range(12))
    candidate = tuple(_row("2023-01-03", item, float(index), index / 100) for index, item in enumerate(instruments))
    control = tuple(_row("2023-01-03", item, float(index), index / 100) for index, item in enumerate(instruments))

    residual = residualize_panel(candidate, (control,))

    assert len(residual) == len(candidate)
    assert max(abs(item.factor_value) for item in residual) < 1e-10


def test_portfolio_grid_uses_prior_day_capacity_and_all_offsets() -> None:
    instruments = tuple(f"S{index}" for index in range(10))
    start = date(2022, 12, 30)
    calendar = tuple((start + timedelta(days=index)).isoformat() for index in range(35))
    bars = {
        instrument: {
            day: QmtDailyBar(
                instrument,
                day,
                10.0,
                10.1,
                9.9,
                10.0,
                10_000_000,
                1_000_000_000,
            )
            for day in calendar
        }
        for instrument in instruments
    }
    rows = tuple(
        _row(day, instrument, float(index), index / 10_000)
        for day in calendar[1:]
        for index, instrument in enumerate(instruments)
    )

    score, returns = evaluate_portfolio(
        "synthetic",
        rows,
        PortfolioSpec(5, "equal", 0),
        year=2023,
        horizon=3,
        nav=3_000_000,
        bars=bars,
        calendar=calendar,
        config=V4Config(),
    )

    assert score.offsets == 3
    assert score.capacity_clipped_notional == pytest.approx(0.0)
    assert score.observations == len(returns)
    assert score.observations > 0
    assert abs(score.cumulative_excess_return) < 0.10


def test_paper_replay_records_aggregate_orders_fills_cash_and_nav() -> None:
    summary, ledger = _paper_replay(
        (0.01, -0.02, 0.005),
        3_000_000,
        0.25,
        horizon=20,
        top_k=5,
    )

    assert summary.periods == len(ledger) == 3
    assert ledger[0].planned_order_notional_cny == pytest.approx(150_000)
    assert ledger[0].order_count == ledger[0].fill_count == 5
    assert ledger[-1].end_nav_cny == pytest.approx(summary.end_nav_cny)
    assert all(not entry.live_order for entry in ledger)
