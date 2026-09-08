"""Fixed synthetic native-account fixtures, not market research or parameter search."""

from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.account_forensics_chain import reconcile_chain
from stephen_quant.discovery.account_forensics_inputs import event_source_keys
from stephen_quant.discovery.account_forensics_source import explain_event_sources


def native_fixture(recovery="hold", *, two_cycles=False, mode="full_target"):
    start = date(2023, 12, 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(140)
            if (start + timedelta(days=i)).weekday() < 5][:90 if two_cycles else 45]
    sessions, targets, saved_bars = [], [], {}
    for i, dt in enumerate(days):
        bars = [StatefulBar(dt, "MARKET", 10, 10, 100000, dt + "T08:00:00+08:00")]
        present = i < 3 or (i >= 27 and recovery != "never")
        if two_cycles and 35 <= i < 61:
            present = False
        if present:
            bars.append(StatefulBar(
                dt, "FAKE", 10 if i < 3 else 5, 10 if i < 3 else 6, 100000,
                dt + "T08:00:00+08:00", can_sell_open=recovery != "blocked",
                tradability_reason="synthetic_locked" if recovery == "blocked" else "unrestricted"))
        sessions.append(tuple(bars))
        saved_bars[dt] = {b.instrument: asdict(b) for b in bars}
        refresh = i == 0 or (i == 27 and recovery != "hold")
        weights = {"FAKE": .5} if i == 0 else {"FAKE": .1} if recovery == "partial" else {}
        if two_cycles and i in (27, 30, 61):
            refresh = True
            weights = {} if i == 27 else {"FAKE": .5 if i == 30 else .1}
        targets.append(TargetAllocation(dt, dt + "T08:00:00+08:00", weights, refresh))
    config = StatefulExecutionConfig(maximum_position_weight=1, commission_bps=2,
                                     slippage_bps=3, sell_tax_bps=5, rebalance_mode=mode)
    report = asdict(run_stateful_execution(tuple(sessions), tuple(targets), config, initial_nav=1000))
    return days, saved_bars, report


@pytest.mark.parametrize("recovery", ["hold", "sell", "partial", "blocked"])
def test_complete_cross_year_writeoff_recovery_chain(recovery):
    days, bars, report = native_fixture(recovery)
    before = deepcopy(report)
    result = reconcile_chain("synthetic-" + recovery, report, calendar=days, saved_bars=bars)
    assert report == before
    assert result["ledger_chain_pass"] and not result["source_truth_verified"]
    assert result["new_accounts"] == 0 and not result["counterfactual_nav_generated"]
    loss, recovered = result["events"]
    assert loss["event_type"] == "writeoff"
    assert len(loss["stale_chain"]["missing_sessions"]) == 20
    assert loss["stale_chain"]["last_marked_date"] == days[2]
    assert recovered["event_type"] == "recovery"
    assert len(recovered["stale_chain"]["missing_sessions"]) == 24
    assert recovered["saved_bar_recovery_cny"] == pytest.approx(250, abs=1e-10, rel=0)
    assert recovered["source_recovery_cny"] is None
    assert recovered["disposed_by_close"] == (recovery == "sell")
    if recovery == "blocked":
        assert recovered["recovery_order"]["executed_notional"] == 0
        assert report["periods"][27]["cash"] == report["periods"][26]["cash"]
    if recovery == "sell":
        assert report["periods"][27]["cash"] - report["periods"][26]["cash"] == pytest.approx(249.75)
    if recovery == "partial":
        assert 0 < recovered["recovery_end_mark"]["shares"] < recovered["prior_shares"]


@pytest.mark.parametrize("change", [
    "missing_date", "permuted_calendar", "missing_history_date", "stale_jump",
    "injected_bar", "open_price", "bar_identity", "share_delta", "cash", "fees",
    "stale_total", "invented_order",
])
def test_chain_rejects_incomplete_or_inconsistent_evidence(change):
    days, bars, report = native_fixture()
    periods = report["periods"]
    if change == "missing_date":
        days = days[:10] + days[11:]
    elif change == "permuted_calendar":
        days[10], days[11] = days[11], days[10]
    elif change == "missing_history_date":
        del bars[days[10]]
    elif change == "stale_jump":
        periods[10]["marks"][0]["stale_sessions"] += 1
    elif change == "injected_bar":
        bars[days[22]]["FAKE"] = {**bars[days[0]]["FAKE"], "trade_date": days[22]}
    elif change == "open_price":
        bars[days[27]]["FAKE"]["open_price"] += 1
    elif change == "bar_identity":
        bars[days[0]]["FAKE"]["instrument"] = "OTHER"
    elif change == "share_delta":
        periods[0]["orders"][0]["executed_notional"] += 1
    elif change == "cash":
        periods[10]["cash"] += 1
    elif change == "fees":
        report["config"]["commission_bps"] += 1
    elif change == "stale_total":
        periods[10]["stale_position_days"] += 1
    elif change == "invented_order":
        periods[10]["orders"][0]["executed_notional"] = 1
    with pytest.raises(ValueError):
        reconcile_chain("synthetic", report, calendar=days, saved_bars=bars)


def test_same_instrument_is_not_deduplicated_across_accounts():
    days, bars, report = native_fixture()
    a = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    b = reconcile_chain("B", report, calendar=days, saved_bars=bars)
    assert len({(e["account"], e["date"], e["instrument"], e["event_type"])
                for e in a["events"] + b["events"]}) == 4


def source_rows(days, bars):
    rows = {}
    for dt in days:
        b = bars[dt].get("FAKE")
        rows[(dt, "FAKE")] = ({"trade_date": dt, "instrument": "FAKE", "open": b["open_price"],
                                "close": b["close_price"], "adjustment_factor": 1, "amount": 100,
                                "available_at": dt + "T18:00:00+08:00"} if b else None)
    return rows


def test_full_source_explanation_is_not_delisting_or_cash_receipt():
    days, bars, report = native_fixture("sell")
    chain = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    out = explain_event_sources(chain, source_lookups=source_rows(days, bars), saved_bars=bars)
    assert out["source_explanation_status"] == "EXPLAINED_BY_FROZEN_SOURCE"
    loss, recovered = out["events"]
    assert loss["source_last_mark_writeoff_cny"] == pytest.approx(500, abs=1e-10, rel=0)
    assert recovered["source_recovery_cny"] == pytest.approx(250, abs=1e-10, rel=0)
    assert not recovered["cash_receipt_inferred_from_recovery"]
    assert not loss["actual_suspension_or_delisting_verified"]
    assert chain["events"][1]["source_recovery_cny"] is None


@pytest.mark.parametrize("kind", ["unqueried", "unknown", "contradiction"])
def test_source_explanation_keeps_unavailability_or_mismatch(kind):
    days, bars, report = native_fixture()
    chain = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    lookups = source_rows(days, bars)
    key = days[10], "FAKE"
    if kind == "unqueried":
        del lookups[key]
        with pytest.raises(ValueError, match="explicit completed"):
            explain_event_sources(chain, source_lookups=lookups, saved_bars=bars)
        return
    lookups[key] = {} if kind == "unknown" else {
        **lookups[(days[0], "FAKE")], "trade_date": days[10],
        "available_at": days[10] + "T18:00:00+08:00"}
    out = explain_event_sources(chain, source_lookups=lookups, saved_bars=bars)
    assert out["source_explanation_status"] == ("UNKNOWN" if kind == "unknown"
                                                else "IMPLEMENTATION_MISMATCH")


def test_unrecovered_writeoff_tail_traced_through_last_session():
    days, bars, report = native_fixture("never")
    chain = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    assert len(chain["events"]) == 1
    tail = chain["open_stale_chains"][0]
    assert tail["through_date"] == days[-1]
    assert tail["written_down_at_end"]
    assert len(tail["stale_chain"]["missing_sessions"]) == 42
    assert (days[-1], "FAKE") in event_source_keys([chain])
    out = explain_event_sources(chain, source_lookups=source_rows(days, bars), saved_bars=bars)
    assert len(out["open_stale_chains"][0]["source_rows"]) == 43
    assert out["source_explanation_status"] == "EXPLAINED_BY_FROZEN_SOURCE"


@pytest.mark.parametrize("mode", ["full_target", "target_changes"])
def test_two_cycles_disposal_reentry_and_partial_recovery(mode):
    days, bars, report = native_fixture("sell", two_cycles=True, mode=mode)
    out = reconcile_chain("A", report, calendar=days, saved_bars=bars)
    assert [len(e["stale_chain"]["missing_sessions"]) for e in out["events"]] == [20, 24, 20, 26]
    assert out["events"][1]["disposed_by_close"]
    assert not out["events"][3]["disposed_by_close"]
    assert out["events"][2]["stale_chain"]["last_marked_date"] == days[34]
    assert out["open_stale_chains"] == []
