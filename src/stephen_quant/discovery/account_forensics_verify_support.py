"""Independent support attribution from raw targets and dated history identities."""

from datetime import date

from .account_forensics_verify import compare
from .account_forensics_verify_members import derive_membership, exact_integer
from .search_power_dsl import sha256_json


def verify_support(targets, diagnostics, emitted, *, source_calendar, ranks):
    dates = list(source_calendar)
    if (not dates or dates != sorted(set(dates))
            or any(date.fromisoformat(d).isoformat() != d or not "2022" <= d[:4] <= "2024"
                   for d in dates)):
        raise ValueError("canonical frozen support calendar required")
    execution = [d for d in dates if d >= "2023-01-01"]
    members = derive_membership(targets, diagnostics, calendar=execution)
    positions = {d: i for i, d in enumerate(dates)}
    previous, expected = {}, []
    for member in members:
        signal, dt, phase = member["signal_date"], member["execution_date"], member["phase"]
        if (positions[signal] + 1 != positions[dt] or signal not in ranks):
            raise ValueError("exact prior-session support required")
        mapping = ranks[signal]
        for name, row in mapping.items():
            if (not isinstance(name, str) or not name or type(row["cell"]) is not int
                    or not 0 <= row["cell"] < 20):
                raise ValueError("invalid raw support identity/cell")
        support = set(mapping)
        selected, held = set(member["selected_names"]), set(member["previous_names"])
        if len(support) != member["eligible_count"] or not selected <= support:
            raise ValueError("independent saved support disagrees with targets/diagnostics")
        old = previous.get(phase)
        old_signal, old_support = (None, None) if old is None else old[:2]
        if old is not None and (positions[signal] - positions[old_signal] != 20 or held != old[2]):
            raise ValueError("independent same-phase chain mismatch")
        if old is None and held:
            raise ValueError("initial sleeve cannot contain prior names")
        lost, eligible_exit = held - support, (held & support) - selected
        if (lost | eligible_exit) != held - selected or lost & eligible_exit:
            raise ValueError("exit support partition mismatch")
        union = support | old_support if old_support is not None else set()
        expected.append({
            "signal_date": signal, "execution_date": dt, "phase": phase,
            "previous_signal_date": old_signal, "initialization": old is None,
            "support_count": len(support), "support_names_sha256": sha256_json(sorted(support)),
            "previous_support_count": len(old_support) if old_support is not None else None,
            "support_entered_count": len(support - old_support) if old_support is not None else None,
            "support_exited_count": len(old_support - support) if old_support is not None else None,
            "same_phase_support_jaccard": len(support & old_support) / len(union) if union else None,
            "previous_selected_lost_support": sorted(lost),
            "previous_selected_exited_still_eligible": sorted(eligible_exit),
            "retained_count": len(held & selected), "entered_count": len(selected - held),
            "exit_cause_beyond_support": "UNAVAILABLE_WITHOUT_SAVED_SCORE_OR_TOP60",
        })
        previous[phase] = signal, support, selected
    exact_integer(emitted["maintenance_count"], 97)
    exact_integer(emitted["new_predictions"], 0)
    for row in emitted["maintenance_events"]:
        for key in ("phase", "support_count", "retained_count", "entered_count"):
            exact_integer(row[key])
        for key in ("previous_support_count", "support_entered_count", "support_exited_count"):
            if row[key] is not None:
                exact_integer(row[key])
    compare(emitted, {
        "maintenance_events": expected, "maintenance_count": 97,
        "source": "saved_history_rank_row_identities_no_rank_or_prediction_recompute",
        "new_predictions": 0, "signal_instability_proven": False,
        "name_churn_is_traded_turnover": False,
    })
    return {"independent_support_verified": True, "maintenance_count": 97,
            "score_instability_verified": False, "validated_alpha": False}
