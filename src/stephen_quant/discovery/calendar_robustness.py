"""Predeclared continuous-capital calendars; no phase selection or Alpha certification."""

from __future__ import annotations

import math
from dataclasses import asdict
from itertools import pairwise

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.discovery.incremental_alpha import (
    incremental_targets,
    matched_ranks,
    scores_from_ranks,
)
from stephen_quant.discovery.reliable_research import compound, holdings, sharpe

VERSION = "11.9.0"
PHASES = (0, 5, 10, 15)
CALENDARS = tuple(f"phase_{p}" for p in PHASES) + ("staggered_four", "annual_calendar")


def phase_targets(days, hypothesis, kind, phase, cache=None):
    """Keep signal lag and twenty-session cadence; unstarted capital stays cash."""
    if type(phase) is not int or phase not in PHASES or hypothesis.horizon != 20:
        raise ValueError("only registered twenty-session phases are supported")
    cache = {} if cache is None else cache
    previous, result, coverage = (), [], []
    for i, day in enumerate(days):
        signal = days[i - 1] if i else None
        rebalance = i >= phase + 1 and (i - phase - 1) % 20 == 0
        weights = {}
        if rebalance:
            key = (signal.date, hypothesis.field)
            if key not in cache:
                cache[key] = matched_ranks(signal.features, hypothesis.field)
            ranks = cache[key]
            scores = scores_from_ranks(ranks, hypothesis, kind)
            previous = holdings(scores, previous)
            weights = {n: 1 / 40 for n in previous}
            coverage.append({"date": signal.date, "selected": len(previous), "phase": phase})
        result.append(
            TargetAllocation(
                day.date,
                f"{signal.date}T23:59:59+08:00" if signal else f"{day.date}T08:00:00+08:00",
                weights,
                rebalance,
            )
        )
    return tuple(result), coverage


def combine_sleeves(sleeves):
    """Average live desired weights, never realized returns or future NAVs.

    This is ONE netted account: on a cohort refresh the whole aggregate target is
    rebalanced, including drift of other cohorts. It is not four segregated funds.
    """
    if len(sleeves) != 4 or not sleeves[0] or len({len(s) for s in sleeves}) != 1:
        raise ValueError("four aligned nonempty sleeves required")
    previous = [{} for _ in sleeves]
    result = []
    for day_rows in zip(*sleeves, strict=True):
        if len({t.trade_date for t in day_rows}) != 1:
            raise ValueError("sleeve dates differ")
        rebalance = any(t.rebalance for t in day_rows)
        for i, t in enumerate(day_rows):
            if t.rebalance:
                previous[i] = t.weights
        weights = {}
        if rebalance:
            for sleeve in previous:
                for n, value in sleeve.items():
                    weights[n] = weights.get(n, 0.0) + value / 4
        if sum(weights.values()) > 1 + 1e-10 or any(w > 0.025 + 1e-10 for w in weights.values()):
            raise ValueError("aggregate exposure exceeds frozen limits")
        result.append(
            TargetAllocation(
                day_rows[0].trade_date,
                max(t.decided_at for t in day_rows),
                weights,
                rebalance,
            )
        )
    return tuple(result)


def calendar_targets(days, hypothesis, kind, calendar, cache=None):
    if calendar not in CALENDARS:
        raise ValueError("unregistered calendar")
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered unique nonempty trading days required")
    if calendar.startswith("phase_"):
        return phase_targets(days, hypothesis, kind, int(calendar[6:]), cache)
    if calendar == "annual_calendar":
        targets, coverage = [], []
        for year in sorted({d.date[:4] for d in days}):
            # Only target selection restarts; the execution engine is called ONCE.
            t, c = incremental_targets(
                tuple(d for d in days if d.date[:4] == year), hypothesis, kind, cache
            )
            targets.extend(t)
            coverage.extend(c)
        return tuple(targets), coverage
    pairs = [phase_targets(days, hypothesis, kind, phase, cache) for phase in PHASES]
    return combine_sleeves([p[0] for p in pairs]), [c for _, rows in pairs for c in rows]


def account_summary(report):
    daily = [p.net_return for p in report.periods]
    dates = [p.trade_date for p in report.periods]
    return {
        "metrics": asdict(report.metrics),
        "daily_returns": daily,
        "dates": dates,
        "profit_cny": report.metrics.final_nav - 3_000_000,
        "pooled_sharpe": sharpe(daily),
        "years": {
            year: compound([r for d, r in zip(dates, daily, strict=True) if d[:4] == year])
            for year in sorted({d[:4] for d in dates})
        },
    }


def assess_calendars(accounts):
    """Require the preselected staggered policy, never the best observed phase."""
    if set(accounts) != set(CALENDARS):
        raise ValueError("complete calendar family required")
    s = accounts["staggered_four"]
    candidate, base, hashed = (s[k] for k in ("candidate", "lowvol", "hash"))
    if any(set(s[k]["years"]) != {"2023", "2024"} for k in s):
        raise ValueError("both continuous-account development years required")
    increments = [
        accounts[f"phase_{p}"]["candidate"]["metrics"]["net_total_return"]
        - accounts[f"phase_{p}"]["lowvol"]["metrics"]["net_total_return"]
        for p in PHASES
    ]
    delta = candidate["metrics"]["net_total_return"] - base["metrics"]["net_total_return"]
    values = increments + [
        delta,
        candidate["pooled_sharpe"],
        candidate["metrics"]["max_drawdown"],
        *candidate["years"].values(),
        *base["years"].values(),
        hashed["metrics"]["net_total_return"],
    ]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("nonfinite assessment")
    checks = {
        "both_years_positive": all(r > 0 for r in candidate["years"].values()),
        "sharpe": candidate["pooled_sharpe"] >= 0.7,
        "continuous_drawdown": candidate["metrics"]["max_drawdown"] >= -0.25,
        "lowvol_increment": delta >= 0.03,
        "annual_increment": all(
            candidate["years"][y] - base["years"][y] >= -0.05 for y in candidate["years"]
        ),
        "hash_increment": candidate["metrics"]["net_total_return"]
        > hashed["metrics"]["net_total_return"],
        "three_of_four_phases": sum(v > 0 for v in increments) >= 3,
        "worst_phase_floor": min(increments) >= -0.05,
        "accounts": all(
            row["audit"]["pass"] for rows in accounts.values() for row in rows.values()
        ),
    }
    return {
        "checks": checks,
        "historical_robust_lead": all(checks.values()),
        "validated_alpha": False,
        "staggered_increment": delta,
        "phase_increments": dict(zip(PHASES, increments, strict=True)),
        "status": "CONTAMINATED_HISTORY_NOT_INDEPENDENT",
    }
