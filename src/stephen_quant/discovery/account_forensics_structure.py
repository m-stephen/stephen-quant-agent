"""Saved support identities and prior-day exposure, not new factor computation."""

from .account_forensics import day, exposure
from .search_power_dsl import sha256_json


def _calendar(calendar):
    dates = [day(dt) for dt in calendar]
    if not dates or dates != sorted(set(dates)):
        raise ValueError("explicit complete ordered source calendar required")
    return dates, {dt: i for i, dt in enumerate(dates)}


def _mapping(ranks, dt):
    if dt not in ranks:
        raise ValueError("missing dated support; cannot substitute empty or nearest available day")
    result = {}
    for name, row in ranks[dt].items():
        if not isinstance(name, str) or not name or type(row["cell"]) is not int:
            raise ValueError("explicit support identity and integer cell required")
        if row["cell"] not in range(20):
            raise ValueError("saved cell outside fixed20 bins")
        result[name] = row["cell"]
    return result


def prior_day_exposures(report, *, source_calendar, ranks):
    """Close positions classified by the immediately prior market session's map.

    First execution day uses the source calendar's prior year-end day, never the
    current date or each stock's last available observation. The full runtime
    must separately bind all calendar/source bytes to the frozen parent plan.
    """
    dates, index = _calendar(source_calendar)
    execution = [dt for dt in dates if dt >= "2023-01-01"]
    if [p["trade_date"] for p in report["periods"]] != execution or not execution:
        raise ValueError("all saved periods must match the source execution calendar")
    result = []
    for period in report["periods"]:
        i = index[period["trade_date"]]
        if not i:
            raise ValueError("prior source session is required even for initial cash-only day")
        asof = dates[i - 1]
        mapping = _mapping(ranks, asof)
        row = exposure(period, mapping, mapping_asof=asof)
        row["mapping_sha256"] = sha256_json(mapping)
        row["zero_value_held_names"] = sorted(
            m["instrument"] for m in period["marks"]
            if m["shares"] > 0 and m["market_value"] == 0)
        row["unknown_held_count"] = len(row["unknown_names"])
        result.append(row)
    return {
        "daily": result, "sessions": len(result),
        "mapping_policy": "immediately_previous_frozen_market_session_not_last_name_observation",
        "weight_denominator": "all_marked_invested_value_including_unknowns_cash_separate",
        "risk_neutrality_proven": False,
    }


def support_persistence(membership, *, source_calendar, ranks):
    """Compare saved identity sets across the same phase's20-session refreshes."""
    dates, index = _calendar(source_calendar)
    events = membership["maintenance_events"]
    execution_dates = [dt for dt in dates if dt >= "2023-01-01"]
    expected = [(dt, (i - 1) % 20) for i, dt in enumerate(execution_dates)
                if i > 0 and (i - 1) % 20 in (0, 5, 10, 15)]
    if (len(events) != 97
            or [(e["execution_date"], e["phase"]) for e in events] != expected):
        raise ValueError("all97 saved maintenance events required")
    previous, result, seen = {}, [], set()
    for event in events:
        signal, execution, phase = event["signal_date"], event["execution_date"], event["phase"]
        if (signal not in index or execution not in index or index[execution] != index[signal] + 1
                or type(phase) is not int or phase not in (0, 5, 10, 15)
                or execution in seen):
            raise ValueError("exact prior-day unique phased maintenance required")
        support = set(_mapping(ranks, signal))
        selected, held = set(event["selected_names"]), set(event["previous_names"])
        if (len(support) != event["eligible_count"] or not selected <= support
                or len(selected) != event["selected_count"]
                or len(held) != event["previous_count"]):
            raise ValueError("stored selected/eligible identities disagree with dated support")
        prior = previous.get(phase)
        if prior is None:
            if not event["initialization"] or held:
                raise ValueError("initial phase cannot have earlier held identities")
            old_signal, old_support = None, None
        else:
            old_signal, old_support, old_selected = prior
            if (event["initialization"] or index[signal] - index[old_signal] != 20
                    or held != old_selected):
                raise ValueError("same-phase20-session identity chain mismatch")
        lost_support = held - support
        exited_eligible = (held - selected) & support
        if len(lost_support) + len(exited_eligible) != event["exited"]:
            raise ValueError("support classifications must cover every exited member")
        intersection = old_support & support if old_support is not None else None
        union = old_support | support if old_support is not None else None
        result.append({
            "signal_date": signal, "execution_date": execution, "phase": phase,
            "previous_signal_date": old_signal, "initialization": prior is None,
            "support_count": len(support), "support_names_sha256": sha256_json(sorted(support)),
            "previous_support_count": len(old_support) if old_support is not None else None,
            "support_entered_count": len(support - old_support) if old_support is not None else None,
            "support_exited_count": len(old_support - support) if old_support is not None else None,
            "same_phase_support_jaccard": len(intersection) / len(union) if union else None,
            "previous_selected_lost_support": sorted(lost_support),
            "previous_selected_exited_still_eligible": sorted(exited_eligible),
            "retained_count": len(held & selected), "entered_count": len(selected - held),
            "exit_cause_beyond_support": "UNAVAILABLE_WITHOUT_SAVED_SCORE_OR_TOP60",
        })
        previous[phase] = signal, support, selected
        seen.add(execution)
    if set(previous) != {0, 5, 10, 15}:
        raise ValueError("complete four-phase coverage required")
    return {
        "maintenance_events": result, "maintenance_count": len(result),
        "source": "saved_history_rank_row_identities_no_rank_or_prediction_recompute",
        "new_predictions": 0, "signal_instability_proven": False,
        "name_churn_is_traded_turnover": False,
    }
