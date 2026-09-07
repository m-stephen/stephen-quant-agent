"""Counted immutable old-target replay and independent account reconciliation."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_protocol import COSTS, plans
from .gross_net_attribution import frozen_targets
from .search_power_dsl import sha256_json


def load_original_targets(registry, tids, *, original_tree, card_sha256, calendar):
    """Read original target values only after all four old-anchor Trials exist."""
    if len(calendar) < 2 or calendar != sorted(set(calendar)):
        raise ValueError("complete ordered development calendar required")
    for p in plans():
        if p["role"] == "feature_provider" or not p["response_policy"].startswith("original_"):
            continue
        tid = tids[p["key"]]
        if registry.fit_lineage(tid)["stages"] or registry.feature_sources(tid)["providers"]:
            raise ValueError("original anchors require explicit no-new-fit/no-provider contracts")
        with registry.connect() as conn:
            row = conn.execute(
                "SELECT hyperparams,result_json FROM trials WHERE trial_id=?", (tid,)
            ).fetchone()
        if row[1] is not None or any(json.loads(row[0]).get(k) != v for k, v in p.items()):
            raise ValueError("original anchor replay requires unchanged uncompleted Trials")
    root = Path(original_tree).resolve(strict=True)
    card_path = root / "configs/v11.11-frozen-stability-observation.json"
    if root not in card_path.resolve(strict=True).parents or file_sha(card_path) != card_sha256:
        raise ValueError("original frozen anchor card changed")
    card = json.loads(card_path.read_bytes())
    targets, proofs = {}, {}
    for policy, old_name in (("original_lowvol", "lowvol"), ("original_stable", "stable_lowrisk")):
        path = root / f"artifacts/temporal-increments/epoch-001/targets/{old_name}.json"
        if (
            root not in path.resolve(strict=True).parents
            or file_sha(path) != card["targets_file_sha256"][old_name]
        ):
            raise ValueError("original anchor target bytes changed")
        raw = path.read_bytes()
        values = json.loads(raw)
        targets[policy] = frozen_targets(
            values, card["targets_canonical_sha256"][old_name], calendar
        )
        proofs[policy] = {
            "original_name": old_name,
            "file_sha256": file_sha(path),
            "canonical_sha256": sha256_json(values),
            "target_bytes": raw,
        }
    return targets, proofs


def _near(actual, expected, why, *, atol=1e-5):
    if (
        not math.isfinite(actual)
        or not math.isfinite(expected)
        or not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=atol)
    ):
        raise ValueError(f"independent account mismatch: {why}")


def audit_response_account(report, sessions, targets, *, roundtrip_bps, mode="target_changes"):
    """Reconstruct holdings/cash/marks from saved fills and supplied source bars.

    No execution-engine, target-generator or summary function is called. Orders
    are independently checked against target-change intent, opening information,
    capacity and analytic funding allocation under the frozen linear fee model.
    Raw-source and target-selection correctness remain separate responsibilities.
    """
    if type(roundtrip_bps) is not int or roundtrip_bps not in COSTS:
        raise ValueError("registered82/164bps audit required")
    if mode not in ("target_changes", "full_target"):
        raise ValueError("registered account mode required")
    cfg = report.config
    scale = roundtrip_bps / 41
    if (
        cfg.rebalance_mode != mode
        or cfg.maximum_position_weight != 0.025
        or cfg.stale_writeoff_sessions != 20
        or cfg.commission_bps != 3 * scale
        or cfg.sell_tax_bps != 5 * scale
        or cfg.slippage_bps != 15 * scale
        or report.metrics.initial_nav != 3_000_000
        or not report.periods
        or len(report.periods) != len(sessions)
        or len(sessions) != len(targets)
    ):
        raise ValueError("frozen account configuration/calendar mismatch")
    nav = cash = peak = 3_000_000.0
    shares, last_close, stale = {}, {}, {}
    costs, traded, tickets, drawdowns, returns, annual = 0.0, 0.0, 0, [], [], {}
    residual = 0.0
    totals = dict.fromkeys(
        (
            "blocked_notional",
            "stale_position_days",
            "writeoff_events",
            "writeoff_loss",
            "recovery_events",
            "recovery_value",
        ),
        0.0,
    )
    previous_date = ""
    pending, declared = set(), {}
    for day, bars, target in zip(report.periods, sessions, targets, strict=True):
        dt = day.trade_date
        by_name = {b.instrument: b for b in bars}
        if len(by_name) != len(bars):
            raise ValueError("duplicate source bar in independent account audit")
        if (
            not previous_date < dt
            or dt != target.trade_date
            or any(b.trade_date != dt for b in bars)
            or len(by_name) != len(bars)
            or dt[:4] not in {"2023", "2024"}
        ):
            raise ValueError("independent account global calendar mismatch")
        decision = datetime.fromisoformat(target.decided_at)
        if decision.tzinfo is None or decision >= datetime.fromisoformat(dt + "T09:30:00+08:00"):
            raise ValueError("target not known before opening execution")
        if sum(target.weights.values()) > 1 + 1e-10 or any(
            not math.isfinite(w) or not 0 <= w <= 0.025 for w in target.weights.values()
        ):
            raise ValueError("target exceeds frozen risk budget")
        _near(day.previous_nav, nav, "previous NAV")
        losses = {
            n: q * last_close[n]
            for n, q in shares.items()
            if q > 1e-12 and n not in by_name and stale.get(n, 0) == 19
        }
        recoveries = {
            n: q * by_name[n].open_price
            for n, q in shares.items()
            if q > 1e-12 and n in by_name and stale.get(n, 0) >= 20
        }
        _near(day.writeoff_positions, len(losses), "writeoff count", atol=0)
        _near(day.writeoff_loss, sum(losses.values()), "writeoff loss")
        _near(day.recovery_positions, len(recoveries), "recovery count", atol=0)
        _near(day.recovery_value, sum(recoveries.values()), "recovery value")
        pending, declared = _check_order_intent(
            day, by_name, target, shares, cash, last_close, stale, pending, declared, mode, scale
        )
        order_cost = 0.0
        for order in day.orders:
            n, amount = order.instrument, order.executed_notional
            _near(
                order.total_cost,
                abs(amount) * (23 if amount < 0 else 18) * scale / 10000,
                "order cost",
            )
            if abs(amount) > order.capacity_notional + 1e-6:
                raise ValueError("fill exceeds reported capacity")
            if abs(amount) > 1e-12:
                bar = by_name.get(n)
                if bar is None or abs(amount) > bar.capacity_cny + 1e-6:
                    raise ValueError("fill lacks source opening price/capacity")
                if (amount > 0 and not bar.can_buy_open) or (amount < 0 and not bar.can_sell_open):
                    raise ValueError("fill violates source opening trading restriction")
                shares[n] = shares.get(n, 0.0) + amount / bar.open_price
                if shares[n] < -1e-7:
                    raise ValueError("unexpected short holding")
            cash -= amount + order.total_cost
            order_cost += order.total_cost
            traded += abs(amount)
            tickets += abs(amount) > 1e-8
        marks = {m.instrument: m for m in day.marks}
        if len(marks) != len(day.marks) or set(marks) != {
            n for n, q in shares.items() if q > 1e-12
        }:
            raise ValueError("held-name set differs from fill reconstruction")
        valuation = 0.0
        for n, mark in marks.items():
            _near(mark.shares, shares[n], "shares", atol=1e-7)
            if n in by_name:
                last_close[n], stale[n] = by_name[n].close_price, 0
            else:
                stale[n] = stale.get(n, 0) + 1
            price = 0.0 if stale[n] >= 20 else last_close[n]
            _near(mark.mark_price, price, "source close/stale mark", atol=1e-10)
            _near(mark.market_value, shares[n] * price, "market value")
            if mark.stale_sessions != stale[n]:
                raise ValueError("stale global-session count differs")
            valuation += shares[n] * price
            expected_source = (
                "current_close"
                if n in by_name
                else "conservative_zero_writeoff"
                if stale[n] >= 20
                else "explicit_stale_last_close"
            )
            if mark.source != expected_source:
                raise ValueError("independent source mark provenance mismatch")
        for n in set(shares) - set(marks):
            shares.pop(n)
            last_close.pop(n, None)
            stale.pop(n, None)
        _near(day.cash, cash, "cash flow")
        if cash < -1e-7:
            raise ValueError("negative cash")
        _near(day.total_cost, order_cost, "daily cost")
        _near(
            day.traded_notional_cny,
            sum(abs(o.executed_notional) for o in day.orders),
            "daily turnover",
        )
        _near(
            day.stale_position_days,
            sum(v > 0 for v in stale.values()),
            "daily stale positions",
            atol=0,
        )
        _near(day.overnight_mark_return, day.open_nav / nav - 1, "overnight return", atol=1e-12)
        totals["blocked_notional"] += sum(o.blocked_notional for o in day.orders)
        totals["stale_position_days"] += sum(v > 0 for v in stale.values())
        totals["writeoff_events"] += len(losses)
        totals["writeoff_loss"] += sum(losses.values())
        totals["recovery_events"] += len(recoveries)
        totals["recovery_value"] += sum(recoveries.values())
        residual = max(residual, abs(day.end_nav - cash - valuation))
        _near(day.end_nav, cash + valuation, "closing NAV")
        ret = day.end_nav / nav - 1
        _near(day.net_return, ret, "daily return", atol=1e-12)
        nav, previous_date = day.end_nav, dt
        peak = max(peak, nav)
        drawdowns.append(nav / peak - 1)
        returns.append(ret)
        annual.setdefault(dt[:4], []).append(ret)
        costs += order_cost
    _near(report.metrics.final_nav, nav, "final NAV")
    _near(report.metrics.net_total_return, nav / 3e6 - 1, "total return", atol=1e-12)
    _near(report.metrics.max_drawdown, min(drawdowns), "max drawdown", atol=1e-12)
    _near(report.metrics.total_cost, costs, "total cost")
    _near(report.metrics.periods, len(returns), "period count", atol=0)
    for field, value in totals.items():
        _near(getattr(report.metrics, field), value, f"aggregate {field}")
    sd = stdev(returns) if len(returns) > 1 else 0.0
    return {
        "pass": True,
        "periods": len(returns),
        "maximum_balance_residual_cny": residual,
        "years": {y: math.prod(1 + r for r in values) - 1 for y, values in annual.items()},
        "pooled_sharpe": mean(returns) / sd * math.sqrt(252) if sd else 0.0,
        "final_nav": nav,
        "traded_cny": traded,
        "executed_tickets": tickets,
        "independent_source_and_target_selection": False,
        "independent_execution_intent": True,
        "order_reason_labels_independently_verified": False,
    }


def _check_order_intent(
    day, bars, target, shares, cash, last_close, stale, pending, declared, mode, scale
):
    opening = {
        n: bars[n].open_price
        if n in bars
        else (0.0 if stale.get(n, 0) + 1 >= 20 else last_close[n])
        for n in shares
        if shares[n] > 1e-12
    }
    values = {n: shares[n] * price for n, price in opening.items()}
    nav = cash + sum(values.values())
    _near(day.open_nav, nav, "opening NAV")
    weights = (
        dict(target.weights)
        if target.rebalance
        else {n: v / nav for n, v in values.items() if nav > 0}
    )
    if mode == "target_changes" and target.rebalance:
        pending = pending | {
            n
            for n in declared.keys() | target.weights.keys()
            if abs(declared.get(n, 0.0) - target.weights.get(n, 0.0)) > 1e-12
        }
        weights = {n: min(v / nav, 0.025) for n, v in values.items() if nav > 0}
        for n in pending:
            weights[n] = target.weights.get(n, 0.0)
        declared = dict(target.weights)
    for n in set(target.forced_exits) | {n for n, bar in bars.items() if bar.forced_exit}:
        weights.pop(n, None)
    original, allowed, capacities = {}, {}, {}
    for n in sorted(values.keys() | weights.keys()):
        original[n] = weights.get(n, 0.0) * nav - values.get(n, 0.0)
        bar = bars.get(n)
        capacities[n] = bar.capacity_cny if bar else 0.0
        permitted = bar is not None and (
            bar.can_buy_open if original[n] > 0 else bar.can_sell_open if original[n] < 0 else True
        )
        allowed[n] = (
            math.copysign(min(abs(original[n]), capacities[n]), original[n]) if permitted else 0.0
        )
    sales = {n: max(v, -shares[n] * bars[n].open_price) for n, v in allowed.items() if v < 0}
    available = cash
    for n in sorted(sales):
        value = sales[n]
        available -= value + abs(value) * 23 * scale / 10000
    buys = {n: v for n, v in allowed.items() if v > 0}
    needed = sum(v * (1 + 18 * scale / 10000) for v in buys.values())
    fraction = min(1.0, max(0.0, available) / needed) if needed else 1.0
    expected = sales | {n: v * fraction for n, v in buys.items()}
    orders = {o.instrument: o for o in day.orders}
    if len(orders) != len(day.orders) or set(orders) != set(original):
        raise ValueError("independent target-change order identity mismatch")
    for n, order in orders.items():
        _near(order.desired_notional, original[n], "target-change requested notional")
        _near(order.capacity_notional, capacities[n], "source capacity")
        _near(
            order.executed_notional, expected.get(n, 0.0), "independent capacity/funding allocation"
        )
        _near(
            order.blocked_notional,
            max(0.0, abs(original[n]) - abs(order.executed_notional)),
            "blocked notional",
        )
    if mode == "target_changes" and target.rebalance:
        pending = {
            n
            for n in pending
            if abs(original.get(n, 0.0) - (orders[n].executed_notional if n in orders else 0.0))
            > 1e-8
            or (n in opening and n not in bars and stale.get(n, 0) + 1 >= 20)
        }
    return pending, declared
