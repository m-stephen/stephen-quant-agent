import json
import sqlite3
from dataclasses import replace

import pytest

from stephen_quant.discovery.residual_execution import fit_stages, guarded_targets
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import SCHEMA, ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


@pytest.fixture
def setup(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = registry.create_experiment(ExperimentSpec("synthetic", "lineage", sid, "synthetic-code"))
    spec = TrialSpec(
        eid,
        "model",
        "mechanism",
        "{}",
        184,
        "2022-01-01",
        "2023-12-31",
        "2023-01-01",
        "2024-12-31",
        "unused",
        "unused",
        fit_stages=fit_stages(),
    )
    return registry, spec


def model_file(tmp_path, year=2023):
    model = {
        "year": year,
        "training_signal_sessions": ["2022-01-03", f"{year - 1}-11-01"],
        "training_signal_dates": 2,
        "maximum_label_end": f"{year - 1}-12-01",
        "fit_cutoff": f"{year - 1}-12-23",
        "models": {"flow_reversal": {"slope": 0.3, "nuisance_z": [0] * 4}},
    }
    path = tmp_path / f"model-{year}.json"
    path.write_text(json.dumps(model))
    return model, path


def bind(registry, tid, model, path):
    return registry.record_model_fit(tid, str(model["year"]), model=model, artifact_path=path)


def test_two_years_native_complete_hash_and_replay(setup, tmp_path):
    registry, spec = setup
    tid, _ = registry.create_trial_deterministic(spec, "staged")
    first, path = model_file(tmp_path)
    one = bind(registry, tid, first, path)
    assert bind(registry, tid, first, path) == one
    with pytest.raises(ValueError, match="incomplete"):
        registry.record_trial_result(tid, "{}")
    second, path2 = model_file(tmp_path, 2024)
    two = bind(registry, tid, second, path2)
    assert two["training_end"] == "2023-12-23"
    assert two["training_signal_sessions"][-1] == "2023-11-01"
    assert two["code_version"] == "synthetic-code"
    assert len(two["snapshot_sha256"]) == 64
    assert (
        registry.assert_prediction_fit(
            tid,
            model=second,
            artifact_path=path2,
            prediction_date="2024-01-02",
            signal_date="2023-12-29",
        )
        == "2024"
    )
    registry.record_trial_result(tid, "{}")
    assert len(registry.fit_lineage(tid)["fits"]) == 2
    assert registry.create_trial_deterministic(spec, "staged")[0] == tid
    assert registry.global_trial_count() == 1
    with pytest.raises(ValueError, match="fit contract identity"):
        registry.create_trial_deterministic(replace(spec, fit_stages=()), "staged")


@pytest.mark.parametrize("mutation", ["future", "unordered", "empty", "count", "year", "before"])
def test_bad_fit_evidence_rejected(setup, tmp_path, mutation):
    registry, spec = setup
    tid, _ = registry.create_trial(spec)
    model, path = model_file(tmp_path)
    if mutation == "future":
        model["maximum_label_end"] = "2023-01-01"
    elif mutation == "unordered":
        model["training_signal_sessions"].reverse()
    elif mutation == "empty":
        model["training_signal_sessions"] = []
    elif mutation == "count":
        model["training_signal_dates"] = 3
    elif mutation == "year":
        model["year"] = 2024
    else:
        model["training_signal_sessions"][0] = "2021-12-01"
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError):
        registry.record_model_fit(tid, "2023", model=model, artifact_path=path)


def test_runtime_model_bytes_and_temporal_scope(setup, tmp_path):
    registry, spec = setup
    tid, _ = registry.create_trial(replace(spec, fit_stages=fit_stages((2023,))))
    model, path = model_file(tmp_path)
    bind(registry, tid, model, path)
    args = {
        "model": model,
        "artifact_path": path,
        "prediction_date": "2023-01-03",
        "signal_date": "2023-01-02",
    }
    for invalid in (
        {"signal_date": "2022-12-23"},
        {"prediction_date": "2024-01-02"},
        {"signal_date": "2023-01-03"},
    ):
        with pytest.raises(ValueError):
            registry.assert_prediction_fit(tid, **(args | invalid))
    model["models"]["flow_reversal"]["slope"] = 9
    with pytest.raises(ValueError, match="artifact bytes"):
        registry.assert_prediction_fit(tid, **args)
    path.write_text(json.dumps(model))
    with pytest.raises(ValueError, match="registered fit"):
        registry.assert_prediction_fit(tid, **args)
    with pytest.raises(ValueError, match="identity collision"):
        bind(registry, tid, model, path)


@pytest.mark.parametrize("table", ["trial_fit_contracts", "trial_model_fits"])
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_native_lineage_append_only(setup, tmp_path, table, action):
    registry, spec = setup
    tid, _ = registry.create_trial(spec)
    bind(registry, tid, *model_file(tmp_path))
    sql = f"DELETE FROM {table}" if action == "DELETE" else f"UPDATE {table} SET trial_id=trial_id"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), registry.connect() as conn:
        conn.execute(sql)


def test_legacy_and_explicit_no_fit_are_distinct(setup):
    registry, spec = setup
    old, _ = registry.create_trial(replace(spec, fit_stages=None))
    control, _ = registry.create_trial(replace(spec, fit_stages=()))
    registry.record_trial_result(old, "{}")
    registry.record_trial_result(control, "{}")
    with pytest.raises(ValueError, match="native fit contract"):
        registry.fit_lineage(old)
    assert registry.fit_lineage(control)["fits"] == []


def test_contract_invalid_rolls_back_trial_and_count(setup):
    registry, spec = setup
    for invalid in (
        (spec.fit_stages[0], spec.fit_stages[0]),
        (replace(spec.fit_stages[0], prediction_end="2024-02-01"), spec.fit_stages[1]),
        (replace(spec.fit_stages[0], training_not_after="2023-01-01"),),
    ):
        with pytest.raises(ValueError):
            registry.create_trial(replace(spec, fit_stages=invalid))
    assert registry.global_trial_count() == 0


def test_old_schema_upgrades_without_changing_old_rows(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO data_snapshots VALUES (?,?,?,?,?,?,?)",
            ("s", "created", "synthetic", "a" * 64, "{}", None, None),
        )
        conn.execute(
            "INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?)",
            ("e", "created", "synthetic", "old", "s", "old-code", "{}", "closed"),
        )
        conn.execute(
            "INSERT INTO trials VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "t",
                1,
                "created",
                "e",
                "old",
                "old",
                "{}",
                0,
                "2022-01-01",
                "2022-12-31",
                "2023-01-01",
                "2023-12-31",
                "2024-01-01",
                "2024-12-31",
                '{"completed":true}',
            ),
        )
        old_rows = conn.execute("SELECT * FROM trials").fetchall()
    registry = ExperimentRegistry(path)
    registry.initialize()
    with registry.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM trial_fit_contracts").fetchone()[0] == 0
        assert [tuple(r) for r in conn.execute("SELECT * FROM trials")] == old_rows
    assert registry.trial_result("t") == '{"completed":true}'


def test_guard_rejects_before_target_function_can_read_features(setup, monkeypatch):
    registry, spec = setup
    tid, _ = registry.create_trial(spec)
    called = []
    monkeypatch.setattr(
        "stephen_quant.discovery.residual_execution.targets_for", lambda *args: called.append(True)
    )
    with pytest.raises(ValueError, match="incomplete"):
        guarded_targets(registry, tid, (), {}, "flow_reversal", {})
    assert called == []
