"""Synthetic inversion of saved aggregate weights; no model invocation."""

from collections import Counter
from datetime import date, timedelta

import pytest

from stephen_quant.discovery.account_forensics_persistence import saved_membership
from stephen_quant.discovery.search_power_dsl import sha256_json


def fixture(empty_and_reenter=False):
    start = date(2023, 1, 3)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(700)
             if (start + timedelta(days=i)).weekday() < 5][:483] + ["2024-12-31"]
    sleeves = {p: set() for p in (0, 5, 10, 15)}
    targets, diagnostics = [], []
    for i, dt in enumerate(dates):
        phase = (i - 1) % 20 if i else None
        refresh = phase in sleeves and i >= phase + 1
        weights = {}
        if refresh:
            prior = sleeves[phase]
            names = {f"S{n:03d}" for n in range(i % 100, i % 100 + 40)}
            if empty_and_reenter and i == 21:
                names = set()
            if empty_and_reenter and i == 41:
                names = set(sorted(names)[:20])
            diagnostics.append({"execution_date": dt, "date": dates[i-1], "phase": phase,
                                "eligible": 200, "selected": len(names),
                                "new_members": len(names - prior),
                                "selected_names_sha256": sha256_json(tuple(sorted(names)))})
            sleeves[phase] = names
            counts = Counter(n for s in sleeves.values() for n in s)
            weights = {n: c / 160 for n, c in counts.items()}
        targets.append({"trade_date": dt, "weights": weights, "rebalance": refresh,
                        "forced_exits": []})
    return targets, diagnostics


def test_exact_same_phase_membership_and_unknown_scores():
    targets, diagnostics = fixture()
    result = saved_membership(targets, diagnostics)
    events = result["maintenance_events"]
    assert len(events) == 97
    assert sum(e["initialization"] for e in events) == 4
    assert events[4]["retained"] == 20
    assert events[4]["entered"] == events[4]["exited"] == 20
    assert events[4]["retention_fraction"] == 0.5
    assert result["new_predictions"] == 0
    assert result["raw_score_persistence"] is None
    assert result["top60_rank_persistence"] is None
    assert not result["name_churn_is_traded_turnover"]


def test_empty_then_partial_reentry_is_not_initialization():
    targets, diagnostics = fixture(empty_and_reenter=True)
    events = saved_membership(targets, diagnostics)["maintenance_events"]
    assert sum(e["initialization"] for e in events) == 4
    phase0 = [e for e in events if e["phase"] == 0]
    assert phase0[1]["selected_count"] == 0
    assert phase0[2]["previous_empty"]
    assert not phase0[2]["initialization"]
    assert phase0[2]["retention_fraction"] is None
    assert phase0[2]["selected_count"] == phase0[2]["entered"] == 20


@pytest.mark.parametrize("change", [
    "short", "missing_event", "duplicate_event", "wrong_phase", "wrong_signal",
    "hash", "new_count", "eligible", "fractional_seat", "negative_weight",
    "nan", "nonrefresh", "forced_exit", "wrong_schedule", "multiple_refresh",
])
def test_inconsistent_saved_membership_rejected(change):
    targets, diagnostics = fixture()
    if change == "short":
        targets.pop()
    elif change == "missing_event":
        diagnostics.pop()
    elif change == "duplicate_event":
        diagnostics[-1] = diagnostics[0]
    elif change == "wrong_phase":
        diagnostics[0]["phase"] = 5
    elif change == "wrong_signal":
        diagnostics[0]["date"] = diagnostics[0]["execution_date"]
    elif change == "hash":
        diagnostics[0]["selected_names_sha256"] = "a" * 64
    elif change == "new_count":
        diagnostics[0]["new_members"] = 39
    elif change == "eligible":
        diagnostics[0]["eligible"] = 39
    elif change in ("fractional_seat", "negative_weight", "nan"):
        targets[1]["weights"]["S001"] = {
            "fractional_seat": .003, "negative_weight": -.01, "nan": float("nan")}[change]
    elif change == "nonrefresh":
        targets[2]["weights"] = {"S001": .00625}
    elif change == "forced_exit":
        targets[1]["forced_exits"] = ["S001"]
    elif change == "wrong_schedule":
        targets[1]["rebalance"] = False
    elif change == "multiple_refresh":
        targets[6]["weights"]["S999"] = .0125
    with pytest.raises(ValueError):
        saved_membership(targets, diagnostics)
