"""Frozen common-support response targets, then one continuous netted account.

Original anchors and the complete empirical epoch budget are integrated by the
future runner, not silently replaced by these same-support controls.
"""

from __future__ import annotations

import hashlib
import json

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)

from .calendar_robustness import PHASES, combine_sleeves
from .flow_response_history import verified_history
from .flow_response_predictor import HORIZON, POLICIES, guarded_predict
from .flow_response_series import clock
from .flow_response_views import HistoricalSessions
from .pairwise_ranking import select
from .search_power_dsl import sha256_json


def history_targets(
    registry, consumer, *, history_path, policy, models=None, paths=None, cache=None
):
    if policy not in POLICIES + ("hash", "lowvol"):
        raise ValueError("registered response allocation policy required")
    with registry.connect() as conn:
        row = conn.execute(
            "SELECT hyperparams FROM trials WHERE trial_id=?", (consumer,)
        ).fetchone()
    if row is None or json.loads(row[0]).get("response_policy") != policy:
        raise ValueError("allocation differs from predeclared Trial policy")
    learned = policy in POLICIES
    if learned and (models is None or paths is None):
        raise ValueError("native response predictors required")
    if not learned and registry.fit_lineage(consumer)["stages"]:
        raise ValueError("explicit no-fit allocation control required")
    history, proof = verified_history(registry, consumer, history_path, cache=cache)
    days = [d for d in history["calendar"] if "2023-01-01" <= d <= "2024-12-31"]
    if not days:
        raise ValueError("development execution window required")
    sleeves, diagnostics = [], []
    for phase in PHASES:
        previous, targets = (), []
        for i, dt in enumerate(days):
            signal = days[i - 1] if i else None
            refresh = i >= phase + 1 and (i - phase - 1) % HORIZON == 0
            weights = {}
            if refresh:
                if learned:
                    model = models[int(dt[:4])]
                    if (
                        model["policy"] != policy
                        or model.get("training_provenance", {}).get("history_artifact_sha256")
                        != proof["history_artifact_sha256"]
                    ):
                        raise ValueError("predictor not bound to actual historical matrix")
                    values = guarded_predict(
                        registry,
                        consumer,
                        model=model,
                        path=paths[int(dt[:4])],
                        signal_date=signal,
                        execution_date=dt,
                        rows=history["ranks"][signal],
                    )
                elif policy == "hash":
                    values = {
                        n: int(hashlib.sha256(f"v11.21:184:{n}".encode()).hexdigest(), 16)
                        for n in history["ranks"][signal]
                    }
                else:
                    values = {n: -r["vol"] for n, r in history["ranks"][signal].items()}
                rows = history["ranks"][signal]
                chosen = select(rows, values, previous)
                weights = {n: 0.025 for n in chosen}  # Vacant cells remain cash.
                diagnostics.append(
                    {
                        "date": signal,
                        "execution_date": dt,
                        "phase": phase,
                        "eligible": len(rows),
                        "selected": len(chosen),
                        "new_members": len(set(chosen) - set(previous)),
                        "scores_sha256": sha256_json(values),
                    }
                )
                previous = chosen
            targets.append(
                TargetAllocation(
                    dt,
                    clock(signal, "23:59:59") if signal else clock(dt, "08:00:00"),
                    weights,
                    refresh,
                )
            )
        sleeves.append(tuple(targets))
    targets = combine_sleeves(sleeves)
    sessions = HistoricalSessions(history["bars"], days)
    return targets, diagnostics, sessions


def execute_response_account(sessions, targets, *, roundtrip_bps):
    if type(roundtrip_bps) is not int or roundtrip_bps not in (82, 164):
        raise ValueError("frozen82/164bps account costs required")
    multiplier = roundtrip_bps // 41
    return run_stateful_execution(
        sessions,
        targets,
        StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=3 * multiplier,
            sell_tax_bps=5 * multiplier,
            slippage_bps=15 * multiplier,
            stale_writeoff_sessions=20,
            rebalance_mode="target_changes",
        ),
        initial_nav=3_000_000,
        retain_details=True,
    )
