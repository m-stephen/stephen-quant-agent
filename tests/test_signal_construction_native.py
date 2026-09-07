"""Real native ledger/model/cache integration with entirely synthetic sources.

No market history is opened and these fixture fits are not empirical attempts.
Unlike allocation unit tests, native guarded_predict/VerifiedHistoryCache are
not mocked. Original source/predictor APIs construct the actual byte bindings.
"""

import json
from dataclasses import asdict, replace

import pytest
from test_flow_response_history import frozen_sources

from stephen_quant.discovery.flow_response_history import (
    VERSION,
    VerifiedHistoryCache,
    build_history_from_frozen,
    fit_history_predictor,
)
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.flow_response_predictor import guarded_predict, stages
from stephen_quant.discovery.flow_response_series import DAILY_SUPPORT, response_stages
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.signal_construction import frozen_targets
from stephen_quant.discovery.signal_construction_audit import audit_targets, independent_targets
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture(scope="module")
def native_bridge(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-signal-bridge")
    days, manifest = frozen_sources(root / "inputs", span_days=800, stock_count=80)
    registry = ExperimentRegistry(root / "registry.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic": manifest}))
    eid = registry.create_experiment(
        ExperimentSpec("bridge-fixture", "SYNTHETIC ONLY", sid, "test")
    )
    params = {
        "response_history_version": VERSION,
        "response_support_policy": DAILY_SUPPORT,
        "response_manifest_sha256": manifest,
        "response_calendar_sha256": sha256_json(days),
    }
    spec = TrialSpec(
        eid,
        "provider",
        "liquidity_impact_absorption",
        json.dumps(params),
        184,
        "2022-01-01",
        "2022-12-31",
        "2023-01-01",
        "2024-12-31",
        "unused",
        "unused",
        fit_stages=response_stages(days),
    )
    provider, _ = registry.create_trial(spec)
    registry.declare_feature_sources(provider, ())
    consumers = {}
    for policy in ("response", "risk"):
        tid, _ = registry.create_trial(
            replace(
                spec,
                model_name=policy,
                hyperparams=json.dumps(params | {"response_policy": policy}),
                fit_stages=stages(),
            )
        )
        registry.declare_feature_sources(tid, (provider,))
        consumers[policy] = tid
    history = build_history_from_frozen(
        registry,
        provider,
        tuple(consumers.values()),
        input_folder=root / "inputs",
        output_folder=root / "history",
        calendar=days,
        manifest_sha256=manifest,
    )
    cache = VerifiedHistoryCache(registry, consumers["response"], history)
    models, paths = {}, {}
    for policy, consumer in consumers.items():
        models[policy], paths[policy] = {}, {}
        for year in (2023, 2024):
            paths[policy][year] = root / f"{policy}-{year}.json"
            models[policy][year] = fit_history_predictor(
                registry,
                consumer,
                provider,
                history_path=history,
                year=year,
                policy=policy,
                model_path=paths[policy][year],
                cache=cache,
            )
    return registry, consumers, history, cache, models, paths


def targets(fixture, policy="response", consumer=None):
    reg, consumers, history, cache, models, paths = fixture
    return frozen_targets(
        reg,
        consumer or consumers[policy],
        history_path=history,
        policy="global_" + policy,
        models=models[policy],
        paths=paths[policy],
        cache=cache,
    )


@pytest.mark.parametrize("policy", ["response", "risk"])
def test_native_models_cache_and_years_work_without_new_fits(native_bridge, policy):
    reg, _, _, _, _, _ = native_bridge
    with reg.connect() as db:
        before = db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]
    allocations, diagnostics, _ = targets(native_bridge, policy)
    assert {d["execution_date"][:4] for d in diagnostics} == {"2023", "2024"}
    assert all(d["date"] < d["execution_date"] for d in diagnostics)
    assert allocations and len(diagnostics) > 20
    assert reg.global_trial_count() == 3
    with reg.connect() as db:
        assert db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == before


def test_wrong_native_consumer_rejected(native_bridge):
    with pytest.raises(ValueError):
        targets(native_bridge, consumer=native_bridge[1]["risk"])


def test_actual_model_byte_change_rejected_then_restored(native_bridge):
    path = native_bridge[5]["response"][2023]
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ValueError):
            targets(native_bridge)
    finally:
        path.write_bytes(original)


def test_future_native_fit_cannot_predict_prior_year(native_bridge):
    reg, consumers, history, cache, models, paths = native_bridge
    document, _ = cache.get(reg, consumers["response"], history)
    days = [d for d in document["calendar"] if d.startswith("2023")]
    with pytest.raises(ValueError):
        guarded_predict(
            reg,
            consumers["response"],
            model=models["response"][2024],
            path=paths["response"][2024],
            signal_date=days[2],
            execution_date=days[3],
            rows=document["ranks"][days[2]],
        )


def test_changed_actual_history_invalidates_cache(native_bridge):
    path = native_bridge[2]
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n")
        with pytest.raises(ValueError):
            targets(native_bridge)
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("policy", ["response", "risk"])
def test_independent_reference_reproduces_actual_native_scores_and_targets(
    native_bridge, policy, monkeypatch
):
    reg, consumers, history, cache, models, _ = native_bridge
    actual, diagnostics, _ = targets(native_bridge, policy)
    document, _ = cache.get(reg, consumers[policy], history)
    from stephen_quant.discovery import flow_response_predictor

    monkeypatch.setattr(
        flow_response_predictor,
        "predict",
        lambda *a: pytest.fail("reference called production predictor"),
    )
    expected, reference = independent_targets(document, "global_" + policy, models[policy])
    assert sha256_json([asdict(t) for t in actual]) == sha256_json(expected)
    assert diagnostics == reference


@pytest.mark.parametrize("fault", ["target", "scores", "membership"])
def test_independent_reference_rejects_rehashed_altered_outputs(native_bridge, tmp_path, fault):
    reg, consumers, history, cache, models, _ = native_bridge
    document, _ = cache.get(reg, consumers["response"], history)
    result = {"targets_sha256": {}, "diagnostics": {}}
    for policy in ("response", "risk"):
        actual, diagnostics, _ = targets(native_bridge, policy)
        raw = [asdict(t) for t in actual]
        if policy == "response":
            if fault == "target":
                raw[1]["weights"] = {"outside-support": 0.25}
            if fault == "scores":
                diagnostics[0]["scores_sha256"] = "a" * 64
            if fault == "membership":
                diagnostics[0]["new_members"] += 1
        name = "global_" + policy
        path = tmp_path / f"targets/{name}.json"
        write(path, raw)
        result["targets_sha256"][name] = file_sha(path)
        result["diagnostics"][name] = diagnostics
    with pytest.raises(ValueError, match="independent score"):
        audit_targets(tmp_path, result, document, models)
