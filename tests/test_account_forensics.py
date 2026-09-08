"""Synthetic saved-ledger checks, no predictions, backtests or raw market data."""

from copy import deepcopy

import pytest

from stephen_quant.discovery.account_forensics import (
    ZERO_MARK,
    exposure,
    extract_events,
    marks_index,
)


def mark(source, price, stale):
    return {"instrument": "FAKE", "source": source, "mark_price": price,
            "shares": 10, "market_value": 10 * price, "stale_sessions": stale}


@pytest.fixture
def report():
    periods = []
    previous = 200
    for day, price, source, stale, count, loss, recovered, value in (
        ("2023-01-03", 10, "explicit_stale_last_close", 19, 0, 0, 0, 0),
        ("2023-01-04", 0, ZERO_MARK, 20, 1, 100, 0, 0),
        ("2023-01-05", 5, "current_close", 0, 0, 0, 1, 50),
    ):
        nav = 100 + 10 * price
        periods.append({
            "trade_date": day, "cash": 100, "previous_nav": previous, "end_nav": nav,
            "net_return": nav / previous - 1, "orders": [], "total_cost": 0,
            "traded_notional_cny": 0, "marks": [mark(source, price, stale)],
            "writeoff_positions": count, "writeoff_loss": loss,
            "recovery_positions": recovered, "recovery_value": value,
        })
        previous = nav
    return {"config": {"stale_writeoff_sessions": 20}, "periods": periods,
            "metrics": {"initial_nav": 200, "final_nav": 150, "writeoff_events": 1,
                        "recovery_events": 1, "writeoff_loss": 100, "recovery_value": 50}}


def test_complete_event_identity_and_no_invented_recovery_amount(report):
    before = deepcopy(report)
    a, b = extract_events("account-a", report), extract_events("account-b", report)
    assert report == before
    assert a["event_count"] == b["event_count"] == 2
    assert a["events"][0]["amount_cny"] == 100
    assert a["events"][1]["amount_cny"] is None
    assert a["events"][1]["retrospective_only"] is True
    assert a["counterfactual_nav_generated"] is False
    identities = {(e["account"], e["date"], e["instrument"], e["event_type"])
                  for result in (a, b) for e in result["events"]}
    assert len(identities) == 4


@pytest.mark.parametrize("mutation", [
    "count", "loss", "duplicate_mark", "duplicate_order", "date", "future", "stale",
    "shares", "nav", "fees", "total", "policy", "nan", "bool_count", "zero_price",
])
def test_bad_saved_evidence_fails_closed(report, mutation):
    row = report["periods"][1]
    if mutation == "count":
        row["writeoff_positions"] = 0
    elif mutation == "loss":
        row["writeoff_loss"] = 99
    elif mutation == "duplicate_mark":
        row["marks"] *= 2
    elif mutation == "duplicate_order":
        row["orders"] = [{"instrument": "FAKE"}] * 2
    elif mutation == "date":
        row["trade_date"] = "2023-01-03"
    elif mutation == "future":
        row["trade_date"] = "2026-01-04"
    elif mutation == "stale":
        row["marks"][0]["stale_sessions"] = 21
    elif mutation == "shares":
        row["marks"][0]["shares"] = 11
    elif mutation == "nav":
        row["end_nav"] += 1
    elif mutation == "fees":
        row["total_cost"] = 1
    elif mutation == "total":
        report["metrics"]["writeoff_events"] = 2
    elif mutation == "policy":
        report["config"]["stale_writeoff_sessions"] = 10
    elif mutation == "nan":
        row["writeoff_loss"] = float("nan")
    elif mutation == "bool_count":
        row["writeoff_positions"] = True
    elif mutation == "zero_price":
        row["marks"][0].update(mark_price=1, market_value=10)
    with pytest.raises(ValueError):
        extract_events("test", report)


def test_recovery_sold_by_close_still_counted(report):
    last = report["periods"][-1]
    last.update(marks=[], cash=150, traded_notional_cny=50)
    last["orders"] = [{"instrument": "FAKE", "executed_notional": -50, "total_cost": 0}]
    events = extract_events("a", report)["events"]
    assert events[-1]["disposed_by_close"] is True
    assert events[-1]["amount_cny"] is None


def test_missing_disposal_evidence_is_not_silent_recovery(report):
    report["periods"][-1].update(marks=[], cash=150)
    with pytest.raises(ValueError, match="disposal"):
        extract_events("a", report)


def test_unknown_exposure_stays_in_denominator(report):
    row = report["periods"][0]
    second = mark("current_close", 10, 0)
    second["instrument"] = "OTHER"
    row["marks"].append(second)
    row["end_nav"] = 300
    result = exposure(row, {"FAKE": 2}, mapping_asof="2023-01-03")
    assert result["cell_invested_weights"][2] == .5
    assert result["unknown_invested_weight"] == .5
    assert result["unknown_nav_weight"] == pytest.approx(1/3)
    assert result["unknown_names"] == ["OTHER"]


@pytest.mark.parametrize("mapping,asof", [({"FAKE": 20}, "2023-01-03"),
                                        ({"FAKE": True}, "2023-01-03"),
                                        ({"FAKE": 1}, "2023-01-04")])
def test_bad_or_future_cell_mapping_rejected(report, mapping, asof):
    with pytest.raises(ValueError):
        exposure(report["periods"][0], mapping, mapping_asof=asof)


def test_all_cash_unknown_weight_is_unavailable_not_zero(report):
    row = report["periods"][0]
    row.update(marks=[], end_nav=100)
    result = exposure(row, {}, mapping_asof=row["trade_date"])
    assert result["unknown_invested_weight"] is None
    assert result["cash_nav_weight"] == 1


@pytest.mark.parametrize("source,price,stale", [
    ("current_close", 10, 1), ("explicit_stale_last_close", 10, 0),
    ("explicit_stale_last_close", 10, 20), (ZERO_MARK, 0, 19),
])
def test_mark_source_stale_age_contradiction_rejected(source, price, stale):
    with pytest.raises(ValueError, match="contradict"):
        marks_index([mark(source, price, stale)])
