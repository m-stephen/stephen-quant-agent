"""Independent membership verification, including coordinated output tampering."""

import pytest
from test_account_forensics_persistence import fixture

from stephen_quant.discovery.account_forensics_persistence import saved_membership
from stephen_quant.discovery.account_forensics_verify_members import verify_membership


@pytest.mark.parametrize("empty", [False, True])
def test_independent_membership(empty):
    targets, diagnostics = fixture(empty)
    result = saved_membership(targets, diagnostics)
    receipt = verify_membership(targets, diagnostics, result,
                                calendar=[t["trade_date"] for t in targets])
    assert receipt["maintenance_count"] == 97
    assert not receipt["support_verified"]


@pytest.mark.parametrize("change", ["omit", "member", "prior", "count_float", "phase_bool",
                                   "hash", "weight", "calendar", "duplicate", "score",
                                   "method", "score_status", "support_status"])
def test_tampering_rejected(change):
    targets, diagnostics = fixture()
    result = saved_membership(targets, diagnostics)
    dates = [t["trade_date"] for t in targets]
    row = result["maintenance_events"][4]
    if change == "omit":
        result["maintenance_events"].pop()
    elif change == "member":
        row["selected_names"][0] = "FORGED"
    elif change == "prior":
        row["previous_names"] = []
    elif change == "count_float":
        row["retained"] = float(row["retained"])
    elif change == "phase_bool":
        diagnostics[0]["phase"] = False
    elif change == "hash":
        diagnostics[0]["selected_names_sha256"] = "f" * 64
    elif change == "weight":
        targets[6]["weights"]["FORGED"] = 2 / 160
    elif change == "calendar":
        dates[4] = dates[3]
    elif change == "duplicate":
        diagnostics[-1] = diagnostics[0]
    elif change == "score":
        result["raw_score_persistence"] = .99
    elif change in ("method", "score_status", "support_status"):
        result[change] = "CERTIFIED_ALPHA"
    with pytest.raises(ValueError):
        verify_membership(targets, diagnostics, result, calendar=dates)
