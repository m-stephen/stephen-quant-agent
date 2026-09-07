"""V12.2 pure allocation bridge; NOT an empirical launch entrypoint.

Original annual models and immutable common-support fields are used unchanged.
This module creates no fits, providers, Trials or execution accounts. A separate
reviewed launcher must reserve all four native accounts before using real inputs.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from stephen_quant.baseline.stateful import TargetAllocation

from .calendar_robustness import combine_sleeves
from .flow_response_history import verified_history
from .flow_response_predictor import INPUTS, guarded_predict
from .flow_response_series import clock
from .flow_response_views import HistoricalSessions
from .search_power_dsl import sha256_json

VERSION = "12.2-signal-construction-1"
POLICIES = ("global_response", "global_risk")
BUDGET, PRIOR_DEBT = 4, 3733


def contract():
    return {
        "version": VERSION,
        "accounts": [
            {
                "key": f"{policy}-{cost}",
                "policy": policy,
                "roundtrip_bps": cost,
                "response_policy": policy,
                "execution_mode": "target_changes",
            }
            for policy in POLICIES
            for cost in (82, 164)
        ],
        "budget": BUDGET,
        "prior_trial_lower_bound": PRIOR_DEBT,
        "new_fits": 0,
        "primary_comparison": "global_response - global_risk",
        "source_window": ["2022-01-01", "2024-12-31"],
        "execution_window": ["2023-01-03", "2024-12-31"],
        "revealed_development": True,
        "top_n": 40,
        "retention_rank": 60,
        "horizon": 20,
        "phases": [0, 5, 10, 15],
        "initial_capital_cny": 3_000_000,
        "tie_break": "instrument_ascending",
        "score": "original_annual_frozen_model_raw_score",
        "statistics": {
            "status": "NOT_IDENTIFIABLE",
            "dsr": None,
            "pbo": None,
            "placebo": None,
            "hac": "descriptive_coverage_limited",
        },
        "validated_alpha": False,
        "automatic_retry": False,
    }


def select_global_signal(rows, scores, previous=()):
    """Global ranking with a fixed retention buffer, not cross-sectional refitting."""
    if not isinstance(rows, Mapping) or not isinstance(scores, Mapping):
        raise TypeError("explicit support and score mappings required")
    if set(rows) != set(scores):
        raise ValueError("exact common support scores required; no silent filtering")
    if len(set(previous)) != len(previous) or any(not isinstance(n, str) for n in previous):
        raise ValueError("unique previous instrument identities required")
    for name, row in rows.items():
        if (
            not isinstance(name, str)
            or not name
            or set(row) != {"cell", "vol", "ranks"}
            or type(row["cell"]) is not int
            or row["cell"] not in range(20)
            or type(row["vol"]) not in (int, float)
            or not math.isfinite(row["vol"])
            or row["vol"] < 0
            or set(row["ranks"]) != set(INPUTS)
            or any(
                type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1
                for v in row["ranks"].values()
            )
            or type(scores[name]) not in (int, float)
            or not math.isfinite(scores[name])
        ):
            raise ValueError("complete finite original common support required")
    ordered = sorted(rows, key=lambda n: (-scores[n], n))
    previous_set = set(previous)
    retained = [n for n in ordered[:60] if n in previous_set][:40]
    chosen = set(retained)
    chosen.update([n for n in ordered if n not in chosen][: 40 - len(chosen)])
    return tuple(sorted(chosen))


def frozen_targets(registry, consumer, *, history_path, policy, models, paths, cache=None):
    """Uses an original native model consumer; zero inherited fits are copied."""
    if policy not in POLICIES:
        raise ValueError("only two frozen bridge policies allowed")
    original_policy = policy.removeprefix("global_")
    if set(models) != {2023, 2024} or set(paths) != {2023, 2024}:
        raise ValueError("both unchanged annual models required")
    history, proof = verified_history(registry, consumer, history_path, cache=cache)
    calendar = list(history["calendar"])
    if (
        calendar != sorted(set(calendar))
        or not calendar
        or any(not "2022-01-01" <= d <= "2024-12-31" for d in calendar)
    ):
        raise ValueError("frozen ordered 2022-2024 calendar required")
    days = [d for d in calendar if d >= "2023-01-01"]
    if not days:
        raise ValueError("development execution sessions required")
    sleeves, diagnostics = [], []
    for phase in (0, 5, 10, 15):
        previous, targets = (), []
        for i, dt in enumerate(days):
            signal = days[i - 1] if i else None
            refresh = i >= phase + 1 and (i - phase - 1) % 20 == 0
            weights = {}
            if refresh:
                year = int(dt[:4])
                model = models[year]
                if (
                    model["policy"] != original_policy
                    or model["year"] != year
                    or model.get("training_provenance", {}).get("history_artifact_sha256")
                    != proof["history_artifact_sha256"]
                ):
                    raise ValueError("unchanged annual model and history binding required")
                rows = history["ranks"][signal]
                scores = guarded_predict(
                    registry,
                    consumer,
                    model=model,
                    path=paths[year],
                    signal_date=signal,
                    execution_date=dt,
                    rows=rows,
                )
                chosen = select_global_signal(rows, scores, previous)
                weights = {name: 0.025 for name in chosen}
                diagnostics.append(
                    {
                        "date": signal,
                        "execution_date": dt,
                        "phase": phase,
                        "eligible": len(rows),
                        "selected": len(chosen),
                        "new_members": len(set(chosen) - set(previous)),
                        "scores_sha256": sha256_json(scores),
                        "selected_names_sha256": sha256_json(chosen),
                        "selected_mean_vol": sum(rows[n]["vol"] for n in chosen) / len(chosen)
                        if chosen
                        else None,
                        "selected_cell_counts": [
                            sum(rows[n]["cell"] == c for n in chosen) for c in range(20)
                        ],
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
    return combine_sleeves(sleeves), diagnostics, HistoricalSessions(history["bars"], days)
