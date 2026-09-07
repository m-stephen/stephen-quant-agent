"""Visible daily risk/eligibility and source-adjusted execution bars.

Unlike the inherited row-window bridge, risk histories cannot compress global
session gaps. A missing immediately preceding ADV leaves zero opening capacity.
These conservative differences must be declared, not called an exact old replay.
"""

from __future__ import annotations

import math
from collections import Counter, deque
from itertools import pairwise
from statistics import fmean, stdev

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.flow_response import aware
from stephen_quant.discovery.flow_response_series import clock, timestamp, validate_calendar

from .qd_csv_adapter import _open_tradability

VERSION = "11.21-response-panel-1"


def _finite(value, *, positive=False):
    return value is not None and math.isfinite(value) and (value > 0 if positive else value >= 0)


def build_response_panel(daily_rows, calendar):
    validate_calendar(calendar)
    by_date = {d: {} for d in calendar}
    for row in daily_rows:
        dt, name = row["trade_date"], row["instrument"]
        if dt not in by_date or not isinstance(name, str) or not name or name.strip() != name:
            raise ValueError("daily panel key outside explicit calendar")
        if name in by_date[dt]:
            raise ValueError("duplicate daily panel key")
        by_date[dt][name] = row
    history, previous, risks, bars, quality = {}, {}, {}, {}, Counter()
    for i, dt in enumerate(calendar):
        risks[dt], bars[dt] = {}, {}
        for name, row in sorted(by_date[dt].items()):
            # Exclude before any numeric inspection, and never retroactively backfill.
            if row["available_at"] is None or timestamp(row["available_at"]) > aware(
                clock(dt, "23:59:59")
            ):
                history.pop(name, None)
                previous.pop(name, None)
                quality["daily_not_available"] += 1
                continue
            close, factor, amount = row["close"], row["adjustment_factor"], row["amount"]
            if not all(_finite(v, positive=True) for v in (close, factor)) or not _finite(amount):
                history.pop(name, None)
                previous.pop(name, None)
                quality["invalid_daily_history"] += 1
                continue
            adjusted, amount_cny = close * factor, amount * 1000
            if not math.isfinite(adjusted) or not math.isfinite(amount_cny):
                raise ValueError("nonfinite adjusted price or CNY turnover")
            prior = previous.get(name)
            past = history.setdefault(name, deque(maxlen=60))
            if past and past[-1][0] != i - 1:
                past.clear()
            capacity = prior[3] * 0.05 if prior and prior[0] == i - 1 else 0.0
            op, volume, display = row["open"], row["volume"], row["name"]
            if _finite(op, positive=True) and math.isfinite(op * factor):
                buy = sell = False
                reason = "missing_metadata"
                if prior and display:
                    code = (
                        name
                        if "." in name
                        else name
                        + (".SH" if name.startswith("6") else ".BJ" if name[0] in "48" else ".SZ")
                    )
                    try:
                        buy, sell, reason = _open_tradability(code, display, dt, op, prior[1])
                    except ValueError:
                        reason = "unsupported_board"
                    if reason == "no_price_limit_inferred":
                        buy = sell = False
                        reason = "uncertain_price_limit_reference"
                if not _finite(volume, positive=True) or amount <= 0:
                    buy = sell = False
                    reason = "no_reported_trades"
                bars[dt][name] = StatefulBar(
                    dt,
                    name,
                    op * factor,
                    adjusted,
                    capacity,
                    clock(dt, "08:00:00"),
                    buy,
                    sell,
                    False,
                    reason,
                )
                quality[reason] += 1
            else:
                quality["invalid_bar_accounted_as_missing"] += 1
            past.append((i, adjusted, amount_cny))
            adv = fmean(x[2] for x in past)
            previous[name] = (i, close, adjusted, adv)
            if len(past) < 21 or adv < 10_000_000 or not display or "ST" in display.upper():
                quality["risk_ineligible"] += 1
                continue
            prices = [x[1] for x in list(past)[-21:]]
            logs = [math.log(b / a) for a, b in pairwise(prices)]
            risks[dt][name] = {
                "volatility_20": stdev(logs),
                "ret_20": prices[-1] / prices[0] - 1,
                "liquidity": adv,
            }
        if not bars[dt]:
            raise ValueError("empty visible market session; no fabricated execution calendar")
    return risks, bars, dict(quality)
