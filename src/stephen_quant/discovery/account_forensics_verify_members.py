"""Independent sleeve inversion from original aggregate targets, not producer deltas."""

from collections import Counter
from math import isfinite

from .account_forensics_verify import compare
from .search_power_dsl import sha256_json


def exact_integer(value, expected=None):
    if type(value) is not int or (expected is not None and value != expected):
        raise ValueError("exact membership integer required")
    return value


def derive_membership(targets, diagnostics, *, calendar):
    """Reference-side identities derived only from original target/diagnostic inputs."""
    dates = list(calendar)
    if (len(dates) != 484 or dates != sorted(set(dates))
            or dates[0] != "2023-01-03" or dates[-1] != "2024-12-31"
            or [t["trade_date"] for t in targets] != dates or len(diagnostics) != 97):
        raise ValueError("complete frozen membership calendar required")
    saved = {d["execution_date"]: d for d in diagnostics}
    if len(saved) != 97:
        raise ValueError("duplicate saved decision")
    sleeves, seen, expected = {p: set() for p in (0, 5, 10, 15)}, set(), []
    for i, target in enumerate(targets):
        phase = (i - 1) % 20 if i else None
        refresh = phase in sleeves
        if type(target["rebalance"]) is not bool or target["rebalance"] != refresh:
            raise ValueError("independent refresh schedule mismatch")
        if target.get("forced_exits"):
            raise ValueError("unexpected forced exits")
        if not refresh:
            if target["weights"] or dates[i] in saved:
                raise ValueError("unexpected nonrefresh evidence")
            continue
        d = saved.get(dates[i])
        if d is None or d["date"] != dates[i - 1]:
            raise ValueError("missing decision or incorrect signal date")
        exact_integer(d["phase"], phase)
        seats = {}
        for name, weight in target["weights"].items():
            if (not isinstance(name, str) or not name or type(weight) not in (int, float)
                    or not isfinite(weight) or not 0 < weight <= 4 / 160):
                raise ValueError("invalid saved aggregate weight")
            value = weight * 160
            if abs(value - round(value)) > 1e-6:
                raise ValueError("noninteger aggregate seat")
            seats[name] = round(value)
            if seats[name] < 1:
                raise ValueError("zero aggregate seat")
        # Subtract the other three persistent sleeves directly. This does not
        # use the producer's previous aggregate delta or its reconstructed names.
        other = Counter(n for p, names in sleeves.items() if p != phase for n in names)
        residual = {n: seats.get(n, 0) - other[n] for n in seats.keys() | other.keys()}
        if any(v not in (0, 1) for v in residual.values()):
            raise ValueError("aggregate cannot contain unchanged other sleeves")
        selected, prior = {n for n, v in residual.items() if v}, sleeves[phase]
        exact_integer(d["selected"], len(selected))
        exact_integer(d["new_members"], len(selected - prior))
        if (len(selected) > 40 or exact_integer(d["eligible"]) < len(selected)
                or d["selected_names_sha256"] != sha256_json(sorted(selected))):
            raise ValueError("independent membership diagnostic mismatch")
        expected.append({
            "signal_date": dates[i - 1], "execution_date": dates[i], "phase": phase,
            "previous_names": sorted(prior), "selected_names": sorted(selected),
            "retained": len(prior & selected), "entered": len(selected - prior),
            "exited": len(prior - selected), "previous_count": len(prior),
            "selected_count": len(selected), "initialization": phase not in seen,
            "previous_empty": not prior,
            "retention_fraction": len(prior & selected) / len(prior) if prior else None,
            "eligible_count": d["eligible"],
        })
        sleeves[phase] = selected
        seen.add(phase)
    if {e["execution_date"] for e in expected} != set(saved):
        raise ValueError("unconsumed decision")
    return expected


def verify_membership(targets, diagnostics, emitted, *, calendar):
    expected = derive_membership(targets, diagnostics, calendar=calendar)
    exact_integer(emitted["maintenance_count"], 97)
    for row in emitted["maintenance_events"]:
        for key in ("phase", "retained", "entered", "exited", "previous_count",
                    "selected_count", "eligible_count"):
            exact_integer(row[key])
    compare(emitted["maintenance_events"], expected)
    exact_integer(emitted["new_predictions"], 0)
    for key in ("raw_score_persistence", "top60_rank_persistence", "support_identity_change"):
        compare(emitted[key], None)
    compare(emitted["name_churn_is_traded_turnover"], False)
    compare(emitted["method"], "saved_aggregate_delta_verified_by_selected_names_sha256")
    compare(emitted["score_status"],
            "UNAVAILABLE_ONLY_SCORE_HASH_SAVED_NO_PREDICTION_RECOMPUTATION")
    compare(emitted["support_status"], "REQUIRES_FROZEN_HISTORY_IDENTITIES_NOT_ELIGIBLE_COUNT")
    return {"independent_membership_verified": True, "maintenance_count": 97,
            "raw_scores_verified": False, "support_verified": False,
            "new_predictions": 0, "validated_alpha": False}
