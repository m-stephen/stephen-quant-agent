"""Recover saved sleeve membership algebraically; no scoring or selection rerun."""

from collections import Counter

from .account_forensics import close, day, finite
from .search_power_dsl import sha256_json


def saved_membership(targets, diagnostics):
    """Invert four equal 40-name sleeves and cross-check stored identity hashes.

    Only one phase refreshes per event. Aggregate share of desired allocation is
    an integer multiple of1/160, so the refreshed sleeve is uniquely determined
    by the aggregate delta and its own previous saved membership. This is NOT a
    reconstruction of missing scores, a new target or a new simulated account.
    """
    if len(targets) != 484 or len(diagnostics) != 97:
        raise ValueError("fixed484 sessions and97 saved decisions required")
    dates = [day(t["trade_date"]) for t in targets]
    if (
        dates != sorted(set(dates))
        or dates[0] != "2023-01-03"
        or dates[-1] != "2024-12-31"
    ):
        raise ValueError("frozen2023-2024 continuous target calendar required")
    indexed = {d["execution_date"]: d for d in diagnostics}
    if len(indexed) != 97:
        raise ValueError("duplicate maintenance decision")
    phases = {phase: set() for phase in (0, 5, 10, 15)}
    seen_phases = set()
    previous_counts, events = Counter(), []
    for i, target in enumerate(targets):
        dt = dates[i]
        phase = (i - 1) % 20 if i else None
        refresh = phase in phases and i >= phase + 1
        if type(target["rebalance"]) is not bool or target["rebalance"] != refresh:
            raise ValueError("frozen phase refresh schedule mismatch")
        if target.get("forced_exits"):
            raise ValueError("unexpected forced exit in saved construction targets")
        weights = target["weights"]
        if not refresh:
            if weights or dt in indexed:
                raise ValueError("nonrefresh target must be empty and have no diagnostic")
            continue
        if dt not in indexed:
            raise ValueError("missing maintenance decision")
        d = indexed[dt]
        if type(d["phase"]) is not int or d["phase"] != phase or d["date"] != dates[i - 1]:
            raise ValueError("maintenance phase/signal date mismatch")
        counts = Counter()
        for name, weight in weights.items():
            if not isinstance(name, str) or not name:
                raise ValueError("explicit name required")
            seats = finite(weight, nonnegative=True) * 160
            nearest = round(seats)
            close(seats, nearest)
            if not 1 <= nearest <= 4:
                raise ValueError("aggregate seat count outside four sleeves")
            counts[name] = nearest
        prior = phases[phase]
        selected = set()
        for name in counts.keys() | previous_counts.keys() | prior:
            indicator = counts[name] - previous_counts[name] + int(name in prior)
            if indicator not in (0, 1):
                raise ValueError("aggregate delta cannot represent one sleeve refresh")
            if indicator:
                selected.add(name)
        if (
            type(d["selected"]) is not int
            or not 0 <= d["selected"] <= 40
            or len(selected) != d["selected"]
            or sha256_json(tuple(sorted(selected))) != d["selected_names_sha256"]
            or type(d["new_members"]) is not int
            or len(selected - prior) != d["new_members"]
            or type(d["eligible"]) is not int
            or d["eligible"] < len(selected)
        ):
            raise ValueError("recovered membership differs from frozen diagnostic")
        events.append({
            "signal_date": d["date"], "execution_date": dt, "phase": phase,
            "previous_names": sorted(prior), "selected_names": sorted(selected),
            "retained": len(prior & selected), "entered": len(selected - prior),
            "exited": len(prior - selected), "previous_count": len(prior),
            "selected_count": len(selected), "initialization": phase not in seen_phases,
            "previous_empty": not prior,
            "retention_fraction": len(prior & selected) / len(prior) if prior else None,
            "eligible_count": d["eligible"],
        })
        phases[phase] = selected
        seen_phases.add(phase)
        previous_counts = counts
    if {e["execution_date"] for e in events} != set(indexed):
        raise ValueError("unconsumed diagnostic outside saved calendar")
    return {
        "maintenance_events": events,
        "maintenance_count": len(events),
        "method": "saved_aggregate_delta_verified_by_selected_names_sha256",
        "raw_score_persistence": None,
        "top60_rank_persistence": None,
        "score_status": "UNAVAILABLE_ONLY_SCORE_HASH_SAVED_NO_PREDICTION_RECOMPUTATION",
        "support_identity_change": None,
        "support_status": "REQUIRES_FROZEN_HISTORY_IDENTITIES_NOT_ELIGIBLE_COUNT",
        "name_churn_is_traded_turnover": False,
        "new_predictions": 0,
    }
