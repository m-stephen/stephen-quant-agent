"""Reconcile saved positions/orders across a complete frozen calendar.

This is an accounting identity check, not another execution of a trading policy.
It never changes orders, imputes prices or constructs a counterfactual NAV.
"""

import math

from .account_forensics import (
    ZERO_MARK,
    close,
    day,
    extract_events,
    finite,
    index_rows,
    marks_index,
)


def _shares(actual, expected):
    if not math.isclose(finite(actual), finite(expected), rel_tol=1e-10, abs_tol=1e-9):
        raise ValueError("saved share delta does not reconcile")


def reconcile_chain(account, report, *, calendar, saved_bars):
    """Require explicit complete date mappings; absent instrument means looked-up absence.

    The caller must supply a byte-bound history and exact frozen calendar. Every
    date must be present; `.get(date,{})` would fabricate a whole missing session.
    Source truth remains separate: saved bars alone can only explain accounting.
    """
    dates = [day(dt) for dt in calendar]
    if not dates or dates != sorted(set(dates)):
        raise ValueError("complete ordered unique execution calendar required")
    if [p["trade_date"] for p in report["periods"]] != dates:
        raise ValueError("saved account differs from exact frozen execution calendar")
    if any(dt not in saved_bars for dt in dates):
        raise ValueError("history date absent; cannot fabricate missing session")
    extracted = extract_events(account, report)
    indexed_events = {(e["date"], e["instrument"], e["event_type"]): e
                      for e in extracted["events"]}
    if len(indexed_events) != len(extracted["events"]):
        raise ValueError("duplicate per-account event identity")
    previous, missing_chains, traces = {}, {}, []
    previous_cash = finite(report["metrics"]["initial_nav"], nonnegative=True)
    last_date = None
    config = report["config"]
    rates = {k: finite(config[k], nonnegative=True)
             for k in ("commission_bps", "sell_tax_bps", "slippage_bps")}
    total_cost = 0.0
    for period in report["periods"]:
        dt = period["trade_date"]
        current, orders = marks_index(period["marks"]), index_rows(period["orders"])
        bars, open_values = saved_bars[dt], {}
        recoveries, losses = [], []
        for name in sorted(previous.keys() | current.keys() | orders.keys()):
            prior, mark, order, bar = (previous.get(name), current.get(name), orders.get(name),
                                       bars.get(name))
            before = prior["shares"] if prior else 0.0
            notional = finite(order["executed_notional"]) if order else 0.0
            if order:
                cost = abs(notional) * (rates["commission_bps"] + rates["slippage_bps"]
                                       + (rates["sell_tax_bps"] if notional < 0 else 0)) / 10000
                close(order["total_cost"], cost)
            if bar is not None:
                if bar["trade_date"] != dt or bar["instrument"] != name:
                    raise ValueError("history bar identity mismatch")
                op, cp = finite(bar["open_price"]), finite(bar["close_price"])
                if op <= 0 or cp <= 0:
                    raise ValueError("positive saved execution prices required")
                open_values[name] = before * op
                after, stale, source = before + notional / op, 0, "current_close"
                mark_price = cp
                if prior and prior["source"] == ZERO_MARK:
                    event = indexed_events.get((dt, name, "recovery"))
                    if event is None:
                        raise ValueError("saved recovery identity absent despite recovered bar")
                    value = before * op
                    recoveries.append(value)
                    traces.append({**event, "saved_bar_recovery_cny": value,
                                   "saved_bar_open_price": op,
                                   "source_recovery_cny": None,
                                   "source_recovery_status": "REQUIRES_FROZEN_SOURCE_LOOKUP",
                                   "stale_chain": missing_chains[name],
                                   "recovery_order": dict(order) if order else None,
                                   "recovery_end_mark": dict(mark) if mark else None})
                missing_chains.pop(name, None)
            else:
                if notional != 0:
                    raise ValueError("executed order without saved bar")
                after = before
                if prior is None:
                    if mark is not None:
                        raise ValueError("position appeared without bar or prior shares")
                    continue
                stale = prior["stale_sessions"] + 1
                source = ZERO_MARK if stale >= 20 else "explicit_stale_last_close"
                mark_price = 0.0 if stale >= 20 else prior["mark_price"]
                open_values[name] = before * mark_price
                if name not in missing_chains:
                    if prior["stale_sessions"] != 0:
                        raise ValueError("missing initial stale-chain history")
                    missing_chains[name] = {
                        "last_marked_date": last_date, "last_mark_price": prior["mark_price"],
                        "prior_shares": before, "missing_sessions": [],
                    }
                missing_chains[name]["missing_sessions"].append({
                    "date": dt, "stale_sessions": stale, "saved_bar_present": False})
                if stale == 20:
                    event = indexed_events.get((dt, name, "writeoff"))
                    if event is None:
                        raise ValueError("saved writeoff identity absent despite stale20")
                    value = before * prior["mark_price"]
                    close(value, event["amount_cny"])
                    losses.append(value)
                    chain = missing_chains[name]
                    traces.append({**event, "stale_chain": {
                        **chain, "missing_sessions": list(chain["missing_sessions"])}})
            if after > 1e-12:
                if mark is None:
                    raise ValueError("positive shares disappeared from saved close")
                _shares(mark["shares"], after)
                if mark["source"] != source or mark["stale_sessions"] != stale:
                    raise ValueError("saved mark contradicts complete stale/bar chain")
                close(mark["mark_price"], mark_price)
            elif mark is not None or after < -1e-9:
                raise ValueError("invalid saved disposal or negative remaining shares")
        close(previous_cash + sum(open_values.values()), period["open_nav"])
        close(period["open_nav"] / period["previous_nav"] - 1, period["overnight_mark_return"])
        close(sum(losses), period["writeoff_loss"])
        close(sum(recoveries), period["recovery_value"])
        if len(losses) != period["writeoff_positions"] or len(recoveries) != period["recovery_positions"]:
            raise ValueError("full-chain event totals disagree")
        cash = previous_cash - sum(finite(o["executed_notional"]) for o in orders.values()) \
            - finite(period["total_cost"], nonnegative=True)
        if cash < -1e-7:
            raise ValueError("saved orders imply invalid negative cash")
        close(max(cash, 0.0), period["cash"])
        if sum(m["stale_sessions"] > 0 for m in current.values()) != period["stale_position_days"]:
            raise ValueError("stale position-day count mismatch")
        total_cost += period["total_cost"]
        previous, previous_cash, last_date = current, period["cash"], dt
    close(total_cost, report["metrics"]["total_cost"])
    if len(traces) != len(indexed_events):
        raise ValueError("incomplete event chain coverage")
    return {"account": account, "sessions_checked": len(dates), "saved_account_reconciled": True,
            "ledger_chain_pass": True, "source_explanation_status": "REQUIRES_FROZEN_SOURCE_LOOKUP",
            "events": sorted(traces, key=lambda e: (e["date"], e["instrument"], e["event_type"])),
            "open_stale_chains": [
                {"account": account, "instrument": name, "through_date": dates[-1],
                 "written_down_at_end": previous[name]["source"] == ZERO_MARK,
                 "stale_chain": chain}
                for name, chain in sorted(missing_chains.items())],
            "source_truth_verified": False, "new_accounts": 0, "counterfactual_nav_generated": False}
