"""Independent streaming mathematical reference for the frozen response contract.

No production reader, bridge, response fit, ranker, predictor or execution engine
is imported. This reimplements the disclosed model, not exchange/broker rules or
the truth of vendor first-seen timestamps. Only hashes share a serialization helper.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from itertools import groupby

import numpy as np

from .search_power_dsl import sha256_json

FIELDS = (
    "volatility_20",
    "ret_20",
    "liquidity",
    "flow_ratio",
    "close_return",
    "flow_surprise",
    "standardized_own_return",
    "price_response_residual",
)


def clock(day, time):
    return datetime.fromisoformat(f"{day}T{time}+08:00")


def visible(value, day):
    if value is None:
        return None
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("reference requires explicit aware availability")
    return result if result <= clock(day, "23:59:59") else None


def finite(value, *, minimum=0, strict=False):
    return (
        value is not None
        and math.isfinite(value)
        and (value > minimum if strict else value >= minimum)
    )


def validate_days(calendar):
    if (
        not calendar
        or list(calendar) != sorted(set(calendar))
        or any(
            not isinstance(d, str)
            or date.fromisoformat(d).isoformat() != d
            or not "2022-01-01" <= d <= "2024-12-31"
            for d in calendar
        )
    ):
        raise ValueError("reference requires explicit unique 2022-24 calendar")


def date_groups(rows):
    previous = ("", "")
    for day, group in groupby(rows, key=lambda r: str(r["trade_date"])):
        result = {}
        for row in group:
            name = row["instrument"]
            if (
                not isinstance(name, str)
                or not name
                or name.strip() != name
                or (day, name) <= previous
            ):
                raise ValueError("reference source requires ordered unique date/instrument keys")
            previous = day, name
            result[name] = row
        yield day, result


def reference_ranks(features):
    """Independent tie-aware current-cell ranks; no production rank helper."""
    names = [n for n, f in features.items() if all(math.isfinite(f[k]) for k in FIELDS)]
    ordered = sorted(names, key=lambda n: (features[n]["volatility_20"], n))
    vol_bins, cells = defaultdict(list), defaultdict(list)
    for i, name in enumerate(ordered):
        vol_bins[i * 5 // len(ordered)].append(name)
    for v, members in vol_bins.items():
        adv_order = sorted(members, key=lambda n: (features[n]["liquidity"], n))
        for i, name in enumerate(adv_order):
            cells[4 * v + i * 4 // len(adv_order)].append(name)
    result = {}
    for c, members in cells.items():
        for n in members:
            result[n] = {"cell": c, "ranks": {}, "vol": features[n]["volatility_20"]}
        for field in FIELDS:
            order = sorted(members, key=lambda n: (features[n][field], n))
            first = 0
            while first < len(order):
                end = first + 1
                while (
                    end < len(order)
                    and features[order[end]][field] == features[order[first]][field]
                ):
                    end += 1
                rank = (first + 1 + end) / (len(order) + 1) - 1
                for n in order[first:end]:
                    result[n]["ranks"][field] = rank
                first = end
    return result


def opening_flags(instrument, display, opening, prior):
    """Frozen B3 daily-bar proxy, not an assertion about executable exchange orders."""
    if prior is None or not display:
        return False, False, "missing_metadata"
    normalized = "".join(display.strip().upper().split())
    if normalized.startswith(("N", "C")):
        return True, True, "no_price_limit"
    code, _, exchange = instrument.partition(".")
    exchange = exchange or ("SH" if code.startswith("6") else "BJ" if code[0] in "48" else "SZ")
    if exchange == "BJ" or code.startswith(("4", "8")):
        rate = "0.30"
    elif code.startswith(("300", "301", "688", "689")):
        rate = "0.20"
    elif (exchange == "SH" and code.startswith(("600", "601", "603", "605"))) or (
        exchange == "SZ" and code.startswith(("000", "001", "002", "003"))
    ):
        rate = "0.05" if "ST" in normalized else "0.10"  # Only2022-24 scope.
    else:
        return False, False, "unsupported_board"
    r, p, tick = Decimal(rate), Decimal(str(prior)), Decimal("0.01")
    lo, hi = [(p * x).quantize(tick, rounding=ROUND_HALF_UP) for x in (1 - r, 1 + r)]
    op = Decimal(str(opening)).quantize(tick, rounding=ROUND_HALF_UP)
    if op < lo or op > hi:
        return False, False, "uncertain_price_limit_reference"
    if op == hi:
        return False, True, "open_at_upper_limit"
    if op == lo:
        return True, False, "open_at_lower_limit"
    return True, True, "normal"


def reference_history(daily_rows, flow_rows, calendar):
    """Yield each day's models/ranks/bars with at most60 observations per instrument.

    Input iterators must have unique sorted keys. No future stock presence chooses
    historical fits. Invalid or unavailable observations reset consecutive windows.
    """
    validate_days(calendar)
    daily_stream, flow_stream = iter(date_groups(daily_rows)), iter(date_groups(flow_rows))
    daily, flow = next(daily_stream, None), next(flow_stream, None)
    previous_close, previous_risk, response_windows, price_windows = {}, {}, {}, {}
    for i, day in enumerate(calendar):
        if daily is None or daily[0] != day or (flow and flow[0] < day):
            raise ValueError("reference source calendar mismatch")
        d, f = daily[1], flow[1] if flow and flow[0] == day else {}
        if set(f) - set(d):
            raise ValueError("reference orphan flow key")
        # First compute past-only response statistics; current values never select models.
        models = {}
        if 61 <= i < len(calendar) - 1:
            for n, window in response_windows.items():
                if (
                    len(window) != 60
                    or window[0]["session"] != i - 60
                    or window[-1]["session"] != i - 1
                ):
                    continue
                matrix = np.asarray([[o["flow_ratio"], o["close_return"]] for o in window])
                mu, sd = matrix.mean(axis=0), matrix.std(axis=0)
                if not np.isfinite(matrix).all() or not np.isfinite(sd).all() or min(sd) <= 1e-12:
                    continue
                z = (matrix - mu) / sd
                beta = float(z[:, 0] @ z[:, 1] / 60 / 1.01)
                models[n] = {
                    "flow_mean": float(mu[0]),
                    "return_mean": float(mu[1]),
                    "flow_std": float(sd[0]),
                    "return_std": float(sd[1]),
                    "slope": beta,
                    "first_session": i - 60,
                    "last_session": i - 1,
                    "last_observed_at": window[-1]["observed_at"],
                    "last_available_at": max(
                        window, key=lambda o: datetime.fromisoformat(o["available_at"])
                    )["available_at"],
                    "observation_sha256": sha256_json(list(window)),
                }
            if not models:
                raise ValueError("reference has no identifiable prior response models")
        current, risk, bars = {}, {}, {}
        for n, raw in d.items():
            prior_close = previous_close.pop(n, None)
            at = visible(raw["available_at"], day)
            if at is None:
                price_windows.pop(n, None)
                previous_risk.pop(n, None)
                continue
            close, factor, amount = [
                None if raw[k] is None else float(raw[k])
                for k in ("close", "adjustment_factor", "amount")
            ]
            if finite(close, strict=True) and finite(factor, strict=True):
                adjusted = close * factor
                if not math.isfinite(adjusted):
                    raise ValueError("reference nonfinite adjusted price")
                previous_close[n] = i, adjusted, max(at, clock(day, "15:00:00"))
                source_flow = f.get(n)
                flow_at = visible(source_flow["available_at"], day) if source_flow else None
                if prior_close and prior_close[0] == i - 1 and flow_at is not None:
                    net = source_flow["net_inflow_amount"]
                    if net is not None:
                        net = float(net)
                    if (
                        finite(amount, strict=True)
                        and net is not None
                        and math.isfinite(net)
                        and math.isfinite(amount * 1000)
                    ):
                        ratio, ret = net / (amount * 1000), adjusted / prior_close[1] - 1
                        if math.isfinite(ratio) and math.isfinite(ret) and ret > -1:
                            current[n] = {
                                "asset": n,
                                "session": i,
                                "observed_at": clock(day, "15:00:00").isoformat(),
                                "available_at": max(
                                    clock(day, "15:00:00"), at, flow_at, prior_close[2]
                                ).isoformat(),
                                "flow_ratio": ratio,
                                "close_return": ret,
                            }
            if not (finite(close, strict=True) and finite(factor, strict=True) and finite(amount)):
                price_windows.pop(n, None)
                previous_risk.pop(n, None)
                continue
            adjusted, turnover = close * factor, amount * 1000
            if not math.isfinite(turnover):
                raise ValueError("reference nonfinite turnover")
            previous = previous_risk.get(n)
            past = price_windows.setdefault(n, deque(maxlen=60))
            if past and past[-1][0] != i - 1:
                past.clear()
            op = None if raw["open"] is None else float(raw["open"])
            if finite(op, strict=True) and math.isfinite(op * factor):
                buy, sell, reason = opening_flags(
                    n, raw["name"], op, previous[1] if previous else None
                )
                volume = None if raw["volume"] is None else float(raw["volume"])
                if not finite(volume, strict=True) or amount <= 0:
                    buy, sell, reason = False, False, "no_reported_trades"
                bars[n] = {
                    "trade_date": day,
                    "instrument": n,
                    "open_price": op * factor,
                    "close_price": adjusted,
                    "capacity_cny": previous[2] * 0.05
                    if previous and previous[0] == i - 1
                    else 0.0,
                    "capacity_available_at": f"{day}T08:00:00+08:00",
                    "can_buy_open": buy,
                    "can_sell_open": sell,
                    "forced_exit": False,
                    "tradability_reason": reason,
                }
            past.append((i, adjusted, turnover))
            adv = math.fsum(x[2] for x in past) / len(past)
            previous_risk[n] = i, close, adv
            if len(past) >= 21 and adv >= 1e7 and raw["name"] and "ST" not in raw["name"].upper():
                prices = np.asarray([x[1] for x in list(past)[-21:]])
                risk[n] = {
                    "volatility_20": float(np.std(np.log(prices[1:] / prices[:-1]), ddof=1)),
                    "ret_20": float(prices[-1] / prices[0] - 1),
                    "liquidity": adv,
                }
        if not bars:
            raise ValueError("reference empty visible session")
        features = {}
        for n in models.keys() & current.keys() & risk.keys():
            m, o = models[n], current[n]
            x, y = (
                (o["flow_ratio"] - m["flow_mean"]) / m["flow_std"],
                (o["close_return"] - m["return_mean"]) / m["return_std"],
            )
            features[n] = {
                **risk[n],
                "flow_ratio": o["flow_ratio"],
                "close_return": o["close_return"],
                "flow_surprise": x,
                "standardized_own_return": y,
                "price_response_residual": y - m["slope"] * x,
            }
        yield (
            day,
            {
                "models": models,
                "features": features,
                "ranks": reference_ranks(features),
                "bars": bars,
            },
        )
        for n, o in current.items():
            window = response_windows.setdefault(n, deque(maxlen=60))
            if window and window[-1]["session"] != i - 1:
                window.clear()
            window.append(o)
        daily = next(daily_stream, None)
        if flow and flow[0] == day:
            flow = next(flow_stream, None)
    if daily or flow:
        raise ValueError("reference source outside complete calendar")
