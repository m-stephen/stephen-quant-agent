from dataclasses import replace

import pytest

from stephen_quant.baseline.models import BaselineError
from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)


def simulate(
    prices,
    weights,
    *,
    caps=None,
    blocked=None,
    refresh=None,
    forced=None,
    mode="target_changes",
    limit=0.6,
    close_multiplier=1,
    fee=0,
):
    sessions, targets = [], []
    for i, price in enumerate(prices):
        day = f"2024-01-{i + 2:02}"
        bars = tuple(
            StatefulBar(
                day,
                name,
                value,
                value * close_multiplier,
                (caps or {}).get((i, name), 10000),
                day + "T08:00:00+08:00",
                can_buy_open=(i, name) not in (blocked or set()),
            )
            for name, value in price.items()
        )
        sessions.append(bars)
        targets.append(
            TargetAllocation(
                day,
                f"2024-01-{i + 1:02}T23:00:00+08:00",
                weights[i],
                rebalance=True if refresh is None else refresh[i],
                forced_exits=tuple((forced or {}).get(i, ())),
            )
        )
    return run_stateful_execution(
        tuple(sessions),
        tuple(targets),
        StatefulExecutionConfig(
            maximum_position_weight=limit,
            commission_bps=fee,
            sell_tax_bps=0,
            slippage_bps=0,
            rebalance_mode=mode,
        ),
        initial_nav=1000,
    )


def traded(report, i):
    return sum(abs(o.executed_notional) for o in report.periods[i].orders)


def test_unchanged_completed_weight_drifts_without_maintenance():
    args = ([{"A": 10}, {"A": 11}], [{"A": 0.4}, {"A": 0.4}])
    drift, full = simulate(*args), simulate(*args, mode="full_target")
    assert traded(drift, 1) == pytest.approx(0)
    assert traded(full, 1) == pytest.approx(24)
    assert drift.periods[1].marks[0].shares == 40


def test_changed_weight_resets_and_removed_member_exits():
    r = simulate([{"A": 10}] * 3, [{"A": 0.4}, {"A": 0.2}, {}])
    assert traded(r, 1) == pytest.approx(200)
    assert r.periods[-1].marks == ()


@pytest.mark.parametrize("constraint", ["capacity", "blocked", "missing"])
def test_unfilled_request_retries_only_at_next_refresh(constraint):
    prices = [{"A": 10, "B": 10}] * 3
    kwargs = {"caps": {(0, "A"): 100}} if constraint == "capacity" else {}
    if constraint == "blocked":
        kwargs["blocked"] = {(0, "A")}
    if constraint == "missing":
        prices = [{"B": 10}, {"A": 10}, {"A": 10}]
    r = simulate(prices, [{"A": 0.4}] * 3, refresh=[True, False, True], **kwargs)
    assert traded(r, 1) == pytest.approx(0)
    assert r.periods[-1].marks[0].shares == pytest.approx(40)


def test_cap_trim_on_refresh_and_close_can_drift_above_cap():
    r = simulate([{"A": 10}, {"A": 20}], [{"A": 0.4}] * 2, limit=0.4)
    assert traded(r, 1) == pytest.approx(240)
    changed_close = simulate([{"A": 10}], [{"A": 0.4}], limit=0.4, close_multiplier=2)
    assert changed_close.periods[0].marks[0].market_value / changed_close.metrics.final_nav > 0.4


def test_forced_exit_precedes_unchanged_target():
    r = simulate([{"A": 10}] * 2, [{"A": 0.4}] * 2, forced={1: ["A"]})
    assert r.periods[-1].marks == ()


def test_fee_cash_scaling_never_leverages_and_retries():
    r = simulate([{"A": 10, "B": 10}] * 3, [{"A": 0.5, "B": 0.5}] * 3, fee=6)
    assert all(p.cash >= 0 for p in r.periods)
    assert sum(m.market_value for m in r.periods[0].marks) < 1000
    assert any(o.reason == "funding_scaled" for o in r.periods[0].orders)


def test_future_close_does_not_affect_same_day_sizing():
    args = ([{"A": 10}], [{"A": 0.4}])
    a, b = simulate(*args), simulate(*args, close_multiplier=5)
    assert a.periods[0].orders == b.periods[0].orders


def test_default_is_legacy_and_unknown_mode_rejected():
    assert StatefulExecutionConfig().rebalance_mode == "full_target"
    with pytest.raises(BaselineError, match="rebalance mode"):
        simulate([{"A": 10}], [{"A": 0.4}], mode="typo")


def test_target_timing_still_rejected():
    day = "2024-01-02"
    bar = StatefulBar(day, "A", 10, 10, 1000, day + "T08:00:00+08:00")
    target = TargetAllocation(day, day + "T09:30:00+08:00", {"A": 0.4})
    with pytest.raises(BaselineError, match="before the execution"):
        run_stateful_execution(
            ((bar,),),
            (target,),
            replace(StatefulExecutionConfig(), rebalance_mode="target_changes"),
        )


@pytest.mark.parametrize("recovery_capacity", [10000, 100])
def test_written_down_exit_is_not_filled_and_retries_recovery(recovery_capacity):
    # Day20's zero valuation does not mean shares were actually sold.
    prices = [{"A": 10}] + [{"B": 10}] * 20 + [{"A": 10}] * 2
    weights = [{"A": .4}] + [{}] * 22
    r = simulate(prices, weights, caps={(21, "A"): recovery_capacity})
    assert r.metrics.writeoff_events == 1
    assert r.metrics.recovery_events == 1
    assert traded(r, 21) == pytest.approx(min(400, recovery_capacity))
    assert r.periods[-1].marks == ()
    assert r.periods[-1].cash == pytest.approx(1000)
