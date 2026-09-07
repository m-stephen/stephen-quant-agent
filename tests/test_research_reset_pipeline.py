import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pytest

from stephen_quant.baseline.stateful import run_stateful_execution
from stephen_quant.discovery.research_reset import runner, search
from stephen_quant.discovery.research_reset.accounts import (
    audit_account,
    execution_config,
    sessions_for,
    targets_for,
)
from stephen_quant.discovery.research_reset.contracts import Candidate, ResetSpec, evidence_state
from stephen_quant.discovery.research_reset.sources import generate
from stephen_quant.integrity.registry import ExperimentRegistry


@pytest.mark.parametrize(
    "key,value",
    [
        ("real_label_authorized", True),
        ("source_kind", "qd_daily"),
        ("automatic_next_epoch", True),
        ("historical_raw_attempts", 0),
        ("capital_cny", 20_000_000),
        ("horizons", (1, 20)),
        ("assets", 50),
    ],
)
def test_frozen_scope_fail_closed(key, value):
    with pytest.raises(ValueError):
        replace(ResetSpec(), **{key: value}).validate()


def test_contract_json_schema_and_identity():
    spec = ResetSpec()
    assert ResetSpec.from_dict(json.loads(json.dumps(spec.payload()))) == spec
    with pytest.raises(ValueError):
        ResetSpec.from_dict(spec.payload() | {"data_path": "somewhere"})
    a = Candidate("interaction", ("flow_state", "price_state"), 1, 5)
    b = replace(a, fields=a.fields[::-1])
    assert a.structure_id == b.structure_id
    assert len({a.identity(0), a.identity(82), a.identity(164), a.identity(82, "shuffle")}) == 4
    assert a.shared_candidate(82).candidate_id == a.identity(82)
    assert replace(a, parents=("a" * 64,)).structure_id == a.structure_id
    with pytest.raises(ValueError):
        Candidate("eval", ("flow_state",), 1, 5).validate()


def test_source_is_generated_frozen_and_oracle_is_not_public():
    panel, truth = generate(42, "linear", ResetSpec())
    repeated, _ = generate(42, "linear", ResetSpec())
    other, _ = generate(43, "linear", ResetSpec())
    assert panel.fingerprint() == repeated.fingerprint() != other.fingerprint()
    assert truth.expression
    assert not hasattr(panel, "oracle") and not hasattr(panel, "scenario")
    assert not hasattr(panel, "seed")
    with pytest.raises(ValueError):
        panel.features[0, 0, 0] = 5
    with pytest.raises(ValueError):
        generate(42, "real_market", ResetSpec())
    with pytest.raises(ValueError):
        replace(panel, source_kind="real").validate()


def test_training_selection_cannot_see_evaluation_labels():
    spec = ResetSpec()
    panel, _ = generate(44, "interaction", spec)
    a = search.discover(panel, spec, lambda *args: None)
    changed = panel.closing.copy()
    changed[spec.train_end + 1 :] *= 5
    b = search.discover(replace(panel, closing=changed), spec, lambda *args: None)
    assert a[0] == b[0]
    assert [(c.structure_id, score) for c, score in a[3]] == [
        (c.structure_id, score) for c, score in b[3]
    ]
    assert len(a[3]) == 48
    assert sum(bool(c.parents) for c, _ in a[3]) == 8


def test_delayed_fields_do_not_enter_ranks_and_rank_does_not_fit():
    panel, _ = generate(45, "linear", ResetSpec())
    ranks, support = search.feature_cache(panel)
    assert not ranks[~support].any()
    altered = panel.features.copy()
    altered[~support] = 1e100
    new_ranks, _ = search.feature_cache(replace(panel, features=altered))
    np.testing.assert_array_equal(ranks, new_ranks)
    assert "oracle" not in inspect.signature(search.discover).parameters


def test_future_features_cannot_change_past_targets():
    spec = ResetSpec()
    panel, _ = generate(46, "linear", spec)
    candidate = Candidate("rank", ("flow_state",), 1, 5)
    ranks, support = search.feature_cache(panel)
    a, _ = targets_for(panel, candidate, ranks, support, spec, "risk_signal")
    changed = ranks.copy()
    changed[150:] *= -1
    b, _ = targets_for(panel, candidate, changed, support, spec, "risk_signal")
    assert a[:51] == b[:51]  # day150 decision uses149; changed150 starts at151.


def test_native_accounts_and_independent_cash_mark_audit():
    spec = ResetSpec()
    panel, _ = generate(47, "correlated_null", spec)
    candidate = Candidate("rank", ("flow_state",), 1, 10)
    ranks, support = search.feature_cache(panel)
    targets, exposure = targets_for(panel, candidate, ranks, support, spec, "risk_signal")
    assert np.max(exposure) <= 1 / 6
    report = run_stateful_execution(
        sessions_for(panel, spec), targets, execution_config(82), initial_nav=spec.capital_cny
    )
    assert audit_account(report)["status"] == "PASS"
    bad = replace(report.periods[0], cash=report.periods[0].cash + 100)
    with pytest.raises(ValueError, match="cash"):
        audit_account(replace(report, periods=(bad,) + report.periods[1:]))


@pytest.fixture
def isolated_control(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "control_root", lambda: tmp_path / "control")
    monkeypatch.setattr(runner, "workspace_root", lambda: tmp_path)
    return tmp_path


def test_plan_consumption_and_pipeline_binding(isolated_control, monkeypatch):
    root = isolated_control
    path, envelope = runner.prepare_plan("audit")
    with pytest.raises(FileExistsError):
        runner.prepare_plan("audit")
    assert runner.verify_plan(path)[2] == envelope["sha256"]
    monkeypatch.setattr(runner, "code_manifest", lambda: {"changed": "a" * 64})
    with pytest.raises(ValueError, match="pipeline changed"):
        runner.run_plan(path, root / "artifacts" / "rejected")
    assert not (root / "control" / "claims").exists()


def test_failure_claim_cannot_be_replayed_in_new_output(isolated_control, monkeypatch):
    root = isolated_control
    path, _ = runner.prepare_plan("development", development_paths=1)

    def broken(*args, **kwargs):
        raise RuntimeError("intentional source failure")

    monkeypatch.setattr(runner, "generate", broken)
    output = root / "artifacts" / "failed"
    with pytest.raises(RuntimeError):
        runner.run_plan(path, output)
    assert runner.read_json(output / "TERMINAL.json")["calibration"] == "ENGINEERING_FAIL"
    with pytest.raises(FileExistsError):
        runner.run_plan(path, root / "artifacts" / "different-output")


def test_plan_duplicates_unknown_fields_and_external_outputs_rejected(isolated_control):
    root = isolated_control
    bad = root / "duplicates.json"
    bad.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        runner.read_json(bad)
    path, _ = runner.prepare_plan("development", development_paths=1)
    with pytest.raises(ValueError, match="workspace"):
        runner.run_plan(path, root / "outside")


def test_one_actual_full_path_records_all_trials_before_reads(tmp_path):
    spec = ResetSpec()
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    result, h = runner.run_path(54, "linear", spec, tmp_path / "path", "a" * 64, registry)
    assert len(h) == 64
    assert result["counts"]["label_structures"] == 48
    assert result["counts"]["native_trial_records"] == 62
    assert result["counts"]["account_runs"] == 12
    assert registry.counts()["trials"] == 62
    assert result["counts"]["oracle_account_runs"] == 2
    assert result["oracle_reference"]["used_for_selection"] is False
    assert result["oracle_reference"]["excluded_from_power_denominator"] is False
    assert result["counts"]["empirical_trials"] == 0
    events = [
        json.loads(line) for line in (tmp_path / "path" / "ledger.jsonl").read_text().splitlines()
    ]
    announced = set()
    for e in events:
        if e["event"] == "before_label_read":
            announced.add(e["structure_id"])
        if e["event"] == "training_score":
            assert e["structure_id"] in announced
    assert len(result["accounts"]) == 12
    assert result["new_fits"] == 0


def test_calibration_pass_is_not_authorization_or_alpha():
    state = evidence_state("PASS")
    assert not state["real_label_authorized"] and not state["validated_alpha"]
    assert state["court"]["status"] == "NOT_IDENTIFIABLE"
    assert state["court"]["dsr"] is None
    assert state["historical_raw_attempts"] == 3733


def test_identical_synthetic_source_path_replay_has_identical_result_hash(tmp_path):
    results = []
    for attempt in ("a", "b"):
        results.append(
            runner.run_path(
                65,
                "interaction",
                ResetSpec(),
                tmp_path / attempt / "same-path",
                "b" * 64,
                ExperimentRegistry(tmp_path / attempt / "registry.sqlite3"),
            )
        )
    assert results[0] == results[1]


def test_exclusive_claim_exactly_one_concurrent_writer(tmp_path):
    path = tmp_path / "claim.json"

    def claim(i):
        try:
            runner.write_new(path, {"worker": i})
            return True
        except FileExistsError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(8))) == 1
    assert runner.read_json(path)["worker"] in range(8)


def test_runtime_change_rejected_before_source(isolated_control, monkeypatch):
    path, _ = runner.prepare_plan("development", development_paths=1)
    monkeypatch.setattr(runner, "runtime_manifest", lambda: {"python": "changed"})
    with pytest.raises(ValueError, match="runtime"):
        runner.verify_plan(path)


def test_partial_failure_preserves_registered_attempt(isolated_control, monkeypatch):
    path, _ = runner.prepare_plan("development", development_paths=1)

    def broken(candidate, *args):
        raise RuntimeError("failure after label-read reservation")

    monkeypatch.setattr(search, "training_proxy", broken)
    output = isolated_control / "artifacts" / "partial"
    with pytest.raises(RuntimeError):
        runner.run_plan(path, output)
    terminal = runner.read_json(output / "TERMINAL.json")
    assert terminal["native_counts_including_incomplete_paths"]["trials"] == 1
    assert not terminal["completed_paths"]
    assert not terminal["validated_alpha"]


def test_resource_stop_is_not_null_success(isolated_control, monkeypatch):
    path, _ = runner.prepare_plan("audit")
    ticks = iter([0.0, 20000.0, 20001.0])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(ticks))
    result = runner.run_plan(path, isolated_control / "artifacts" / "resource-limit")
    assert result["calibration"] == "INCONCLUSIVE"
    assert result["native_counts"]["trials"] == 0
    assert result["scenarios"]["linear"]["n"] == 0


def test_complete_development_run_is_not_reserved_evidence(isolated_control):
    path, _ = runner.prepare_plan("development", development_paths=1)
    result = runner.run_plan(path, isolated_control / "artifacts" / "all-scenes")
    assert result["calibration"] == "NOT_TESTED"
    assert set(result["scenarios"]) == set(ResetSpec().scenarios)
    assert result["counts"]["physical_path_runs"] == 4
    assert result["counts"]["oracle_account_runs"] == 4
    assert result["native_counts"]["trials"] == 244
    assert result["counts"]["native_trial_records"] == 244


def test_cli_status_preserves_scope_without_registry(tmp_path, capsys, monkeypatch):
    from stephen_quant.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["stephen-quant", "research-reset", "status"])
    main()
    value = json.loads(capsys.readouterr().out)
    assert value["real_label_authorized"] is False
    assert value["scope"] == "M0-M2_SYNTHETIC_ONLY"
    assert not list(tmp_path.iterdir())
