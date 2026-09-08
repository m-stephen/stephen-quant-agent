"""Raw identity checks distinguish equal-sized support changes from score claims."""

import pytest
from test_account_forensics_persistence import fixture
from test_account_forensics_structure import support_fixture

from stephen_quant.discovery.account_forensics_persistence import saved_membership
from stephen_quant.discovery.account_forensics_structure import support_persistence
from stephen_quant.discovery.account_forensics_verify_support import verify_support
from stephen_quant.discovery.search_power_dsl import sha256_json


def inputs():
    membership, calendar, ranks = support_fixture()
    targets, diagnostics = fixture()
    result = support_persistence(membership, source_calendar=calendar, ranks=ranks)
    return targets, diagnostics, result, calendar, ranks


def test_support_independent_raw_identities():
    targets, diagnostics, result, calendar, ranks = inputs()
    out = verify_support(targets, diagnostics, result, source_calendar=calendar, ranks=ranks)
    assert out["independent_support_verified"]
    assert not out["score_instability_verified"]
    event = result["maintenance_events"][4]
    assert len(event["previous_selected_lost_support"]) == 5
    assert len(event["previous_selected_exited_still_eligible"]) == 15


@pytest.mark.parametrize("all_empty", [True, False])
def test_empty_support_or_sleeve_reentry(all_empty):
    targets, diagnostics = fixture(empty_and_reenter=True)
    if all_empty:
        for t in targets:
            t["weights"] = {}
        for d in diagnostics:
            d.update(selected=0, new_members=0, eligible=0, selected_names_sha256=sha256_json([]))
    else:
        diagnostics[4]["eligible"] = 0
    membership = saved_membership(targets, diagnostics)
    calendar = ["2022-12-30"] + [t["trade_date"] for t in targets]
    ranks = {d["date"]: ({} if d["eligible"] == 0 else
             {f"S{n:03d}": {"cell": n % 20} for n in range(200)}) for d in diagnostics}
    result = support_persistence(membership, source_calendar=calendar, ranks=ranks)
    verify_support(targets, diagnostics, result, source_calendar=calendar, ranks=ranks)
    assert sum(e["initialization"] for e in result["maintenance_events"]) == 4
    if all_empty:
        assert all(e["same_phase_support_jaccard"] is None for e in result["maintenance_events"])


@pytest.mark.parametrize("change", ["missing_map", "same_count_different_names", "changed_target",
                                   "future_map", "omit", "lost_names", "jaccard", "float_count",
                                   "false_certification", "cell", "method"])
def test_support_tampering(change):
    targets, diagnostics, result, calendar, ranks = inputs()
    event = result["maintenance_events"][4]
    signal = event["signal_date"]
    if change == "missing_map":
        del ranks[signal]
    elif change == "same_count_different_names":
        del ranks[signal]["S199"]
        ranks[signal]["Z999"] = {"cell": 0}
    elif change == "changed_target":
        targets[21]["weights"]["FORGED"] = .00625
    elif change == "future_map":
        event["signal_date"] = event["execution_date"]
    elif change == "omit":
        result["maintenance_events"].pop()
    elif change == "lost_names":
        event["previous_selected_lost_support"] = []
    elif change == "jaccard":
        event["same_phase_support_jaccard"] = 1
    elif change == "float_count":
        event["support_entered_count"] = 5.0
    elif change == "false_certification":
        result["signal_instability_proven"] = True
    elif change == "cell":
        ranks[signal]["S199"]["cell"] = True
    elif change == "method":
        result["source"] = "certified_alpha"
    with pytest.raises(ValueError):
        verify_support(targets, diagnostics, result, source_calendar=calendar, ranks=ranks)
