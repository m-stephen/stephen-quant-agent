"""Synthetic-only allocation tests; these are not empirical research trials."""

import copy
from datetime import date, timedelta
from types import MappingProxyType

import pytest

from stephen_quant.discovery import signal_construction as bridge
from stephen_quant.discovery.flow_response_predictor import INPUTS


def rows(n=100):
    return {
        f"S{i:03d}": {"cell": i % 20, "vol": 0.1, "ranks": dict.fromkeys(INPUTS, 0.0)}
        for i in range(n)
    }


def test_fixed_four_account_contract():
    c = bridge.contract()
    assert c["budget"] == len(c["accounts"]) == 4
    assert c["prior_trial_lower_bound"] == 3733 and c["new_fits"] == 0
    assert c["revealed_development"] and not c["validated_alpha"]
    assert c["statistics"]["pbo"] is None
    c["accounts"].clear()
    assert len(bridge.contract()["accounts"]) == 4


def test_retention_scores_ties_and_exact_common_support():
    r = rows()
    scores = {n: -int(n[1:]) for n in r}
    prior = tuple(f"S{i:03d}" for i in range(30, 70))
    expected = tuple(
        sorted([f"S{i:03d}" for i in range(30, 60)] + [f"S{i:03d}" for i in range(10)])
    )
    assert bridge.select_global_signal(r, scores, prior) == expected
    assert bridge.select_global_signal(r, dict.fromkeys(r, 3.0)) == tuple(sorted(r)[:40])
    assert bridge.select_global_signal({}, {}, prior) == ()
    assert bridge.select_global_signal(rows(3), dict.fromkeys(rows(3), 1)) == tuple(rows(3))


def test_no_extra_normalization_or_mutation():
    r = rows()
    scores = {n: 10000 + i / 17 for i, n in enumerate(r)}
    before = copy.deepcopy((r, scores))
    chosen = bridge.select_global_signal(MappingProxyType(r), MappingProxyType(scores))
    assert chosen == tuple(sorted(r)[-40:])
    assert before == (r, scores)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "1"])
def test_invalid_scores_reject_no_drop(bad):
    r = rows()
    scores = dict.fromkeys(r, 1.0)
    scores["S000"] = bad
    with pytest.raises(ValueError):
        bridge.select_global_signal(r, scores)


def test_missing_unused_feature_rejects():
    r = rows()
    del r["S000"]["ranks"][INPUTS[-1]]
    with pytest.raises(ValueError):
        bridge.select_global_signal(r, dict.fromkeys(r, 1.0))


def test_missing_score_or_duplicate_previous_rejects():
    r = rows()
    with pytest.raises(ValueError):
        bridge.select_global_signal(r, {})
    with pytest.raises(ValueError):
        bridge.select_global_signal(r, dict.fromkeys(r, 0), ("S001", "S001"))


def synthetic(monkeypatch):
    # Cross-year refresh is controlled by the continuous global calendar.
    start = date(2023, 12, 1)
    days = [
        (start + timedelta(days=i)).isoformat()
        for i in range(80)
        if (start + timedelta(days=i)).weekday() < 5
    ]
    history = {"calendar": days, "ranks": {d: rows() for d in days}, "bars": {d: {} for d in days}}
    proof = {"history_artifact_sha256": "a" * 64}
    calls = []
    monkeypatch.setattr(bridge, "verified_history", lambda *a, **kw: (history, proof))

    def guarded(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs["signal_date"] < kwargs["execution_date"]
        assert kwargs["model"]["year"] == int(kwargs["execution_date"][:4])
        return {n: float(i) for i, n in enumerate(kwargs["rows"])}

    monkeypatch.setattr(bridge, "guarded_predict", guarded)
    models = {
        year: {"year": year, "policy": "response", "training_provenance": proof}
        for year in (2023, 2024)
    }
    return history, models, calls


def test_prior_session_annual_model_continuous_calendar(monkeypatch):
    history, models, calls = synthetic(monkeypatch)
    targets, diagnostic, _ = bridge.frozen_targets(
        None,
        "original-consumer",
        history_path="synthetic",
        policy="global_response",
        models=models,
        paths={2023: "m23", 2024: "m24"},
    )
    expected = sum(
        i >= p + 1 and (i - p - 1) % 20 == 0
        for p in (0, 5, 10, 15)
        for i in range(len(history["calendar"]))
    )
    assert len(calls) == len(diagnostic) == expected
    assert not targets[0].rebalance
    assert {c["path"] for c in calls} == {"m23", "m24"}
    assert all(c["rows"] is history["ranks"][c["signal_date"]] for c in calls)
    assert all(max(t.weights.values(), default=0) <= 0.025 for t in targets)
    assert max(sum(t.weights.values()) for t in targets) == pytest.approx(1)
    assert all(d["selected"] == 40 for d in diagnostic)


@pytest.mark.parametrize("fault", ["policy", "year", "hash", "calendar"])
def test_frozen_boundary_rejected(monkeypatch, fault):
    history, models, _ = synthetic(monkeypatch)
    if fault == "policy":
        models[2023]["policy"] = "risk"
    if fault == "year":
        models[2023]["year"] = 2024
    if fault == "hash":
        models[2023]["training_provenance"] = {"history_artifact_sha256": "b" * 64}
    if fault == "calendar":
        history["calendar"].append("2025-01-01")
    with pytest.raises(ValueError):
        bridge.frozen_targets(
            None,
            "original",
            history_path="synthetic",
            policy="global_response",
            models=models,
            paths={2023: "m23", 2024: "m24"},
        )
