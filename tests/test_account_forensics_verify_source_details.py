"""Independent original-account to source explanation and recovery amount checks."""

from copy import deepcopy

import pytest
from test_account_forensics_chain import native_fixture

from stephen_quant.discovery.account_forensics_chain import reconcile_chain
from stephen_quant.discovery.account_forensics_inputs import event_source_keys
from stephen_quant.discovery.account_forensics_source import explain_event_sources
from stephen_quant.discovery.account_forensics_verify_events import derive_events
from stephen_quant.discovery.account_forensics_verify_source import verify_source_details


def fixture(mode="hold", kind="normal"):
    days, bars, report = native_fixture(mode)
    chain = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    reference = derive_events("A", report, calendar=days, bars=bars)
    lookups = {}
    for dt, name in event_source_keys([chain]):
        bar = bars[dt].get(name)
        lookups[(dt, name)] = None if bar is None else {
            "trade_date": dt, "instrument": name, "name": name,
            "open": bar["open_price"] / 2, "close": bar["close_price"] / 2,
            "adjustment_factor": 2., "amount": 100., "volume": 0.,
            "available_at": dt + "T18:00:00+08:00"}
    first = lookups[(days[2], "FAKE")]
    if kind == "unknown":
        first["available_at"] = "invalid"
    elif kind == "mismatch":
        first["open"] += 1
    elif kind == "refused":
        # A source row on a saved-missing day was not visible by that day's close.
        lookups[(days[3], "FAKE")] = {**first, "trade_date": days[3],
                                     "available_at": days[4] + "T18:00:00+08:00"}
    emitted = explain_event_sources(chain, source_lookups=lookups, saved_bars=bars)
    return reference, emitted, lookups, bars


@pytest.mark.parametrize("mode", ["hold", "sell", "partial", "blocked", "never"])
@pytest.mark.parametrize("kind", ["normal", "unknown", "mismatch", "refused"])
def test_complete_source_explanations(mode, kind):
    ref, out, lookups, bars = fixture(mode, kind)
    proof = verify_source_details(ref, out, lookups=lookups, bars=bars)
    assert proof["independent_source_explanations_verified"]
    assert proof["source_explanation_status"] == {
        "normal": "EXPLAINED_BY_FROZEN_SOURCE", "unknown": "UNKNOWN",
        "mismatch": "IMPLEMENTATION_MISMATCH", "refused": "EXPLAINED_BY_FROZEN_SOURCE"}[kind]
    assert not proof["validated_alpha"]


@pytest.mark.parametrize("bad", ["event_omit", "event_duplicate", "row_omit", "classification",
                                  "source_amount", "writeoff_amount", "cash_claim", "source_claim",
                                  "aggregate_status", "missing_lookup", "tail_omit", "tail_row"])
def test_source_explanation_tampering(bad):
    ref, out, lookups, bars = fixture("never" if bad.startswith("tail") else "hold")
    event = out["events"][0]
    if bad == "event_omit":
        out["events"].pop()
    elif bad == "event_duplicate":
        out["events"].append(deepcopy(event))
    elif bad == "row_omit":
        event["source_rows"].pop()
    elif bad == "classification":
        event["source_rows"][1]["classification"] = "source_and_saved_bar_match"
    elif bad == "source_amount":
        out["events"][1]["source_recovery_cny"] += 1
    elif bad == "writeoff_amount":
        event["source_last_mark_writeoff_cny"] += 1
    elif bad == "cash_claim":
        out["events"][1]["cash_receipt_inferred_from_recovery"] = True
    elif bad == "source_claim":
        out["source_truth_verified"] = True
    elif bad == "aggregate_status":
        out["source_explanation_status"] = "UNKNOWN"
    elif bad == "missing_lookup":
        lookups.pop(next(iter(lookups)))
    elif bad == "tail_omit":
        out["open_stale_chains"].pop()
    else:
        out["open_stale_chains"][0]["source_rows"].pop()
    with pytest.raises(ValueError):
        verify_source_details(ref, out, lookups=lookups, bars=bars)


def test_no_events_or_open_tails():
    reference = {"account": "A", "events": [], "open_stale_chains": []}
    out = explain_event_sources(reference, source_lookups={}, saved_bars={})
    proof = verify_source_details(reference, out, lookups={}, bars={})
    assert proof["source_explanation_status"] == "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS"
