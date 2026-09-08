"""Synthetic prior-session classification and saved same-phase support checks."""

import copy

import pytest
from test_account_forensics_persistence import fixture

from stephen_quant.discovery.account_forensics_persistence import saved_membership
from stephen_quant.discovery.account_forensics_structure import (
    prior_day_exposures,
    support_persistence,
)


def exposure_fixture():
    calendar = ["2022-12-30", "2023-01-03", "2023-01-04"]
    ranks = {calendar[0]: {"A": {"cell": 2}}, calendar[1]: {"A": {"cell": 3}},
             calendar[2]: {"A": {"cell": 19}, "B": {"cell": 0}}}
    marks = [{"instrument": n, "shares": 10, "mark_price": p, "market_value": p * 10,
              "source": "current_close" if p else "conservative_zero_writeoff",
              "stale_sessions": 0 if p else 20} for n, p in [("A", 10), ("B", 20), ("Z", 0)]]
    report = {"periods": [{"trade_date": d, "marks": copy.deepcopy(marks),
                           "cash": 100, "end_nav": 400} for d in calendar[1:]]}
    return report, calendar, ranks


def test_prior_market_day_unknown_denominator_and_zero_share_names():
    report, calendar, ranks = exposure_fixture()
    out = prior_day_exposures(report, source_calendar=calendar, ranks=ranks)
    a, b = out["daily"]
    assert a["mapping_asof"] == "2022-12-30"
    assert a["cell_cny"][2] == b["cell_cny"][3] == 100
    assert b["cell_cny"][19] == 0
    assert a["unknown_names"] == b["unknown_names"] == ["B", "Z"]
    assert a["zero_value_held_names"] == ["Z"]
    assert a["unknown_invested_weight"] == pytest.approx(2 / 3)
    assert a["unknown_nav_weight"] == .5 and a["cash_nav_weight"] == .25
    assert sum(a["cell_invested_weights"]) + a["unknown_invested_weight"] == 1


@pytest.mark.parametrize("bad", ["no_prior", "no_rank", "gap", "future", "cell", "bool_cell"])
def test_incomplete_or_future_map_refused(bad):
    report, calendar, ranks = exposure_fixture()
    if bad == "no_prior":
        calendar.pop(0)
    elif bad == "no_rank":
        del ranks[calendar[0]]
    elif bad == "gap":
        report["periods"].pop()
    elif bad == "future":
        calendar[-1] = "2025-01-02"
    else:
        ranks[calendar[0]]["A"]["cell"] = 20 if bad == "cell" else True
    with pytest.raises(ValueError):
        prior_day_exposures(report, source_calendar=calendar, ranks=ranks)


def support_fixture():
    targets, diagnostics = fixture()
    membership = saved_membership(targets, diagnostics)
    calendar = ["2022-12-30"] + [t["trade_date"] for t in targets]
    ranks = {e["signal_date"]: {f"S{n:03d}": {"cell": n % 20} for n in range(200)}
             for e in membership["maintenance_events"]}
    # Fifth event:5 old held names lose source support,5 different names replace
    # them, preserving eligible count200. Other15 exits remain source-eligible.
    e = membership["maintenance_events"][4]
    for n in range(1, 6):
        del ranks[e["signal_date"]][f"S{n:03d}"]
        ranks[e["signal_date"]][f"X{n:03d}"] = {"cell": 0}
    return membership, calendar, ranks


def test_equal_eligible_count_does_not_hide_identity_change():
    membership, calendar, ranks = support_fixture()
    out = support_persistence(membership, source_calendar=calendar, ranks=ranks)
    assert out["maintenance_count"] == 97
    e = out["maintenance_events"][4]
    assert e["support_count"] == e["previous_support_count"] == 200
    assert e["support_entered_count"] == e["support_exited_count"] == 5
    assert e["same_phase_support_jaccard"] == pytest.approx(195 / 205)
    assert len(e["previous_selected_lost_support"]) == 5
    assert len(e["previous_selected_exited_still_eligible"]) == 15
    assert not out["signal_instability_proven"]
    assert all(e["previous_signal_date"] is None for e in out["maintenance_events"][:4])


@pytest.mark.parametrize("bad", ["missing", "selected", "eligible", "previous", "phase", "signal",
                                 "initialization", "duplicate", "short"])
def test_inconsistent_saved_support_chain_refused(bad):
    membership, calendar, ranks = support_fixture()
    e = membership["maintenance_events"][4]
    if bad == "missing":
        del ranks[e["signal_date"]]
    elif bad == "selected":
        ranks[e["signal_date"]].pop(e["selected_names"][0])
    elif bad == "eligible":
        e["eligible_count"] += 1
    elif bad == "previous":
        e["previous_names"][0] = "wrong"
    elif bad == "phase":
        e["phase"] = 7
    elif bad == "signal":
        e["signal_date"] = calendar[1]
    elif bad == "initialization":
        e["initialization"] = True
    elif bad == "duplicate":
        membership["maintenance_events"][-1] = e
    else:
        membership["maintenance_events"].pop()
    with pytest.raises(ValueError):
        support_persistence(membership, source_calendar=calendar, ranks=ranks)
