"""Matched policy accounts executed by the existing native stateful engine."""

from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)

from .contracts import ROLES
from .search import scores, selected_ids
from .statistics import paired_metrics


def execution_config(cost):
    if cost not in (0, 82, 164):
        raise ValueError("unknown roundtrip cost")
    multiplier = cost / 41
    return StatefulExecutionConfig(
        maximum_position_weight=1 / 6,
        commission_bps=3 * multiplier,
        sell_tax_bps=5 * multiplier,
        slippage_bps=15 * multiplier,
        rebalance_mode="target_changes",
        stale_writeoff_sessions=20,
    )


def targets_for(panel, candidate, ranks, support, spec, role):
    if role not in ROLES:
        raise ValueError("unknown account role")
    values = scores(candidate, ranks)
    targets, exposures, previous = [], [], ()
    # Fixed identity ordering; no realized returns or oracle used by the baseline.
    baseline_score = np.array([((i * 17 + 13) % 29) / 29 for i in range(spec.assets)])
    permutation = np.concatenate([np.roll(np.flatnonzero(panel.groups == g), 1) for g in range(6)])
    for t in range(spec.evaluation_start, spec.sessions):
        rebalance = (t - spec.evaluation_start) % candidate.horizon == 0
        if rebalance:
            score = values[t - 1]
            if role == "risk_only":
                score = baseline_score
            elif role == "shuffle":
                score = score[permutation]
            previous = selected_ids(score, support[t - 1], panel.groups, previous, role=role)
        weights = {panel.instruments[i]: 1 / 6 for i in previous}
        # Empty groups remain in cash rather than reallocating based on future presence.
        targets.append(
            TargetAllocation(
                panel.dates[t], panel.dates[t - 1] + "T19:00:00+08:00", weights, rebalance=rebalance
            )
        )
        exposures.append([sum(panel.groups[i] == g for i in previous) / 6 for g in range(6)])
    return tuple(targets), exposures


def sessions_for(panel, spec):
    return tuple(
        tuple(
            StatefulBar(
                panel.dates[t],
                name,
                float(panel.opening[t, i]),
                float(panel.closing[t, i]),
                float(panel.capacity[t, i]),
                panel.dates[t - 1] + "T18:00:00+08:00",
                bool(panel.can_buy[t, i]),
                bool(panel.can_sell[t, i]),
            )
            for i, name in enumerate(panel.instruments)
        )
        for t in range(spec.evaluation_start, spec.sessions)
    )


def audit_account(report):
    """Independent scalar cash/mark/fee/NAV reconciliation, not broker certification."""
    previous, cash = report.metrics.initial_nav, report.metrics.initial_nav
    fees = 0.0
    for period in report.periods:
        if not math.isclose(period.previous_nav, previous, rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("account previous NAV mismatch")
        for order in period.orders:
            fees += order.total_cost
            cash -= order.executed_notional + order.total_cost
        # The native reports expose end marks; reconstruction is independent of target weights.
        if not math.isclose(cash, period.cash, rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("account cash mismatch")
        marked = math.fsum(m.market_value for m in period.marks)
        for mark in period.marks:
            if not math.isclose(
                mark.market_value, mark.shares * mark.mark_price, rel_tol=1e-10, abs_tol=1e-6
            ):
                raise ValueError("position mark mismatch")
        if not math.isclose(cash + marked, period.end_nav, rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("account wealth mismatch")
        expected = period.end_nav / previous - 1
        if period.net_return is None or not math.isclose(
            expected, period.net_return, abs_tol=1e-12
        ):
            raise ValueError("account return mismatch")
        previous = period.end_nav
    if not math.isclose(fees, report.metrics.total_cost, rel_tol=1e-10, abs_tol=1e-6):
        raise ValueError("account fee total mismatch")
    return {
        "status": "PASS",
        "periods": len(report.periods),
        "final_nav": previous,
        "scope": "cash/marks/fees/returns; not full independent order-fill reconstruction",
    }


def execute_four_accounts(panel, candidate, ranks, support, spec, record):
    sessions = sessions_for(panel, spec)
    targets = {role: targets_for(panel, candidate, ranks, support, spec, role) for role in ROLES}
    reports, summaries = {}, {}
    for cost in spec.costs_bps:
        for role in ROLES:
            record("before_account", candidate, {"role": role, "cost": cost})
            report = run_stateful_execution(
                sessions,
                targets[role][0],
                execution_config(cost),
                initial_nav=spec.capital_cny,
                retain_details=True,
            )
            audit = audit_account(report)
            reports[cost, role] = report
            summaries[f"{cost}:{role}"] = {
                "policy_id": candidate.identity(cost, role),
                "metrics": asdict(report.metrics),
                "audit": audit,
                "traded_notional_cny": math.fsum(p.traded_notional_cny for p in report.periods),
                "mean_group_target_weights": np.mean(targets[role][1], axis=0).tolist(),
                "realized_group_weights": [
                    [
                        math.fsum(
                            m.market_value for m in p.marks if int(m.instrument[3:]) // 4 == g
                        )
                        / p.end_nav
                        for g in range(6)
                    ]
                    for p in report.periods
                ],
                "daily": [[p.trade_date, p.net_return] for p in report.periods],
            }
            record(
                "account_complete",
                candidate,
                {"role": role, "cost": cost, "final_nav": report.metrics.final_nav},
            )
    paired = {}
    for cost in spec.costs_bps:
        a = reports[cost, "risk_signal"]
        for baseline in ("risk_only", "shuffle"):
            b = reports[cost, baseline]
            comparison = paired_metrics(
                [(p.trade_date, p.net_return) for p in a.periods],
                [(p.trade_date, p.net_return) for p in b.periods],
                capital_cny=spec.capital_cny,
                lag=spec.hac_lag,
            )
            comparison["fee_increment_cny"] = a.metrics.total_cost - b.metrics.total_cost
            comparison["traded_notional_increment_cny"] = (
                summaries[f"{cost}:risk_signal"]["traded_notional_cny"]
                - summaries[f"{cost}:{baseline}"]["traded_notional_cny"]
            )
            comparison["max_realized_group_weight_difference"] = float(
                np.max(
                    np.abs(
                        np.array(summaries[f"{cost}:risk_signal"]["realized_group_weights"])
                        - np.array(summaries[f"{cost}:{baseline}"]["realized_group_weights"])
                    )
                )
            )
            paired[f"{cost}:{baseline}"] = comparison
    required = [paired[f"{cost}:risk_only"] for cost in (82, 164)]
    promoted = economic_gate(required, spec)
    return {
        "accounts": summaries,
        "paired": paired,
        "promoted": promoted,
        "promotion_scope": "synthetic economic diagnostic, not Alpha Court",
        "native_account_count": len(reports),
        "new_fits": 0,
    }


def economic_gate(required, spec):
    return all(
        v["paired"]["mean"] >= spec.active_mean_min
        and v["paired"]["t"] is not None
        and v["paired"]["t"] >= spec.active_t_min
        and min(v["segment_means"]) > 0
        for v in required
    )


def oracle_reference(panel, oracle, winner, ranks, support, spec, result, record):
    """Evaluator-only known expression, same winner horizon/constraints; not an optimizer.

    Report every planted case, including an untradeable reference. Never filter the
    power denominator with this diagnostic or feed it back to candidate selection.
    """
    if oracle.expression is None:
        return {"status": "NOT_APPLICABLE_NULL", "account_runs": 0}
    from .contracts import Candidate

    operator, fields = oracle.expression[:-1].split("(")
    known = Candidate(operator, tuple(fields.split(",")), oracle.direction, winner.horizon)
    targets, _ = targets_for(panel, known, ranks, support, spec, "risk_signal")
    sessions = sessions_for(panel, spec)
    paired, audits = {}, {}
    for cost in (82, 164):
        record("before_oracle_account", known, {"role": "risk_signal", "cost": cost})
        report = run_stateful_execution(
            sessions, targets, execution_config(cost), initial_nav=spec.capital_cny
        )
        audits[str(cost)] = audit_account(report)
        paired[str(cost)] = paired_metrics(
            [(p.trade_date, p.net_return) for p in report.periods],
            result["accounts"][f"{cost}:risk_only"]["daily"],
            capital_cny=spec.capital_cny,
            lag=spec.hac_lag,
        )
        record(
            "oracle_account_complete", known, {"cost": cost, "final_nav": report.metrics.final_nav}
        )
    return {
        "status": "EVALUATOR_DIAGNOSTIC_ONLY",
        "account_runs": 2,
        "expression": oracle.expression,
        "horizon": winner.horizon,
        "scope": "known expression; same selected horizon, ranks and execution; not clairvoyant optimal trading",
        "positive_net_increment_both_costs": all(p["paired"]["mean"] > 0 for p in paired.values()),
        "passes_same_economic_gate": economic_gate(paired.values(), spec),
        "paired": paired,
        "audits": audits,
        "used_for_selection": False,
        "excluded_from_power_denominator": False,
    }
