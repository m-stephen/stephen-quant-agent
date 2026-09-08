"""Producer omissions cannot silently shrink the independently expected query."""

from copy import deepcopy

import pytest
from test_account_forensics_chain import native_fixture

from stephen_quant.discovery.account_forensics_chain import reconcile_chain
from stephen_quant.discovery.account_forensics_inputs import FIELDS, event_source_keys
from stephen_quant.discovery.account_forensics_verify_events import derive_events
from stephen_quant.discovery.account_forensics_verify_keys import (
    required_source_keys,
    verify_lookup_coverage,
)


def inputs(recovery="hold", short_tail=False):
    days, bars, report = native_fixture(recovery)
    if short_tail:
        days = days[:8]
        report["periods"] = report["periods"][:8]
        report["metrics"]["writeoff_events"] = report["metrics"]["recovery_events"] = 0
        report["metrics"]["writeoff_loss"] = report["metrics"]["recovery_value"] = 0
        report["metrics"]["final_nav"] = report["periods"][-1]["end_nav"]
    reference = derive_events("A", report, calendar=days, bars=bars)
    producer = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    requested = event_source_keys([producer])
    lookups = {key: None if key[0] not in (days[2], days[27] if len(days) > 27 else "") else
               {**dict.fromkeys(FIELDS), "trade_date": key[0], "instrument": key[1]}
               for key in requested}
    n = sum(row is not None for row in lookups.values())
    receipt = {"requested_keys": len(requested), "matched_rows": n,
               "absent_keys": len(requested) - n, "query_projection": list(FIELDS),
               "input_bytes_unchanged": True}
    return reference, producer, requested, lookups, receipt


@pytest.mark.parametrize("recovery,short", [("hold", False), ("sell", False), ("never", False),
                                           ("never", True)])
def test_independent_complete_keyset(recovery, short):
    ref, _, requested, lookups, receipt = inputs(recovery, short)
    proof = verify_lookup_coverage([ref], requested, lookups, receipt)
    assert proof["independent_lookup_coverage_verified"]
    if short:
        assert not ref["events"] and len(requested) == 6


def test_queries_deduplicate_but_accounts_do_not():
    ref, _, requested, lookups, receipt = inputs()
    other = deepcopy(ref)
    other["account"] = "B"
    for e in other["events"]:
        e["account"] = "B"
    assert required_source_keys([ref, other]) == requested
    verify_lookup_coverage([ref, other], requested, lookups, receipt)
    with pytest.raises(ValueError):
        required_source_keys([ref, ref])


@pytest.mark.parametrize("bad", ["producer_omit", "missing", "extra", "duplicate", "row_identity",
                                  "matched_count", "float_count", "projection", "changed_bytes",
                                  "actual_projection"])
def test_query_tampering(bad):
    ref, producer, requested, lookups, receipt = inputs()
    if bad == "producer_omit":
        producer["events"].pop()
        requested = event_source_keys([producer])
        lookups = {k: lookups[k] for k in requested}
        receipt["requested_keys"] = len(requested)
    elif bad == "missing":
        del lookups[requested[-1]]
    elif bad == "extra":
        lookups[("2023-01-03", "FORGED")] = None
    elif bad == "duplicate":
        requested.append(requested[0])
    elif bad == "row_identity":
        lookups[requested[0]]["instrument"] = "FORGED"
    elif bad == "matched_count":
        receipt["matched_rows"] += 1
    elif bad == "float_count":
        receipt["absent_keys"] = float(receipt["absent_keys"])
    elif bad == "projection":
        receipt["query_projection"].pop()
    elif bad == "actual_projection":
        del lookups[requested[0]]["volume"]
    else:
        receipt["input_bytes_unchanged"] = False
    with pytest.raises(ValueError):
        verify_lookup_coverage([ref], requested, lookups, receipt)


def test_explicit_empty_query():
    ref = {"account": "A", "events": [], "open_stale_chains": []}
    proof = verify_lookup_coverage([ref], [], {},
                                    {"requested_keys": 0, "matched_rows": 0, "absent_keys": 0})
    assert proof["requested_keys"] == 0
