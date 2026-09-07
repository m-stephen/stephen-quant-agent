"""Historical buy-ticket diagnostics, NOT a physical-share portfolio simulator.

Prices must be unadjusted CNY prices. Never convert an adjusted fractional-share
account into a dividend/split/rights ledger from an adjustment factor alone.
The bounded rule set is for ordinary SH/SZ A shares during 2023-2024 only.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import asdict, dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal


@dataclass(frozen=True)
class BuyRule:
    board: str
    minimum: int
    increment: int
    maximum: int


def buy_rule(instrument: str, trade_date: str) -> BuyRule:
    day = date.fromisoformat(trade_date)
    if not date(2023, 1, 1) <= day <= date(2024, 12, 31):
        raise ValueError("quantity rules are frozen for 2023-2024 only")
    match = re.fullmatch(r"(\d{6})(?:\.(SH|SZ|BJ))?", instrument)
    if not match:
        raise ValueError("unsupported instrument identifier")
    code, suffix = match.groups()
    if code.startswith("688") and suffix in (None, "SH"):
        return BuyRule("STAR", 200, 1, 100_000)
    if code.startswith(("600", "601", "603", "605")) and suffix in (None, "SH"):
        return BuyRule("SH_MAIN", 100, 100, 1_000_000)
    if code.startswith(("000", "001", "002", "003")) and suffix in (None, "SZ"):
        return BuyRule("SZ_MAIN", 100, 100, 1_000_000)
    if code.startswith(("300", "301")) and suffix in (None, "SZ"):
        return BuyRule("CHINEXT", 100, 100, 1_000_000)
    raise ValueError("board not covered by this historical rule set")


def _number(value, *, positive=False) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError("finite nonnegative value required")
    return result


def buy_ticket(notional, raw_price, rule: BuyRule) -> dict:
    """Round down ONE existing buy ticket, without reallocating residual money.

    This is a sizing diagnostic: not proof of limit-price validity, liquidity,
    cash availability, fills, settlement or subsequent portfolio performance.
    """
    budget, price = _number(notional), _number(raw_price, positive=True)
    if min(rule.minimum, rule.increment, rule.maximum) <= 0 or rule.maximum < rule.minimum:
        raise ValueError("invalid quantity rule")
    whole = min(int((budget / price).to_integral_value(rounding=ROUND_FLOOR)), rule.maximum)
    quantity = (
        0
        if whole < rule.minimum
        else (rule.minimum + (whole - rule.minimum) // rule.increment * rule.increment)
    )
    rounded = price * quantity
    return {
        "raw_quantity": quantity,
        "rounded_notional": float(rounded),
        "unallocated_notional": float(budget - rounded),
        "below_minimum": budget > 0 and quantity == 0,
        "single_ticket_maximum_bound": budget / price > rule.maximum,
        **asdict(rule),
    }


def minimum_commission_gap(executed_notional, commission_bps=6, minimum_cny=5) -> float:
    """Incremental commission on the SAME saved ticket, not a NAV correction."""
    absolute = _number(abs(executed_notional))
    rate, floor = _number(commission_bps), _number(minimum_cny)
    return float(max(Decimal(0), floor - absolute * rate / 10_000)) if absolute else 0.0


def audit_saved_account(
    periods: list[dict], prices: dict[tuple[str, str], dict]
) -> tuple[dict, list, list]:
    """No new targets, fits, trading simulation, yield estimate or stock filtering.

    Track adjustment changes on stocks actually held at the preceding close.
    A factor jump is a REVIEW KEY, not a parsed corporate action; its absence
    does not prove event completeness. Missing raw rows remain explicit.
    """
    if not periods or any(a["date"] >= b["date"] for a, b in itertools.pairwise(periods)):
        raise ValueError("nonempty strictly increasing account calendar required")
    totals = {
        "sessions": len(periods),
        "executed_tickets": 0,
        "buy_tickets": 0,
        "sell_tickets": 0,
        "unsupported_buy_tickets": 0,
        "missing_buy_prices": 0,
        "buy_notional_cny": 0.0,
        "supported_buy_notional_cny": 0.0,
        "rounded_buy_notional_cny": 0.0,
        "unallocated_buy_notional_cny": 0.0,
        "below_minimum_buy_tickets": 0,
        "maximum_bound_buy_tickets": 0,
        "commission_floor_tickets": 0,
        "extra_minimum_commission_cny": 0.0,
        "held_factor_change_keys": 0,
        "held_raw_missing_keys": 0,
        "held_prior_factor_missing_keys": 0,
    }
    tickets, review, held = [], [], set()
    boards = {}
    previous_date = None
    for p in periods:
        day = p["date"]
        if not "2023-01-01" <= day <= "2024-12-31":
            raise ValueError("account outside frozen diagnostic dates")
        for instrument in sorted(held):
            raw = prices.get((day, instrument))
            if raw is None:
                totals["held_raw_missing_keys"] += 1
                review.append({"date": day, "instrument": instrument, "reason": "held_raw_missing"})
            elif raw["previous_factor"] is None:
                totals["held_prior_factor_missing_keys"] += 1
                review.append(
                    {"date": day, "instrument": instrument, "reason": "prior_factor_missing"}
                )
            elif not math.isclose(raw["factor"], raw["previous_factor"], rel_tol=1e-10, abs_tol=0):
                totals["held_factor_change_keys"] += 1
                review.append(
                    {
                        "date": day,
                        "instrument": instrument,
                        "reason": "held_adjustment_change",
                        "factor": raw["factor"],
                        "previous_factor": raw["previous_factor"],
                        "previous_raw_date": raw["previous_date"],
                        "previous_account_date": previous_date,
                    }
                )
        for order in p["orders"]:
            n = order["executed_notional"]
            if not math.isfinite(n):
                raise ValueError("nonfinite saved order")
            if n == 0:
                continue
            totals["executed_tickets"] += 1
            gap = minimum_commission_gap(n)
            totals["extra_minimum_commission_cny"] += gap
            totals["commission_floor_tickets"] += int(gap > 0)
            if n < 0:
                totals["sell_tickets"] += 1
                continue  # Odd-lot selling needs a true raw-share inventory: not inferred here.
            totals["buy_tickets"] += 1
            totals["buy_notional_cny"] += n
            instrument = order["instrument"]
            raw = prices.get((day, instrument))
            if raw is None:
                totals["missing_buy_prices"] += 1
                tickets.append(
                    {"date": day, "instrument": instrument, "status": "MISSING_RAW_PRICE"}
                )
                continue
            try:
                rule = buy_rule(instrument, day)
            except ValueError:
                totals["unsupported_buy_tickets"] += 1
                tickets.append(
                    {"date": day, "instrument": instrument, "status": "UNSUPPORTED_RULE"}
                )
                continue
            ticket = buy_ticket(n, raw["open"], rule)
            tickets.append(
                dict(date=day, instrument=instrument, status="DIAGNOSTIC_ONLY", **ticket)
            )
            totals["supported_buy_notional_cny"] += n
            totals["rounded_buy_notional_cny"] += ticket["rounded_notional"]
            totals["unallocated_buy_notional_cny"] += ticket["unallocated_notional"]
            totals["below_minimum_buy_tickets"] += int(ticket["below_minimum"])
            totals["maximum_bound_buy_tickets"] += int(ticket["single_ticket_maximum_bound"])
            boards[rule.board] = boards.get(rule.board, 0) + 1
        held = {m["instrument"] for m in p["positions"] if m["shares"] > 0}
        previous_date = day
    totals["board_buy_counts"] = boards
    base = totals["supported_buy_notional_cny"]
    totals["unallocated_buy_fraction"] = (
        totals["unallocated_buy_notional_cny"] / base if base else None
    )
    totals["physical_execution_verified"] = False
    totals["validated_alpha"] = False
    totals["minimum_commission_cny_assumption"] = 5
    totals["minimum_commission_is_broker_confirmed"] = False
    totals["interpretation"] = "SAME_SAVED_TICKETS_ONLY_NOT_A_PORTFOLIO_REPLAY_OR_NAV_ADJUSTMENT"
    return totals, tickets, review
