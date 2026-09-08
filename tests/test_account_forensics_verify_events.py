"""Independent event checks use tiny synthetic native reports, never market data."""

from copy import deepcopy

import pytest
from test_account_forensics_chain import native_fixture

from stephen_quant.discovery.account_forensics_chain import reconcile_chain
from stephen_quant.discovery.account_forensics_verify_events import verify_events


@pytest.mark.parametrize("recovery", ["hold", "sell", "partial", "blocked", "never"])
def test_independent_event_and_open_tail_coverage(recovery):
    days, bars, report = native_fixture(recovery)
    emitted = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    proof = verify_events("A", report, emitted, calendar=days, bars=bars)
    assert proof["writeoff_events"] == 1
    assert proof["recovery_events"] == (0 if recovery == "never" else 1)
    assert proof["open_stale_chains"] == (1 if recovery == "never" else 0)
    assert proof["validated_alpha"] is False


def test_two_cycles_keep_every_event():
    days, bars, report = native_fixture(two_cycles=True)
    emitted = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    proof = verify_events("A", report, emitted, calendar=days, bars=bars)
    assert proof["writeoff_events"] == proof["recovery_events"] == 2


@pytest.mark.parametrize("bad", ["missing", "duplicate", "account", "amount", "chain",
                                  "recovery", "fractional_count", "bool_count", "tail"])
def test_event_tampering_refused(bad):
    days, bars, report = native_fixture()
    emitted = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    if bad == "missing":
        emitted["events"].pop()
    elif bad == "duplicate":
        emitted["events"].append(deepcopy(emitted["events"][0]))
    elif bad == "account":
        emitted["events"][0]["account"] = "B"
    elif bad == "amount":
        emitted["events"][0]["amount_cny"] += 1
    elif bad == "chain":
        emitted["events"][0]["stale_chain"]["missing_sessions"].pop()
    elif bad == "recovery":
        emitted["events"][1]["saved_bar_recovery_cny"] += 1
    elif bad == "fractional_count":
        report["metrics"]["writeoff_events"] = 1.00000001
    elif bad == "bool_count":
        report["metrics"]["writeoff_events"] = True
    else:
        emitted["open_stale_chains"] = [{"stale_chain": {"missing_sessions": []}}]
    with pytest.raises(ValueError):
        verify_events("A", report, emitted, calendar=days, bars=bars)


@pytest.mark.parametrize("location", ["event", "chain", "tail", "new_bar"])
def test_integer_age_and_first_holding_checks(location):
    days, bars, report = native_fixture("never" if location == "tail" else "hold")
    emitted = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    if location == "event":
        emitted["events"][0]["stale_sessions"] = 20.00000001
    elif location == "chain":
        emitted["events"][0]["stale_chain"]["missing_sessions"][0]["stale_sessions"] = True
    elif location == "tail":
        emitted["open_stale_chains"][0]["stale_chain"]["missing_sessions"][0]["stale_sessions"] = 1.0
    else:
        del bars[days[0]]["FAKE"]
    with pytest.raises(ValueError):
        verify_events("A", report, emitted, calendar=days, bars=bars)
