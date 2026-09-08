"""Independent saved-report arithmetic checks; no producer metric helpers.

These checks are one component of the future full forensic verifier, not source
truth, execution-policy validation or an Alpha Court certificate.
"""

import json
import math

from .search_power_dsl import sha256_json


def compare(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError("independent field coverage mismatch")
        for key in expected:
            compare(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("independent row coverage mismatch")
        for a, b in zip(actual, expected, strict=True):
            compare(a, b)
    elif type(expected) in (int, float):
        if (type(actual) not in (int, float) or not math.isfinite(actual)
                or not math.isfinite(expected)
                or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-6)):
            raise ValueError("independent amount mismatch")
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError("independent identity mismatch")


def verify_compact(report, path):
    """Stream the original compact ledger and compare every saved full period."""
    fields = {"date": "trade_date", "nav": "end_nav", "return": "net_return",
              "cash": "cash", "cost": "total_cost", "stale_positions": "stale_position_days",
              "writeoff_loss": "writeoff_loss", "positions": "marks", "orders": "orders"}
    with path.open(encoding="utf-8") as stream:
        for period in report["periods"]:
            line = stream.readline()
            if not line:
                raise ValueError("incomplete compact ledger")
            compare(json.loads(line), {k: period[v] for k, v in fields.items()})
        if stream.read():
            raise ValueError("extra compact ledger records")
    return len(report["periods"])


def _window(rows):
    if not rows:
        raise ValueError("nonempty independent window required")
    opening = rows[0]["previous_nav"]
    prior, peak, worst = opening, opening, 0.0
    returns, turnover = [], []
    for row in rows:
        compare(row["previous_nav"], prior)
        if prior <= 0 or row["end_nav"] <= 0:
            raise ValueError("positive NAV required")
        value = row["end_nav"] / prior - 1
        compare(row["net_return"], value)
        compare(row["cash"] + math.fsum(m["market_value"] for m in row["marks"]), row["end_nav"])
        cost = math.fsum(o["total_cost"] for o in row["orders"])
        traded = math.fsum(abs(o["executed_notional"]) for o in row["orders"])
        compare(row["total_cost"], cost)
        compare(row["traded_notional_cny"], traded)
        turnover.append(traded / (2 * prior))
        returns.append(value)
        prior = row["end_nav"]
        peak = max(peak, prior)
        worst = min(worst, prior / peak - 1)
    count = len(rows)
    mean = math.fsum(returns) / count
    variance = math.fsum((r - mean) ** 2 for r in returns) / (count - 1) if count > 1 else 0
    return {
        "start": rows[0]["trade_date"], "end": rows[-1]["trade_date"], "sessions": count,
        "opening_nav_cny": opening, "closing_nav_cny": prior, "profit_cny": prior - opening,
        "net_return": prior / opening - 1,
        "sharpe_252_zero_risk_free": mean * math.sqrt(252 / variance) if variance > 0 else None,
        "max_drawdown": worst,
        "fees_cny": math.fsum(p["total_cost"] for p in rows),
        "traded_notional_cny": math.fsum(p["traded_notional_cny"] for p in rows),
        "sum_one_way_turnover": math.fsum(turnover),
        "mean_daily_one_way_turnover": math.fsum(turnover) / count,
        "mean_cash_nav_weight": math.fsum(p["cash"] / p["end_nav"] for p in rows) / count,
        "max_actual_positions": max(len(p["marks"]) for p in rows),
        "writeoff_events": sum(p["writeoff_positions"] for p in rows),
        "writeoff_cny": math.fsum(p["writeoff_loss"] for p in rows),
        "recovery_events": sum(p["recovery_positions"] for p in rows),
        "recovery_valuation_cny": math.fsum(p["recovery_value"] for p in rows),
    }


def verify_metrics(report, summary, *, calendar):
    rows = report["periods"]
    if [p["trade_date"] for p in rows] != list(calendar):
        raise ValueError("independent complete calendar mismatch")
    compare(summary["continuous"], _window(rows))
    years = {dt[:4] for dt in calendar}
    if set(summary["years"]) != years:
        raise ValueError("independent annual coverage mismatch")
    for year in sorted(years):
        compare(summary["years"][year], _window([p for p in rows if p["trade_date"][:4] == year]))
    if summary["validated_alpha"] is not False:
        raise ValueError("saved arithmetic is not alpha certification")
    return {"arithmetic_verified": True, "sessions": len(rows), "validated_alpha": False}


def verify_primary(response, risk, primary, *, calendar):
    a, b = response["periods"], risk["periods"]
    if any([p["trade_date"] for p in rows] != list(calendar) for rows in (a, b)):
        raise ValueError("independent paired calendar mismatch")
    compare(a[0]["previous_nav"], b[0]["previous_nav"])
    expected = {}
    for window in ("continuous", *sorted({dt[:4] for dt in calendar})):
        pairs = [(p, q) for p, q in zip(a, b, strict=True)
                 if window == "continuous" or p["trade_date"][:4] == window]
        x, y = _window([p for p, _ in pairs]), _window([q for _, q in pairs])
        expected[window] = {
            "net_return_difference_pp": 100 * (x["net_return"] - y["net_return"]),
            "profit_difference_cny": x["profit_cny"] - y["profit_cny"],
            "paired_mean_net_return_difference_bps": math.fsum(
                p["net_return"] - q["net_return"] for p, q in pairs) * 10000 / len(pairs),
            "sessions": len(pairs),
        }
    compare(primary, {"windows": expected, "statistical_status": "DESCRIPTIVE_NOT_CERTIFIED",
                      "dsr": None, "pbo": None, "placebo_pvalue": None, "validated_alpha": False})
    return {"primary_arithmetic_verified": True, "validated_alpha": False}


def verify_exposures(report, emitted, *, source_calendar, ranks):
    """Recompute every invested denominator, including unknown and zero holdings."""
    if list(source_calendar) != sorted(set(source_calendar)):
        raise ValueError("independent ordered source calendar required")
    dates = {dt: i for i, dt in enumerate(source_calendar)}
    rows = report["periods"]
    if [p["trade_date"] for p in rows] != [d for d in source_calendar if d >= "2023-01-01"]:
        raise ValueError("independent full exposure calendar required")
    expected = []
    for p in rows:
        i = dates[p["trade_date"]]
        if i == 0:
            raise ValueError("independent prior market day required")
        asof = source_calendar[i - 1]
        mapping = {name: row["cell"] for name, row in ranks[asof].items()}
        if any(type(cell) is not int or cell not in range(20) for cell in mapping.values()):
            raise ValueError("independent twenty cell mapping required")
        marks = p["marks"]
        names = [m["instrument"] for m in marks]
        if len(set(names)) != len(names):
            raise ValueError("independent unique held names required")
        invested = math.fsum(m["market_value"] for m in marks)
        if any(m["market_value"] < 0 for m in marks):
            raise ValueError("negative marked value")
        unknown_names = sorted(set(names) - mapping.keys())
        unknown = math.fsum(m["market_value"] for m in marks if m["instrument"] in unknown_names)
        cells = [math.fsum(m["market_value"] for m in marks
                          if mapping.get(m["instrument"]) == cell) for cell in range(20)]
        nav = p["end_nav"]
        compare(invested + p["cash"], nav)
        expected.append({
            "date": p["trade_date"], "mapping_asof": asof, "mapping_sha256": sha256_json(mapping),
            "invested_cny": invested, "cell_cny": cells, "unknown_cny": unknown,
            "cell_invested_weights": [v / invested if invested else None for v in cells],
            "unknown_invested_weight": unknown / invested if invested else None,
            "unknown_nav_weight": unknown / nav if nav else None,
            "cash_nav_weight": p["cash"] / nav if nav else None,
            "unknown_names": unknown_names, "unknown_held_count": len(unknown_names),
            "zero_value_held_names": sorted(m["instrument"] for m in marks
                                            if m["shares"] > 0 and m["market_value"] == 0),
        })
    compare(emitted, {
        "daily": expected, "sessions": len(expected),
        "mapping_policy": "immediately_previous_frozen_market_session_not_last_name_observation",
        "weight_denominator": "all_marked_invested_value_including_unknowns_cash_separate",
        "risk_neutrality_proven": False,
    })
    return {"exposure_arithmetic_verified": True, "sessions": len(expected)}
