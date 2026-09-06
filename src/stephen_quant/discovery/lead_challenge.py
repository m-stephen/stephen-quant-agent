"""Predeclared falsification of frozen leads, not an Alpha certificate."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from statistics import mean

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.incremental_alpha import incremental_targets
from stephen_quant.discovery.reliable_research import compound, sharpe

VERSION = "11.8.0"


@dataclass(frozen=True)
class Challenge:
    name: str
    extra_slippage_bps: int = 0
    capacity_fraction: float = 1.0
    delay_sessions: int = 0
    continuous: bool = False


CHALLENGES = (
    Challenge("baseline_82"),
    Challenge("cost_102", extra_slippage_bps=10),
    Challenge("cost_132", extra_slippage_bps=25),
    Challenge("quarter_capacity", capacity_fraction=0.25),
    Challenge("delay_one", delay_sessions=1),
    Challenge("continuous_82", continuous=True),
)


def delayed_targets(targets, lag):
    """Delay the complete frozen order schedule; never reselect using later features."""
    if isinstance(lag, bool) or lag not in (0, 1):
        raise ValueError("only the predeclared zero/one-session delay is supported")
    return tuple(
        replace(targets[i - lag], trade_date=t.trade_date)
        if i >= lag
        else TargetAllocation(t.trade_date, t.decided_at, {}, False)
        for i, t in enumerate(targets)
    )


def challenge_execute(days, hypothesis, kind, challenge, rank_cache=None):
    if challenge not in CHALLENGES:
        raise ValueError("unregistered challenge")
    targets, coverage = incremental_targets(days, hypothesis, kind, rank_cache)
    targets = delayed_targets(targets, challenge.delay_sessions)
    sessions = tuple(
        d.bars
        if challenge.capacity_fraction == 1
        else tuple(
            replace(b, capacity_cny=b.capacity_cny * challenge.capacity_fraction) for b in d.bars
        )
        for d in days
    )
    report = run_stateful_execution(
        sessions,
        targets,
        StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=6,
            sell_tax_bps=10,
            slippage_bps=30 + challenge.extra_slippage_bps,
        ),
        initial_nav=3_000_000,
    )
    return report, targets, coverage


def _aligned(actual, control):
    if len(actual) != len(control) or len(actual) < 3:
        raise ValueError("aligned nonempty return vectors required")
    if any(not math.isfinite(v) or v <= -1 for v in (*actual, *control)):
        raise ValueError("finite returns above -100% required")


def lowvol_attribution(actual, control, lag=20):
    """Descriptive OLS with Bartlett HAC; NOT selection-adjusted inference."""
    _aligned(actual, control)
    if not isinstance(lag, int) or lag < 0:
        raise ValueError("HAC lag must be a nonnegative integer")
    n = len(actual)
    xbar, ybar = mean(control), mean(actual)
    xx = sum((x - xbar) ** 2 for x in control)
    if xx <= 1e-20:
        return {"status": "NOT_IDENTIFIABLE", "reason": "constant low-vol control"}
    beta = sum((x - xbar) * (y - ybar) for x, y in zip(control, actual)) / xx
    intercept = ybar - beta * xbar
    residual = [y - intercept - beta * x for x, y in zip(control, actual)]
    yy = sum((y - ybar) ** 2 for y in actual)
    # Row0 of (X'X)^-1 times x_t gives the influence of observation t on intercept.
    influence = [(1 / n - xbar * (x - xbar) / xx) * e for x, e in zip(control, residual)]
    variance = sum(v * v for v in influence)
    for k in range(1, min(lag + 1, n)):
        variance += (
            2 * (1 - k / (lag + 1)) * sum(influence[t] * influence[t - k] for t in range(k, n))
        )
    se = math.sqrt(max(0.0, variance * n / (n - 2)))
    return {
        "status": "DESCRIPTIVE_NOT_SELECTION_ADJUSTED",
        "beta_to_lowvol": beta,
        "r_squared": 1 - sum(e * e for e in residual) / yy if yy else None,
        "annualized_intercept": intercept * 252,
        "hac95_annualized_intercept_interval": [
            (intercept - 1.96 * se) * 252,
            (intercept + 1.96 * se) * 252,
        ],
        "hac_lag": lag,
        "market_industry_size_controls": "NOT_TESTED",
        "causal_alpha": False,
    }


def tail_sensitivity(actual, control, top=5):
    """Counterfactual diagnostic only. No observations are removed or traded."""
    _aligned(actual, control)
    if not isinstance(top, int) or top < 1:
        raise ValueError("positive top-day count required")
    active = [a - b for a, b in zip(actual, control)]
    selected = sorted((i for i, r in enumerate(active) if r > 0), key=lambda i: (-active[i], i))[
        :top
    ]
    masked = list(actual)
    for i in selected:
        masked[i] = control[i]
    positive = sum(max(0, r) for r in active)
    return {
        "status": "NONTRADABLE_POSTHOC_DIAGNOSTIC",
        "top_positive_active_days": selected,
        "positive_active_sum_share": sum(active[i] for i in selected) / positive if positive else 0,
        "net_return_if_top_active_days_equal_control": compound(masked),
        "increment_if_top_active_days_equal_control": compound(masked) - compound(control),
        "observations_retained": len(actual),
    }


def challenge_assessment(years):
    """Identical economic screen to V11.7, applied to EVERY frozen stress scenario."""
    from stephen_quant.discovery.incremental_alpha import suspected_lead

    return suspected_lead({year: {"2": row} for year, row in years.items()})


def next_action(survivors, *, engineering_pass=True):
    # Historical diagnostics alone can NEVER reach a validated or tradable state.
    if not engineering_pass:
        return "REPAIR_ENGINEERING_BEFORE_RESEARCH"
    if survivors:
        return "FROZEN_BROKERAGE_AND_STYLE_CHALLENGE"
    return "PREREGISTER_NEXT_BOUNDED_MECHANISM_EPOCH"


def summarize_account(report):
    daily = [p.net_return for p in report.periods]
    if any(v is None for v in daily):
        raise ValueError("undefined account returns")
    traded = sum(p.traded_notional_cny for p in report.periods)
    profit = report.metrics.final_nav - report.metrics.initial_nav
    return {
        "metrics": asdict(report.metrics),
        "daily_returns": daily,
        "dates": [p.trade_date for p in report.periods],
        "sharpe": sharpe(daily),
        "profit_cny": profit,
        "gross_traded_notional": traded,
        "one_way_turnover_initial_capital": traded / report.metrics.initial_nav,
        "fixed_fill_extra_one_way_bps_to_zero_profit": profit / traded * 10_000 if traded else None,
        "break_even_caveat": "linear fixed-fill sensitivity, not a rerun or executable capacity claim",
        "quarterly_returns": {
            f"{y}Q{q}": compound(
                [
                    p.net_return
                    for p in report.periods
                    if p.trade_date[:4] == y and (int(p.trade_date[5:7]) - 1) // 3 + 1 == q
                ]
            )
            for y in sorted({p.trade_date[:4] for p in report.periods})
            for q in (1, 2, 3, 4)
        },
    }
