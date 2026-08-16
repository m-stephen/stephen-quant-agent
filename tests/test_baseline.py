from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineError,
    BaselineLineage,
    BaselineObservation,
    run_momentum_topk,
    write_baseline_report,
)


def _lineage() -> BaselineLineage:
    return BaselineLineage(
        factor_id="ret_60",
        factor_version="1.0.0",
        snapshot_id="snap_fixture",
        experiment_id="exp_fixture",
        trial_id="trial_fixture",
        code_version="test-sha",
    )


def _observations(
    signal_sets: tuple[dict[str, float], ...] | None = None,
    *,
    average_daily_value: float = 100_000_000.0,
    forward_returns: dict[str, float] | None = None,
) -> list[BaselineObservation]:
    signals = signal_sets or (
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0},
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0},
        {"A": 1.0, "B": 2.0, "C": 4.0, "D": 3.0},
    )
    returns = forward_returns or {"A": 0.01, "B": 0.02, "C": -0.01, "D": 0.0}
    start = date(2025, 1, 2)
    rows: list[BaselineObservation] = []
    for period_index, period_signals in enumerate(signals):
        signal_date = start + timedelta(days=period_index * 7)
        execution_date = signal_date + timedelta(days=1)
        return_end = execution_date + timedelta(days=5)
        for instrument, signal in period_signals.items():
            rows.append(
                BaselineObservation(
                    instrument=instrument,
                    signal=signal,
                    signal_at=f"{signal_date.isoformat()}T15:00:00+08:00",
                    signal_available_at=f"{signal_date.isoformat()}T15:01:00+08:00",
                    average_daily_value=average_daily_value,
                    liquidity_available_at=f"{signal_date.isoformat()}T16:00:00+08:00",
                    execution_at=f"{execution_date.isoformat()}T09:30:00+08:00",
                    return_end_at=f"{return_end.isoformat()}T15:00:00+08:00",
                    forward_return=returns[instrument],
                )
            )
    return rows


def test_topk_ranking_weights_and_tie_break_are_deterministic() -> None:
    signals = ({"B": 4.0, "A": 4.0, "C": 2.0, "D": 1.0},)
    report = run_momentum_topk(
        _observations(signals, forward_returns={item: 0.0 for item in "ABCD"}),
        _lineage(),
        BaselineConfig(top_k=2, cash_reserve=0.2, max_participation_rate=1.0),
    )

    period = report.periods[0]
    assert period.selected_instruments == ("A", "B")
    orders = {order.instrument: order for order in period.orders}
    assert orders["A"].target_weight == pytest.approx(0.4)
    assert orders["B"].target_weight == pytest.approx(0.4)
    assert period.cash_after_execution == pytest.approx(200_000.0)
    assert report.metrics.final_nav == pytest.approx(1_000_000.0)


def test_unchanged_portfolio_has_zero_turnover_and_zero_cost() -> None:
    report = run_momentum_topk(
        _observations(forward_returns={item: 0.0 for item in "ABCD"}),
        _lineage(),
        BaselineConfig(
            top_k=2,
            rebalance_every=2,
            cash_reserve=0.1,
            commission_bps=5.0,
            slippage_bps=5.0,
            impact_coefficient_bps=2.0,
            max_participation_rate=1.0,
        ),
    )

    unchanged = report.periods[1]
    assert unchanged.traded_notional == pytest.approx(0.0)
    assert unchanged.turnover == pytest.approx(0.0)
    assert unchanged.total_cost == pytest.approx(0.0)


def test_higher_costs_cannot_improve_net_performance() -> None:
    rows = _observations()
    zero_cost = run_momentum_topk(
        rows,
        _lineage(),
        BaselineConfig(top_k=2, cash_reserve=0.1, max_participation_rate=1.0),
    )
    costly = run_momentum_topk(
        rows,
        _lineage(),
        BaselineConfig(
            top_k=2,
            cash_reserve=0.1,
            commission_bps=8.0,
            slippage_bps=12.0,
            impact_coefficient_bps=20.0,
            max_participation_rate=1.0,
        ),
    )

    assert costly.metrics.total_cost > 0
    assert costly.metrics.final_nav < zero_cost.metrics.final_nav
    assert costly.metrics.net_total_return < zero_cost.metrics.net_total_return


def test_sell_tax_is_charged_only_on_sell_orders() -> None:
    signals = (
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0},
        {"A": 1.0, "B": 2.0, "C": 4.0, "D": 3.0},
    )
    report = run_momentum_topk(
        _observations(signals, forward_returns={item: 0.0 for item in "ABCD"}),
        _lineage(),
        BaselineConfig(top_k=2, sell_tax_bps=10.0, max_participation_rate=1.0),
    )

    first_orders = report.periods[0].orders
    second_orders = report.periods[1].orders
    assert all(order.sell_tax_cost == 0 for order in first_orders)
    assert all(
        order.sell_tax_cost > 0
        for order in second_orders
        if order.executed_notional < 0
    )
    assert all(
        order.sell_tax_cost == 0
        for order in second_orders
        if order.executed_notional >= 0
    )


def test_capacity_limits_clip_orders_and_are_reported() -> None:
    report = run_momentum_topk(
        _observations(average_daily_value=100_000.0),
        _lineage(),
        BaselineConfig(top_k=2, max_participation_rate=0.01),
    )

    first = report.periods[0]
    assert all(abs(order.executed_notional) <= 1_000.0 for order in first.orders)
    assert report.metrics.capacity_clipped_notional > 0
    assert report.metrics.clipped_orders > 0
    assert all(order.participation_rate <= 0.01 for order in first.orders)


def test_unfunded_buys_are_scaled_without_negative_cash() -> None:
    report = run_momentum_topk(
        _observations(forward_returns={item: 0.0 for item in "ABCD"}),
        _lineage(),
        BaselineConfig(
            top_k=2,
            commission_bps=100.0,
            slippage_bps=100.0,
            impact_coefficient_bps=100.0,
            max_participation_rate=1.0,
        ),
    )

    first = report.periods[0]
    assert first.cash_after_execution >= 0
    assert report.metrics.funding_clipped_notional > 0
    assert sum(order.executed_notional for order in first.orders) < 1_000_000.0


def test_rebalance_schedule_holds_positions_between_rebalances() -> None:
    report = run_momentum_topk(
        _observations(),
        _lineage(),
        BaselineConfig(top_k=2, rebalance_every=2, cash_reserve=0.1),
    )

    assert [period.rebalanced for period in report.periods] == [True, False, True]
    assert report.periods[1].orders == ()
    assert report.periods[1].traded_notional == 0.0


def test_future_signal_and_liquidity_are_rejected() -> None:
    rows = _observations()
    first = rows[0]
    rows[0] = BaselineObservation(
        **{
            **first.__dict__,
            "signal_available_at": first.execution_at,
        }
    )
    with pytest.raises(BaselineError, match="signal is not available"):
        run_momentum_topk(rows, _lineage(), BaselineConfig(top_k=2))

    rows = _observations()
    first = rows[0]
    rows[0] = BaselineObservation(
        **{
            **first.__dict__,
            "liquidity_available_at": first.execution_at,
        }
    )
    with pytest.raises(BaselineError, match="liquidity is not available"):
        run_momentum_topk(rows, _lineage(), BaselineConfig(top_k=2))


def test_overlapping_forward_return_windows_are_rejected() -> None:
    rows = _observations()
    first_execution = rows[0].execution_at
    for index, row in enumerate(rows):
        if row.execution_at == first_execution:
            rows[index] = BaselineObservation(
                **{
                    **row.__dict__,
                    "return_end_at": "2025-01-20T15:00:00+08:00",
                }
            )
    with pytest.raises(BaselineError, match="cannot overlap"):
        run_momentum_topk(rows, _lineage(), BaselineConfig(top_k=2))


def test_report_artifacts_are_deterministic_and_contain_lineage(tmp_path: Path) -> None:
    report = run_momentum_topk(
        _observations(),
        _lineage(),
        BaselineConfig(
            top_k=2,
            cash_reserve=0.1,
            commission_bps=2.0,
            slippage_bps=3.0,
            impact_coefficient_bps=5.0,
        ),
    )
    first = write_baseline_report(report, tmp_path / "first")
    second = write_baseline_report(report, tmp_path / "second")
    payload = json.loads(first.json_path.read_text(encoding="utf-8"))

    assert first.json_sha256 == second.json_sha256
    assert first.markdown_sha256 == second.markdown_sha256
    assert payload["lineage"]["snapshot_id"] == "snap_fixture"
    assert payload["config"]["cost_model_version"]
    assert "net_total_return" in payload["metrics"]
    assert "Momentum Top-K Baseline" in first.markdown_path.read_text(encoding="utf-8")
