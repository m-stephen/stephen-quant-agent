from __future__ import annotations

from pathlib import Path

import pytest

from stephen_quant.baseline import (
    BaselineError,
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
    write_stateful_execution_report,
)


def _bar(
    day: str,
    instrument: str,
    opening: float,
    close: float,
    *,
    can_sell: bool = True,
    forced_exit: bool = False,
    capacity: float = 10_000_000,
) -> StatefulBar:
    previous = {"2025-01-02": "2025-01-01", "2025-01-03": "2025-01-02", "2025-01-06": "2025-01-05", "2025-01-07": "2025-01-06"}[day]
    return StatefulBar(
        trade_date=day,
        instrument=instrument,
        open_price=opening,
        close_price=close,
        capacity_cny=capacity,
        capacity_available_at=f"{previous}T15:01:00+08:00",
        can_sell_open=can_sell,
        forced_exit=forced_exit,
        tradability_reason="open_at_lower_limit" if not can_sell else "unrestricted",
    )


def _target(day: str, weights: dict[str, float]) -> TargetAllocation:
    previous = {"2025-01-02": "2025-01-01", "2025-01-03": "2025-01-02", "2025-01-06": "2025-01-05", "2025-01-07": "2025-01-06"}[day]
    return TargetAllocation(day, f"{previous}T15:01:00+08:00", weights)


def _zero_cost(writeoff: int = 20) -> StatefulExecutionConfig:
    return StatefulExecutionConfig(
        maximum_position_weight=1.0,
        commission_bps=0,
        sell_tax_bps=0,
        slippage_bps=0,
        stale_writeoff_sessions=writeoff,
    )


def test_suspension_keeps_holding_and_realizes_gap_when_trading_resumes() -> None:
    sessions = (
        (_bar("2025-01-02", "A", 10, 10),),
        (_bar("2025-01-03", "B", 1, 1),),
        (_bar("2025-01-06", "A", 8, 8),),
    )
    targets = (
        _target("2025-01-02", {"A": 1.0}),
        _target("2025-01-03", {}),
        _target("2025-01-06", {}),
    )

    report = run_stateful_execution(sessions, targets, _zero_cost())

    suspended = report.periods[1]
    resumed = report.periods[2]
    assert suspended.marks[0].source == "explicit_stale_last_close"
    assert suspended.orders[0].reason == "missing_bar_suspension"
    assert suspended.end_nav == pytest.approx(1_000_000)
    assert resumed.overnight_mark_return == pytest.approx(-0.2)
    assert resumed.end_nav == pytest.approx(800_000)
    assert resumed.marks == ()


def test_stale_holding_is_written_to_zero_and_can_recover() -> None:
    sessions = (
        (_bar("2025-01-02", "A", 10, 10),),
        (_bar("2025-01-03", "B", 1, 1),),
        (_bar("2025-01-06", "B", 1, 1),),
        (_bar("2025-01-07", "A", 5, 5),),
    )
    targets = tuple(
        _target(day, {"A": 1.0} if index == 0 else {})
        for index, day in enumerate(("2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"))
    )

    report = run_stateful_execution(sessions, targets, _zero_cost(writeoff=2))

    assert report.periods[2].marks[0].source == "conservative_zero_writeoff"
    assert report.periods[2].end_nav == 0
    assert report.metrics.writeoff_events == 1
    assert report.metrics.writeoff_loss == pytest.approx(1_000_000)
    assert report.periods[3].recovery_value == pytest.approx(500_000)
    assert report.periods[3].end_nav == pytest.approx(500_000)
    assert report.metrics.recovery_events == 1


def test_forced_exit_waits_until_the_open_is_sellable() -> None:
    sessions = (
        (_bar("2025-01-02", "A", 10, 10),),
        (_bar("2025-01-03", "A", 9, 9, can_sell=False, forced_exit=True),),
        (_bar("2025-01-06", "A", 8, 8, forced_exit=True),),
    )
    targets = (
        _target("2025-01-02", {"A": 1.0}),
        _target("2025-01-03", {"A": 1.0}),
        _target("2025-01-06", {"A": 1.0}),
    )

    report = run_stateful_execution(sessions, targets, _zero_cost())

    assert report.periods[1].orders[0].reason == "open_at_lower_limit"
    assert report.periods[1].marks[0].instrument == "A"
    assert report.periods[2].orders[0].executed_notional < 0
    assert report.periods[2].marks == ()


def test_target_must_be_known_before_open() -> None:
    with pytest.raises(BaselineError, match="decided before"):
        run_stateful_execution(
            ((_bar("2025-01-02", "A", 10, 10),),),
            (TargetAllocation("2025-01-02", "2025-01-02T09:30:00+08:00", {}),),
            _zero_cost(),
        )


def test_capacity_and_costs_are_explicit_and_cash_stays_non_negative() -> None:
    config = StatefulExecutionConfig(
        maximum_position_weight=1.0,
        commission_bps=10,
        sell_tax_bps=10,
        slippage_bps=10,
        stale_writeoff_sessions=20,
    )
    report = run_stateful_execution(
        ((_bar("2025-01-02", "A", 10, 10, capacity=100_000),),),
        (_target("2025-01-02", {"A": 1.0}),),
        config,
    )

    order = report.periods[0].orders[0]
    assert order.executed_notional == pytest.approx(100_000)
    assert order.reason == "capacity_clipped"
    assert order.total_cost > 0
    assert report.periods[0].cash >= 0
    assert report.metrics.final_nav < 1_000_000


def test_capacity_timestamp_must_precede_open() -> None:
    bar = StatefulBar(
        **{
            **_bar("2025-01-02", "A", 10, 10).__dict__,
            "capacity_available_at": "2025-01-02T15:00:00+08:00",
        }
    )
    with pytest.raises(BaselineError, match="capacity must be available"):
        run_stateful_execution(
            ((bar,),),
            (_target("2025-01-02", {}),),
            _zero_cost(),
        )


def test_stateful_report_artifacts_are_hashed(tmp_path: Path) -> None:
    report = run_stateful_execution(
        ((_bar("2025-01-02", "A", 10, 10),),),
        (_target("2025-01-02", {"A": 1.0}),),
        _zero_cost(),
    )
    artifacts = write_stateful_execution_report(report, tmp_path)

    assert artifacts.json_path.exists()
    assert artifacts.markdown_path.exists()
    assert artifacts.json_sha256
    assert artifacts.markdown_sha256


def test_non_rebalance_session_holds_drifted_weights_without_trading() -> None:
    sessions = (
        (
            _bar("2025-01-02", "A", 10, 12),
            _bar("2025-01-02", "B", 10, 8),
        ),
        (
            _bar("2025-01-03", "A", 12, 12),
            _bar("2025-01-03", "B", 8, 8),
        ),
    )
    targets = (
        _target("2025-01-02", {"A": 0.5, "B": 0.5}),
        TargetAllocation(
            "2025-01-03",
            "2025-01-02T15:01:00+08:00",
            {},
            rebalance=False,
        ),
    )

    report = run_stateful_execution(sessions, targets, _zero_cost())

    assert all(order.executed_notional == pytest.approx(0) for order in report.periods[1].orders)
