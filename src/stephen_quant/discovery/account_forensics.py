"""Read-only calculations on saved accounts; never predicts or executes trades.

Events describe the producer's valuation policy, not verified corporate events.
Recovery is a retrospective valuation change, not necessarily a cash receipt.
"""

from __future__ import annotations

import math
from datetime import date

ZERO_MARK = "conservative_zero_writeoff"
MARK_SOURCES = {ZERO_MARK, "explicit_stale_last_close", "current_close"}


def finite(value, *, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite numeric ledger value required")
    if nonnegative and value < 0:
        raise ValueError("nonnegative ledger value required")
    return float(value)


def close(actual, expected):
    if not math.isclose(finite(actual), finite(expected), rel_tol=1e-10, abs_tol=1e-6):
        raise ValueError("saved ledger amount does not reconcile")


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("canonical ISO date required")
    if not "2022-01-01" <= value <= "2024-12-31":
        raise ValueError("forensics is restricted to frozen2022–2024")
    return value


def index_rows(rows):
    indexed = {}
    for row in rows:
        name = row["instrument"]
        if not isinstance(name, str) or not name or name in indexed:
            raise ValueError("unique nonempty instrument per period required")
        indexed[name] = row
    return indexed


def marks_index(rows):
    marks = index_rows(rows)
    for mark in marks.values():
        if mark["source"] not in MARK_SOURCES:
            raise ValueError("unrecognized saved valuation source")
        for key in ("shares", "mark_price", "market_value"):
            finite(mark[key], nonnegative=True)
        if type(mark["stale_sessions"]) is not int or mark["stale_sessions"] < 0:
            raise ValueError("nonnegative integer stale age required")
        stale = mark["stale_sessions"]
        if ((mark["source"] == "current_close" and stale != 0)
                or (mark["source"] == "explicit_stale_last_close" and not 1 <= stale < 20)
                or (mark["source"] == ZERO_MARK and stale < 20)):
            raise ValueError("valuation source and stale age contradict frozen policy")
        close(mark["market_value"], mark["shares"] * mark["mark_price"])
        if mark["source"] == ZERO_MARK and mark["mark_price"] != 0:
            raise ValueError("written-down mark must be zero")
    return marks


def extract_events(account, report):
    """Keep (account,date,instrument,type), including identities shared by accounts.

    Recovery open prices are absent from producer orders. Preserve their daily
    aggregate without inventing a per-instrument allocation; source tracing must
    supply and verify those values separately. No loss is added back to NAV.
    """
    if not isinstance(account, str) or not account:
        raise ValueError("explicit account identity required")
    limit = report["config"]["stale_writeoff_sessions"]
    if type(limit) is not int or limit != 20:
        raise ValueError("frozen stale20 policy required")
    events, daily = [], []
    previous, last_day = {}, None
    previous_nav = finite(report["metrics"]["initial_nav"], nonnegative=True)
    if previous_nav <= 0:
        raise ValueError("positive initial NAV required")
    for period in report["periods"]:
        current_day = day(period["trade_date"])
        if last_day is not None and current_day <= last_day:
            raise ValueError("unique increasing account dates required")
        current = marks_index(period["marks"])
        orders = index_rows(period["orders"])
        losses, recoveries = [], []
        for name, mark in current.items():
            prior = previous.get(name)
            if mark["source"] == ZERO_MARK and (prior is None or prior["source"] != ZERO_MARK):
                if prior is None or prior["stale_sessions"] != limit - 1:
                    raise ValueError("new writeoff requires prior stale19 evidence")
                if mark["stale_sessions"] != limit:
                    raise ValueError("new writeoff must occur at frozen stale limit")
                close(mark["shares"], prior["shares"])
                losses.append({
                    "account": account, "date": current_day, "instrument": name,
                    "event_type": "writeoff", "amount_cny": prior["market_value"],
                    "prior_shares": prior["shares"], "prior_mark_price": prior["mark_price"],
                    "prior_date": last_day, "stale_sessions": mark["stale_sessions"],
                    "source_classification": "unknown", "actual_delisting_verified": False,
                })
        for name, prior in previous.items():
            if prior["source"] != ZERO_MARK:
                continue
            mark = current.get(name)
            if mark is not None and mark["source"] == ZERO_MARK:
                continue
            if mark is not None and mark["source"] != "current_close":
                raise ValueError("zero-mark recovery requires current bar evidence")
            if mark is None and (name not in orders or orders[name]["executed_notional"] >= 0):
                raise ValueError("disappearing zero-mark shares require recorded disposal")
            recoveries.append({
                "account": account, "date": current_day, "instrument": name,
                "event_type": "recovery", "amount_cny": None,
                "amount_status": "requires_frozen_source_open_price",
                "prior_shares": prior["shares"], "prior_date": last_day,
                "disposed_by_close": mark is None,
                "source_classification": "unknown", "retrospective_only": True,
            })
        for key, rows in (("writeoff_positions", losses), ("recovery_positions", recoveries)):
            if type(period[key]) is not int or period[key] != len(rows):
                raise ValueError("all per-account daily event identities must reconcile")
        close(sum(e["amount_cny"] for e in losses), period["writeoff_loss"])
        recovery = finite(period["recovery_value"], nonnegative=True)
        if not recoveries:
            close(recovery, 0)
        close(period["previous_nav"], previous_nav)
        close(period["cash"] + sum(m["market_value"] for m in current.values()), period["end_nav"])
        close(period["end_nav"] / previous_nav - 1, period["net_return"])
        close(sum(finite(o["total_cost"], nonnegative=True) for o in orders.values()),
              period["total_cost"])
        close(sum(abs(finite(o["executed_notional"])) for o in orders.values()),
              period["traded_notional_cny"])
        daily.append({
            "date": current_day, "writeoff_count": len(losses), "recovery_count": len(recoveries),
            "writeoff_cny": period["writeoff_loss"], "recovery_cny": recovery,
        })
        events.extend(losses + recoveries)
        previous, last_day, previous_nav = current, current_day, period["end_nav"]
    if not daily:
        raise ValueError("complete nonempty account required")
    for metric, field in (("writeoff_events", "writeoff_count"),
                          ("recovery_events", "recovery_count"),
                          ("writeoff_loss", "writeoff_cny"), ("recovery_value", "recovery_cny")):
        close(sum(row[field] for row in daily), report["metrics"][metric])
    close(previous_nav, report["metrics"]["final_nav"])
    return {"account": account, "events": events, "daily": daily,
            "event_count": len(events), "counterfactual_nav_generated": False}


def exposure(period, mapping, *, mapping_asof):
    """All invested value is denominator, including unknowns; cash/NAV also explicit."""
    current_day, asof = day(period["trade_date"]), day(mapping_asof)
    if asof > current_day:
        raise ValueError("future cell mappings cannot explain decision-time exposure")
    for value in mapping.values():
        if type(value) is not int or not 0 <= value < 20:
            raise ValueError("cell index must be integer0..19; omit unknown keys")
    cells, unknown = [0.0] * 20, 0.0
    marks = marks_index(period["marks"])
    for name, mark in marks.items():
        if name in mapping:
            cells[mapping[name]] += mark["market_value"]
        else:
            unknown += mark["market_value"]
    invested = sum(cells) + unknown
    nav = finite(period["end_nav"], nonnegative=True)
    close(invested + finite(period["cash"], nonnegative=True), nav)
    return {
        "date": current_day, "mapping_asof": asof, "invested_cny": invested,
        "cell_cny": cells, "unknown_cny": unknown,
        "cell_invested_weights": [v / invested if invested else None for v in cells],
        "unknown_invested_weight": unknown / invested if invested else None,
        "unknown_nav_weight": unknown / nav if nav else None,
        "cash_nav_weight": period["cash"] / nav if nav else None,
        "unknown_names": sorted(set(marks) - set(mapping)),
    }
