import json
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.peer_information import (
    choose,
    fit_graph,
    peer_days,
    plans,
    risk_cells,
    signal_rows,
    stages,
    targets_for,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.integrity.fit_lineage import FitStage, contract_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def synthetic_days(count=220, size=48):
    rng = np.random.default_rng(184)
    cluster = rng.normal(0, 0.01, (count, (size + 15) // 16))
    noise = rng.normal(0, 0.001, (count, size))
    result = []
    for i in range(count):
        dt = str(date(2022, 1, 1) + timedelta(days=i))
        features = {
            f"n{j:03d}": {
                "volatility_20": 0.01 + j * 0.0001,
                "liquidity": 1e7 + j * 100,
                "ret_20": 0.02,
                "return1": float(cluster[i, j // 16] + noise[i, j]),
                "price": 0.001 * j,
                "flow": 0.01 * j,
            }
            for j in range(size)
        }
        result.append(ResearchDay(dt, features, ()))
    return tuple(result)


def test_graph_is_prefix_only_deterministic_and_no_self_edges():
    days = synthetic_days()
    model = fit_graph(days, 2023)
    future = ResearchDay("2023-01-03", {"poison": {"return1": float("nan")}}, ())
    assert fit_graph(days + (future,), 2023) == model
    assert len(model["graph"]) == 48
    assert model["fit_cutoff"] == days[-6].date
    assert "maximum_label_end" not in model
    for n, edges in model["graph"].items():
        assert len(edges) == 10
        assert n not in {p for p, _ in edges}
        assert all(0.15 <= w <= 1 for _, w in edges)
        assert all(x >= 120 for x in model["overlaps"][n])


def test_pairwise_missing_pearson_matches_numpy():
    days = list(synthetic_days())
    for i in range(0, 210, 7):
        values = dict(days[i].features)
        values.pop("n000")
        days[i] = replace(days[i], features=values)
    model = fit_graph(days, 2023)
    peer, actual = model["graph"]["n000"][0]
    x, y = [], []
    for day in days[:-5]:
        f = day.features
        if "n000" in f and peer in f:
            mean = sum(v["return1"] for v in f.values()) / len(f)
            x.append(f["n000"]["return1"] - mean)
            y.append(f[peer]["return1"] - mean)
    assert actual == pytest.approx(np.corrcoef(x, y)[0, 1], abs=1e-12)
    assert len(x) == model["overlaps"]["n000"][0]


def test_graph_shuffle_preserves_topology_weights_and_training_cells():
    model = fit_graph(synthetic_days(), 2023)
    perm = model["permutation"]
    assert set(perm) == set(perm.values()) == set(model["nodes"])
    assert any(a != b for a, b in perm.items())
    for group in risk_cells(model["training_risk"]).values():
        for names in group.values():
            assert {perm[n] for n in names} == set(names)
    for n, peers in model["graph"].items():
        assert model["shuffle"][perm[n]] == [[perm[p], w] for p, w in peers]


@pytest.mark.parametrize("issue", ["short", "unordered", "duplicate", "year", "nan"])
def test_graph_invalid_inputs(issue):
    days = synthetic_days()
    year = 2023
    if issue == "short":
        days = days[:100]
    elif issue == "unordered":
        days = tuple(reversed(days))
    elif issue == "duplicate":
        days = days + (days[-1],)
    elif issue == "year":
        year = 2025
    else:
        days[0].features["n000"]["return1"] = float("nan")
    with pytest.raises(ValueError):
        fit_graph(days, year)


def test_peer_series_gap_and_missing_flow_reset_without_future_use():
    days = []
    for i in range(15):
        dt = str(date(2022, 1, 1) + timedelta(days=i))
        f = {"volatility_20": 0.01, "liquidity": 1e7, "ret_20": 0.1, "net_inflow_ratio": 0.2}
        if i == 7:
            f.pop("net_inflow_ratio")
        bar = StatefulBar(dt, "firm", 10, 10 * 1.01**i, 1e6, dt + "T08:00:00+08:00")
        days.append(ResearchDay(dt, {} if i == 10 else {"firm": f}, (bar,)))
    rows = peer_days(days)
    assert "price" not in rows[4].features["firm"]
    assert rows[5].features["firm"]["price"] == pytest.approx(1.01**5 - 1)
    assert rows[5].features["firm"]["flow"] == 0.2
    assert "price" not in rows[7].features["firm"]
    assert "firm" not in rows[11].features
    assert "price" not in rows[14].features["firm"]
    assert peer_days(days[:7]) == rows[:7]


def test_common_support_requires_both_graphs_and_eight_current_peers():
    f = {
        f"n{i}": {
            "price": i / 100,
            "flow": i / 10,
            "volatility_20": 0.01,
            "liquidity": 1e7,
            "ret_20": 0,
        }
        for i in range(21)
    }
    graph = {"n0": [[f"n{i}", 0.5] for i in range(1, 11)]}
    shuffled = {"n0": [[f"n{i}", 0.5] for i in range(11, 21)]}
    model = {"graph": graph, "shuffle": shuffled}
    rows, n = signal_rows(f, model)
    assert n == 21 and rows["n0"]["price_peer"] == pytest.approx(0.055)
    for i in (11, 12):
        f.pop(f"n{i}")
    assert "n0" in signal_rows(f, model)[0]
    f.pop("n13")
    assert signal_rows(f, model)[0] == {}


def test_common_cell_gap_order_is_identical_to_negative_own():
    f = synthetic_days()[0].features
    names = sorted(f)
    for signal in ("price", "flow"):
        common = sum(f[n][signal] for n in names) / len(names)
        assert sorted(names, key=lambda n: (f[n][signal], n)) == sorted(
            names, key=lambda n: (-(common - f[n][signal]), n)
        )
        buckets = {str(i): names[i * 12 : (i + 1) * 12] for i in range(4)}
        selected = choose(f, buckets, (), signal, "own")
        assert len(selected) == 40
        assert choose(f, buckets, selected, signal, "own") == selected


def test_targets_next_open_no_warmup_position_and_no_future_mutation():
    f = synthetic_days()[0].features
    for v in f.values():
        v.update(price_peer=-v["price"], flow_peer=-v["flow"])
    buckets = {str(i): list(f)[i * 12 : (i + 1) * 12] for i in range(4)}
    days, cache = [], {}
    for i in range(50):
        dt = str(date(2023, 1, 2) + timedelta(days=i))
        days.append(ResearchDay(dt, f, ()))
        cache[dt] = (str(date(2023, 1, 1) + timedelta(days=i)), f, {"low": buckets})
    targets = targets_for(days, cache, "low", "price", "peer")
    assert not targets[0].weights
    assert max(targets[1].weights.values()) == 0.00625
    assert sum(targets[16].weights.values()) == pytest.approx(1)
    assert targets_for(days[:20], cache, "low", "price", "peer") == targets[:20]
    assert all(t.decided_at[:10] < t.trade_date for t in targets)


def make_registry(tmp_path, fit_stages=None):
    r = ExperimentRegistry(tmp_path / "registry.sqlite3")
    sid = r.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = r.create_experiment(ExperimentSpec("synthetic", "graph", sid, "code"))
    tid, _ = r.create_trial(
        TrialSpec(
            eid,
            "graph",
            "peers",
            "{}",
            184,
            "unused",
            "unused",
            "2023-01-01",
            "2023-12-31",
            "unused",
            "unused",
            fit_stages=stages()[:1] if fit_stages is None else fit_stages,
        )
    )
    model = {
        "fit_kind": "unsupervised",
        "year": 2023,
        "training_observation_sessions": ["2022-01-03", "2022-12-20"],
        "training_observation_dates": 2,
        "maximum_observation_at": "2022-12-20",
        "fit_cutoff": "2022-12-23",
        "graph": {"a": [["b", 0.5]]},
    }
    return r, tid, model


def test_unsupervised_native_lineage_is_not_synthetic_label_evidence(tmp_path):
    registry, tid, model = make_registry(tmp_path)
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    fit = registry.record_model_fit(tid, "2023", model=model, artifact_path=path)
    assert "maximum_label_end" not in fit
    assert "training_signal_sessions" not in fit
    assert fit["maximum_observation_at"] == "2022-12-20"
    registry.assert_prediction_fit(
        tid, model=model, artifact_path=path, prediction_date="2023-01-03", signal_date="2023-01-02"
    )
    registry.record_trial_result(tid, "{}")
    model["graph"]["a"][0][1] = 0.9
    with pytest.raises(ValueError):
        registry.assert_prediction_fit(
            tid,
            model=model,
            artifact_path=path,
            prediction_date="2023-01-03",
            signal_date="2023-01-02",
        )


@pytest.mark.parametrize(
    "mutation", ["future", "label", "count", "empty", "kind", "stage", "observation"]
)
def test_unsupervised_fail_closed(tmp_path, mutation):
    s = (FitStage("2023", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),)
    registry, tid, model = make_registry(tmp_path, s if mutation == "stage" else None)
    if mutation == "future":
        model["fit_cutoff"] = "2023-01-01"
    elif mutation == "label":
        model["maximum_label_end"] = "2022-12-21"
    elif mutation == "count":
        model["training_observation_dates"] = 3
    elif mutation == "empty":
        model["training_observation_sessions"] = []
    elif mutation == "kind":
        model["fit_kind"] = "unsupported"
    elif mutation == "observation":
        model["maximum_observation_at"] = "2022-12-21"
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError):
        registry.record_model_fit(tid, "2023", model=model, artifact_path=path)


def test_legacy_contract_serialization_and_budget_unchanged():
    stage = FitStage("y", "2022-01-01", "2022-12-31", "2023-01-01", "2023-12-31")
    assert "fit_kind" not in contract_json((stage,))
    assert len(plans()) == len({p["key"] for p in plans()}) == 50
    assert len({p["identity"] for p in plans() if p["policy"] == "peer"}) == 6
