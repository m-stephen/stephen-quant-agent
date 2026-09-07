import json
from dataclasses import replace

import pytest
from test_flow_response_predictor import sample_pairs

from stephen_quant.discovery.flow_response_history import bind_shared_history_predictor
from stephen_quant.discovery.flow_response_predictor import fit_and_bind_predictor, stages
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.fit_lineage import UnsupervisedFitStage
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def fitted(tmp_path):
    # Relational shared-fit test; full source derivation is in history integration.
    pairs, calendar = sample_pairs()
    calendar += ["2024-01-02", "2024-01-03"]
    reg = ExperimentRegistry(tmp_path / "registry.sqlite3")
    sid = reg.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = reg.create_experiment(ExperimentSpec("shared", "synthetic", sid, "test-code"))
    params = {
        "response_policy": "response_interaction",
        "response_calendar_sha256": sha256_json(calendar),
    }
    spec = TrialSpec(
        eid,
        "predictor",
        "response",
        json.dumps(params),
        184,
        "2022-01-01",
        "2023-12-31",
        "2023-01-01",
        "2024-12-31",
        "unused",
        "unused",
        fit_stages=stages(),
    )
    provider, _ = reg.create_trial(
        replace(
            spec,
            model_name="provider",
            fit_stages=(
                UnsupervisedFitStage(
                    "provider", "2022-01-01", "2022-01-02", "2022-01-03", "2022-12-31"
                ),
            ),
        )
    )
    reg.declare_feature_sources(provider, ())
    consumers = {}
    for cost in (82, 164):
        tid, _ = reg.create_trial(
            replace(
                spec,
                model_name=f"policy-{cost}",
                hyperparams=json.dumps(params | {"roundtrip_bps": cost, "key": f"policy-{cost}"}),
            )
        )
        consumers[cost] = tid
        reg.declare_feature_sources(tid, (provider,))
    model = {
        "fit_kind": "unsupervised",
        "year": 2022,
        "fit_cutoff": "2022-01-02",
        "maximum_observation_at": "2022-01-02",
        "training_observation_sessions": ["2022-01-01", "2022-01-02"],
        "training_observation_dates": 2,
    }
    provider_path = tmp_path / "provider.json"
    provider_path.write_text(json.dumps(model), encoding="utf-8")
    reg.record_model_fit(provider, "provider", model=model, artifact_path=provider_path)
    reg.record_trial_result(
        provider,
        json.dumps(
            {
                "feature_provider_ready": True,
                "native_fit_lineage_sha256": reg.fit_lineage(provider)["sha256"],
            }
        ),
    )
    for tid in consumers.values():
        reg.bind_feature_source(tid, provider)
    history = tmp_path / "synthetic-history-placeholder.json"
    history.write_text('{"synthetic_relational_test_only":true}', encoding="utf-8")
    paths = {}
    for year in (2023, 2024):
        paths[year] = tmp_path / f"predictor-{year}.json"
        fit_and_bind_predictor(
            reg,
            consumers[82],
            provider,
            pairs=pairs,
            calendar=calendar,
            year=year,
            policy="response_interaction",
            artifact_path=paths[year],
            training_provenance={"history_artifact_sha256": file_sha(history)},
        )
    return reg, provider, consumers, calendar, history, paths


def test_both_years_exact_bytes_shared_without_refit(fitted, monkeypatch):
    reg, provider, consumers, calendar, history, paths = fitted
    before = {y: file_sha(p) for y, p in paths.items()}

    def poison(*args, **kwargs):
        raise AssertionError("shared cost must never numerically refit")

    monkeypatch.setattr("stephen_quant.discovery.flow_response_predictor.fit_predictor", poison)
    for year in (2023, 2024):
        bind_shared_history_predictor(
            reg,
            consumers[82],
            consumers[164],
            provider,
            history_path=history,
            model_path=paths[year],
            year=year,
            policy="response_interaction",
            calendar=calendar,
        )
    assert before == {y: file_sha(p) for y, p in paths.items()}
    assert reg.fit_lineage(consumers[82]) == reg.fit_lineage(consumers[164])
    assert reg.global_trial_count() == 3
    with reg.connect() as db:
        assert db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 5
    with pytest.raises(ValueError, match="unfitted"):
        bind_shared_history_predictor(
            reg,
            consumers[82],
            consumers[164],
            provider,
            history_path=history,
            model_path=paths[2023],
            year=2023,
            policy="response_interaction",
            calendar=calendar,
        )


@pytest.mark.parametrize("kind", ["matrix", "file", "calendar", "policy", "self"])
def test_shared_provenance_rejections(fitted, kind):
    reg, provider, consumers, calendar, history, paths = fitted
    policy, source_trial = "response_interaction", consumers[82]
    if kind == "matrix":
        history.write_text("{}", encoding="utf-8")
    elif kind == "file":
        paths[2023].write_text("{}", encoding="utf-8")
    elif kind == "calendar":
        calendar = calendar[:-1]
    elif kind == "policy":
        policy = "risk"
    else:
        source_trial = consumers[164]
    with pytest.raises(ValueError):
        bind_shared_history_predictor(
            reg,
            source_trial,
            consumers[164],
            provider,
            history_path=history,
            model_path=paths[2023],
            year=2023,
            policy=policy,
            calendar=calendar,
        )
