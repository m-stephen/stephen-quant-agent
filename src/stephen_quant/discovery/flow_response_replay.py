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

    No execution-engine, target-generator or summary function is called. This does
    not independently prove optimal fills/target_changes scheduling or raw source
    correctness; those remain separate target/source audit responsibilities.
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
    previous_date = ""
    for day, bars, target in zip(report.periods, sessions, targets, strict=True):
        dt = day.trade_date
        by_name = {b.instrument: b for b in bars}
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
        for n in set(shares) - set(marks):
            shares.pop(n)
            last_close.pop(n, None)
            stale.pop(n, None)
        _near(day.cash, cash, "cash flow")
        if cash < -1e-7:
            raise ValueError("negative cash")
        _near(day.total_cost, order_cost, "daily cost")
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
    }
