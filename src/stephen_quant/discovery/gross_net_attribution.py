"""Frozen-policy cost-path diagnostics, never an Alpha promotion mechanism."""

from __future__ import annotations

import math
from datetime import datetime

from stephen_quant.baseline.stateful import StatefulExecutionConfig, TargetAllocation

from .search_power_dsl import sha256_json

VERSION = "11.20.0"
DEBT = 3648
BASES = ("linear", "quadratic")
KINDS = ("full", "risk", "shuffle", "regression")
CONTROLS = ("hash", "lowvol", "original_lowvol", "original_stable")


def plans():
    identities = [(b, k) for b in BASES for k in KINDS] + [("control", k) for k in CONTROLS]
    return [
        {
            "key": f"{b}-{k}-0",
            "target_key": f"{b}-{k}",
            "identity": b,
            "policy": k,
            "basis": b if b in BASES else "none",
            "scale": 0,
            "roundtrip_bps": 0,
            "mode": "full_target" if k.startswith("original_") else "target_changes",
            "operation_kind": "frozen_target_replay",
        }
        for b, k in identities
    ]


def execution_config(plan):
    if plan not in plans():
        raise ValueError("unregistered zero-cost replay plan")
    return StatefulExecutionConfig(
        maximum_position_weight=0.025,
        commission_bps=0,
        sell_tax_bps=0,
        slippage_bps=0,
        rebalance_mode=plan["mode"],
    )


def frozen_targets(raw, digest, calendar):
    if sha256_json(raw) != digest:
        raise ValueError("frozen target semantics changed")
    if not calendar or calendar != sorted(set(calendar)):
        raise ValueError("ordered unique calendar required")
    if [t["trade_date"] for t in raw] != calendar:
        raise ValueError("target calendar mismatch")
    result = []
    for t in raw:
        day = t["trade_date"]
        if not "2023-01-01" <= day <= "2024-12-31":
            raise ValueError("restricted target year")
        decision = datetime.fromisoformat(t["decided_at"])
        if decision.tzinfo is None or decision >= datetime.fromisoformat(day + "T09:30:00+08:00"):
            raise ValueError("target decision must precede execution")
        if any(not math.isfinite(w) or not 0 <= w <= 0.025 for w in t["weights"].values()):
            raise ValueError("invalid frozen target weight")
        if sum(t["weights"].values()) > 1 + 1e-10:
            raise ValueError("target exceeds capital")
        result.append(TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}))
    return tuple(result)


def execution_summary(report):
    return {
        "executed_tickets": sum(
            abs(o.executed_notional) > 1e-8 for d in report.periods for o in d.orders
        ),
        "traded_cny": sum(d.traded_notional_cny for d in report.periods),
        "mean_cash_fraction": sum(d.cash / d.end_nav for d in report.periods) / len(report.periods),
        "max_close_weight": max(
            (m.market_value / d.end_nav for d in report.periods for m in d.marks), default=0
        ),
        "max_actual_positions": max(len(d.marks) for d in report.periods),
        "end_positions": len(report.periods[-1].marks),
    }


def attribution(records):
    """Complete-factorial descriptive differences; no selected winner or p-value."""
    expected = {p["target_key"] + f"-{cost}" for p in plans() for cost in (0, 82, 164)}
    if set(records) != expected:
        raise ValueError("all36 zero/paid records required")
    for key, r in records.items():
        if r["key"] != key or r["roundtrip_bps"] != int(key.rsplit("-", 1)[1]):
            raise ValueError("record identity mismatch")
        if set(r["years"]) != {"2023", "2024"}:
            raise ValueError("both years required")
        values = [r["metrics"]["net_total_return"], *r["years"].values()]
        if not all(math.isfinite(v) and v >= -1 for v in values):
            raise ValueError("invalid return")
        if not math.isclose(
            math.prod(1 + v for v in r["years"].values()) - 1, values[0], abs_tol=1e-10
        ):
            raise ValueError("continuous annual compounding mismatch")
    path_drag, increments = [], []
    for p in plans():
        tk = p["target_key"]
        zero = records[tk + "-0"]
        for cost in (82, 164):
            paid = records[tk + f"-{cost}"]
            gross, net = zero["metrics"]["net_total_return"], paid["metrics"]["net_total_return"]
            path_drag.append(
                {
                    "identity": p["identity"],
                    "policy": p["policy"],
                    "target_key": tk,
                    "roundtrip_bps": cost,
                    "zero_cost_return": gross,
                    "paid_return": net,
                    "cost_path_drag": gross - net,
                    "direct_cost_fraction_initial_capital": paid["metrics"]["total_cost"]
                    / 3_000_000,
                    "addback_error": gross - net - paid["metrics"]["total_cost"] / 3_000_000,
                    "drag2023": zero["years"]["2023"] - paid["years"]["2023"],
                    "drag2024": zero["years"]["2024"] - paid["years"]["2024"],
                }
            )
    for b in BASES:
        controls = [f"{b}-{k}" for k in ("risk", "shuffle", "regression")] + [
            f"control-{k}" for k in CONTROLS
        ]
        for control in controls:
            gross = (
                records[b + "-full-0"]["metrics"]["net_total_return"]
                - records[control + "-0"]["metrics"]["net_total_return"]
            )
            for cost in (0, 82, 164):
                candidate, peer = records[f"{b}-full-{cost}"], records[f"{control}-{cost}"]
                delta = (
                    candidate["metrics"]["net_total_return"] - peer["metrics"]["net_total_return"]
                )
                increments.append(
                    {
                        "identity": b,
                        "control": control,
                        "roundtrip_bps": cost,
                        "candidate_return": candidate["metrics"]["net_total_return"],
                        "control_return": peer["metrics"]["net_total_return"],
                        "increment": delta,
                        "gross_increment": gross,
                        "increment_path_drag": gross - delta,
                        "increment2023": candidate["years"]["2023"] - peer["years"]["2023"],
                        "increment2024": candidate["years"]["2024"] - peer["years"]["2024"],
                    }
                )
    return {
        "path_drag": path_drag,
        "increments": increments,
        "validated_alpha": False,
        "screen_survived": {b: False for b in BASES},
        "interpretation": "diagnostic_only;counterfactual_cost_paths_are_not_causal_fee_estimates",
    }
