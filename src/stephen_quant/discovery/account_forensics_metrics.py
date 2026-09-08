"""Descriptive arithmetic on saved NAV accounts; never an Alpha Court verdict."""

import math
from statistics import fmean, stdev

from .account_forensics import close, day, finite


def _window(periods):
    if not periods:
        raise ValueError("nonempty saved window required")
    initial = finite(periods[0]["previous_nav"])
    if initial <= 0:
        raise ValueError("positive saved opening NAV required")
    previous, peak, drawdown = initial, initial, 0.0
    returns, turnover = [], []
    for p in periods:
        close(p["previous_nav"], previous)
        nav, ret = finite(p["end_nav"]), finite(p["net_return"])
        close(nav / previous - 1, ret)
        if nav <= 0:
            raise ValueError("positive saved NAV required for these diagnostics")
        peak = max(peak, nav)
        drawdown = min(drawdown, nav / peak - 1)
        returns.append(ret)
        turnover.append(finite(p["traded_notional_cny"], nonnegative=True) / previous / 2)
        previous = nav
    sd = stdev(returns) if len(returns) > 1 else 0
    fees = sum(finite(p["total_cost"], nonnegative=True) for p in periods)
    return {
        "start": periods[0]["trade_date"], "end": periods[-1]["trade_date"],
        "sessions": len(periods), "opening_nav_cny": initial, "closing_nav_cny": previous,
        "profit_cny": previous - initial, "net_return": previous / initial - 1,
        "sharpe_252_zero_risk_free": fmean(returns) / sd * math.sqrt(252) if sd > 0 else None,
        "max_drawdown": drawdown, "fees_cny": fees,
        "traded_notional_cny": sum(p["traded_notional_cny"] for p in periods),
        "sum_one_way_turnover": sum(turnover), "mean_daily_one_way_turnover": fmean(turnover),
        "mean_cash_nav_weight": fmean(p["cash"] / p["end_nav"] for p in periods),
        "max_actual_positions": max(len(p["marks"]) for p in periods),
        "writeoff_events": sum(p["writeoff_positions"] for p in periods),
        "writeoff_cny": sum(p["writeoff_loss"] for p in periods),
        "recovery_events": sum(p["recovery_positions"] for p in periods),
        "recovery_valuation_cny": sum(p["recovery_value"] for p in periods),
    }


def account_summary(report, *, calendar):
    dates = [day(p["trade_date"]) for p in report["periods"]]
    if dates != list(calendar) or dates != sorted(set(dates)):
        raise ValueError("exact complete saved account calendar required")
    full = _window(report["periods"])
    for key, field in (("initial_nav", "opening_nav_cny"), ("final_nav", "closing_nav_cny"),
                       ("net_total_return", "net_return"), ("max_drawdown", "max_drawdown"),
                       ("total_cost", "fees_cny")):
        close(report["metrics"][key], full[field])
    years = {year: _window([p for p in report["periods"] if p["trade_date"].startswith(year)])
             for year in sorted({dt[:4] for dt in dates})}
    return {
        "continuous": full, "years": years,
        "definitions": {
            "year_capital": "actual_carried_previous_nav_not_reset_to_initial_capital",
            "turnover": "0.5_times_sum_abs_executed_notional_over_previous_close_nav_each_day",
            "sharpe": "sqrt252_times_mean_daily_net_return_over_sample_sd_zero_risk_free",
            "drawdown": "window_peak_including_actual_window_opening_nav",
            "writeoff_recovery": "valuation_events_not_counterfactual_profit_or_cash_receipts",
        },
        "validated_alpha": False,
    }


def primary_difference(response, risk, *, calendar):
    a, b = response["periods"], risk["periods"]
    if [p["trade_date"] for p in a] != list(calendar) or [p["trade_date"] for p in b] != list(calendar):
        raise ValueError("exact paired calendar required")
    x, y = account_summary(response, calendar=calendar), account_summary(risk, calendar=calendar)
    close(x["continuous"]["opening_nav_cny"], y["continuous"]["opening_nav_cny"])
    differences = {}
    for key in ("continuous", *x["years"]):
        xa = x["continuous"] if key == "continuous" else x["years"][key]
        yb = y["continuous"] if key == "continuous" else y["years"][key]
        pairs = [(p, q) for p, q in zip(a, b, strict=True)
                 if key == "continuous" or p["trade_date"].startswith(key)]
        differences[key] = {
            "net_return_difference_pp": (xa["net_return"] - yb["net_return"]) * 100,
            "profit_difference_cny": xa["profit_cny"] - yb["profit_cny"],
            "paired_mean_net_return_difference_bps": fmean(
                p["net_return"] - q["net_return"] for p, q in pairs) * 10000,
            "sessions": len(pairs),
        }
    return {"windows": differences, "statistical_status": "DESCRIPTIVE_NOT_CERTIFIED",
            "dsr": None, "pbo": None, "placebo_pvalue": None,
            "validated_alpha": False}
