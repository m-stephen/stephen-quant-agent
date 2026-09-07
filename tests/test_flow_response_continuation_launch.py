"""Synthetic once-only orchestration; never touches real claims or market data."""

import copy
import json
from pathlib import Path

import pytest
from test_flow_response_continuation import spec  # noqa: F401

from stephen_quant.discovery import flow_response_continuation_launch as m


@pytest.fixture
def fixture(tmp_path, monkeypatch, spec):  # noqa: F811
    root = tmp_path / "tree"
    root.mkdir()
    plan = {
        "version": m.VERSION,
        "claim_key": m.CLAIM_KEY,
        "paths": {"worktree": str(root), "claim": str(tmp_path / "common/once.json")},
        "spec": spec,
        "prior_debt": 3707,
        "budget": 22,
        "validated_alpha": False,
    }
    expected = copy.deepcopy(plan)
    monkeypatch.setattr(m, "prepare_plan", lambda _: copy.deepcopy(expected))
    monkeypatch.setattr(m, "fetch_preregistration", lambda i, d, _: {"id": i, "plan_sha256": d})
    monkeypatch.setattr(m, "_resource_preflight", lambda: {"physical_available_bytes": 8 * 1024**3})
    path = root / "plan.json"
    m.write(path, plan)
    return root, path, plan


def test_prepare_binds_new_driver_all_consumed_evidence_and_frozen_scope(
    tmp_path, monkeypatch, spec  # noqa: F811
):
    paths = {k: tmp_path / k for k in ("worktree", "claim", "inputs", "original", "old_operation")}
    consumed = {
        "prior_debt": 3707,
        "failed003": {"files": {k: {"sha256": v} for k, v in spec["inherited"]["files"].items()}},
        "B17": {"native_trials": 1, "original_verdict": "UNRESOLVED"},
    }
    m.write(
        paths["old_operation"] / "RESERVATIONS.json", {"trial_ids": spec["inherited"]["trial_ids"]}
    )
    monkeypatch.setattr(m, "continuation_paths", lambda *a: paths)
    monkeypatch.setattr(
        m, "code_evidence", lambda _: {"files": {"old_driver": "a" * 64}, "sha256": "b" * 64}
    )
    monkeypatch.setattr(m, "_bound", lambda *a: "c" * 64)
    monkeypatch.setattr(m, "consumed_evidence", lambda _: consumed)
    monkeypatch.setattr(
        m, "source_evidence", lambda _: ({"daily": "d" * 64, "flow": "e" * 64}, ["2023-01-03"])
    )
    monkeypatch.setattr(m, "original_evidence", lambda _: {"anchors": "f" * 64})
    plan = m.prepare_plan(tmp_path)
    assert plan["spec"]["accounts"] == m.account_plans()
    assert plan["spec"]["research_contract"] == m.contract()
    assert plan["spec"]["consumed_evidence_sha256"] == m.sha256_json(consumed)
    assert plan["spec"]["runtime_code_sha256"] == m.sha256_json(plan["evidence"]["code"]["files"])
    assert plan["evidence"]["code"]["files"][m.DRIVER] == "c" * 64
    assert plan["spec"]["inherited"]["files"] == spec["inherited"]["files"]
    assert plan["spec"]["new_fits"] == 0 and not plan["automatic_retry"]
    assert not paths["claim"].exists()


@pytest.mark.parametrize(
    "field,value", [("prior_debt", 0), ("budget", 2), ("validated_alpha", True)]
)
def test_changed_continuation_plan_refused_before_claim(fixture, field, value):
    root, path, plan = fixture
    plan[field] = value
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        m.launch(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("stage", ["fetch_preregistration", "_resource_preflight"])
def test_missing_preflight_does_not_consume_claim(fixture, monkeypatch, stage):
    root, path, plan = fixture

    def deny(*a, **kw):
        raise ValueError("synthetic preflight refusal")

    monkeypatch.setattr(m, stage, deny)
    with pytest.raises(ValueError, match="refusal"):
        m.launch(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("outcome", ["FAILED", "GUARD_STOPPED", "PRELAUNCH_REFUSED"])
def test_all22_native_reservations_precede_child_and_no_replay(fixture, monkeypatch, outcome):
    root, path, plan = fixture
    calls = []

    def child(command, **kw):
        calls.append(command)
        output = Path(command[-1])
        assert Path(plan["paths"]["claim"]).is_file()
        reg = m.ReadOnlyRegistry(output / "registry.sqlite3")
        receipt = m.read(output / "RESERVATIONS.json")
        assert reg.global_trial_count() == receipt["reserved"] == 22
        for tid in receipt["trial_ids"].values():
            assert not reg.fit_lineage(tid)["stages"]
            assert not reg.fit_lineage(tid)["fits"]
            assert not reg.feature_sources(tid)["providers"]
        return {"outcome": outcome, "exit_code": 1, "samples": 1}

    monkeypatch.setattr(m, "supervise", child)
    with pytest.raises(RuntimeError, match="no retry"):
        m.launch(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    terminal = m.read(claim.with_name("once.terminal.json"))
    assert terminal["raw_global_trial_lower_bound"] == 3729
    assert terminal["native_reserved"] == terminal["committed_attempt_budget"] == 22
    assert terminal["outcome"] == "FAILED" and not terminal["validated_alpha"]
    with pytest.raises(FileExistsError):
        m.launch(path, comment_id=1, worktree=root)
    assert len(calls) == 1


@pytest.mark.parametrize("partial", [False, True])
def test_reservation_failure_retains_full_budget_and_actual_count(fixture, monkeypatch, partial):
    root, path, plan = fixture
    actual = m.reserve_continuation

    def fail(output, frozen):
        if partial:
            actual(output, frozen)
        raise OSError("synthetic reservation failure")

    monkeypatch.setattr(m, "reserve_continuation", fail)
    with pytest.raises(OSError):
        m.launch(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    terminal = m.read(claim.with_name("once.terminal.json"))
    assert terminal["native_reserved"] == (22 if partial else 0)
    assert terminal["raw_global_trial_lower_bound"] == 3729
    assert terminal["committed_attempt_budget"] == 22


@pytest.mark.parametrize("kind", ["child", "terminal", "reservation", "native", "claim"])
def test_child_rejects_replay_or_mutation_before_backend(fixture, monkeypatch, kind):
    root, path, plan = fixture
    claim = Path(plan["paths"]["claim"])

    def forbidden(*a, **kw):
        raise AssertionError("numeric execution before complete once-only gates")

    monkeypatch.setattr(m, "execute_continuation", forbidden)

    def child(command, **kw):
        output = Path(command[-1])
        if kind == "child":
            m.write(output / "CHILD_backend.json", {})
        elif kind == "terminal":
            m.write(claim.with_name("once.terminal.json"), {})
        elif kind == "reservation":
            value = m.read(output / "RESERVATIONS.json")
            value["debt"] = 0
            (output / "RESERVATIONS.json").write_text(json.dumps(value), encoding="utf-8")
        elif kind == "native":
            with m.ExperimentRegistry(output / "registry.sqlite3").connect() as db:
                db.execute("UPDATE trials SET hyperparams='{}'")
        else:
            claim.write_text("{}", encoding="utf-8")
        with pytest.raises((ValueError, FileExistsError)):
            m.run_stage("backend", operation=output, worktree=root)
        if kind == "terminal":
            claim.with_name("once.terminal.json").unlink()  # Synthetic fixture only.
        return {"outcome": "FAILED", "exit_code": 1, "samples": 1}

    monkeypatch.setattr(m, "supervise", child)
    with pytest.raises(RuntimeError, match="no retry"):
        m.launch(path, comment_id=1, worktree=root)


@pytest.mark.parametrize("change", ["missing", "exit", "samples", "result", "registry"])
def test_independent_audit_requires_actual_completed_producer(tmp_path, change):
    m.write(tmp_path / "RESULT.json", {"synthetic": True})
    (tmp_path / "registry.sqlite3").write_bytes(b"synthetic immutable database bytes")
    supervisor = {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
    if change == "exit":
        supervisor["exit_code"] = 1
    elif change == "samples":
        supervisor["samples"] = 0
    m.write(tmp_path / "supervisor-backend/SUPERVISOR.json", supervisor)
    completed = {
        "result_sha256": m.file_sha(tmp_path / "RESULT.json"),
        "registry_sha256": m.file_sha(tmp_path / "registry.sqlite3"),
        "supervisor_sha256": m.file_sha(tmp_path / "supervisor-backend/SUPERVISOR.json"),
    }
    if change != "missing":
        m.write(tmp_path / "BACKEND_COMPLETED.json", completed)
    if change in ("result", "registry"):
        name = "RESULT.json" if change == "result" else "registry.sqlite3"
        with (tmp_path / name).open("ab") as stream:
            stream.write(b"\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        m._producer_completion(tmp_path)


def test_successful_exit_without_saved_supervision_is_not_completion(fixture, monkeypatch):
    root, path, plan = fixture
    monkeypatch.setattr(
        m, "supervise", lambda *a, **kw: {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
    )
    with pytest.raises(FileNotFoundError):
        m.launch(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    assert m.read(claim.with_name("once.terminal.json"))["outcome"] == "FAILED"


@pytest.mark.parametrize("change", [None, "alpha", "count", "fit", "debt", "statistics", "screen"])
def test_final_assessment_cannot_promote_or_drop_validation_obligations(
    tmp_path, monkeypatch, change
):
    completed = {"result_sha256": "a" * 64, "registry_sha256": "b" * 64}
    monkeypatch.setattr(m, "_producer_completion", lambda _: completed)
    audit = {
        "pipeline_audit_pass": True,
        "validated_alpha": False,
        "launch_authorization_verified": False,
        "new_native_accounts_checked": 22,
        "new_fits": 0,
        "raw_global_trial_lower_bound": 3729,
        "result_sha256": completed["result_sha256"],
        "native_registry_sha256": completed["registry_sha256"],
        "statistics": m.contract()["statistics"],
        "audited_screen": {"synthetic": False},
    }
    if change == "alpha":
        audit["validated_alpha"] = True
    elif change == "count":
        audit["new_native_accounts_checked"] = 20
    elif change == "fit":
        audit["new_fits"] = 1
    elif change == "debt":
        audit["raw_global_trial_lower_bound"] = 22
    elif change == "statistics":
        audit["statistics"] = {"DSR": 0.99}
    m.write(tmp_path / "AUDIT.json", audit)
    assessment = {
        "validated_alpha": False,
        "plan_sha256": "c" * 64,
        "result_sha256": completed["result_sha256"],
        "audit_sha256": m.file_sha(tmp_path / "AUDIT.json"),
        "audited_screen": {"synthetic": change == "screen"},
        "statistics": m.contract()["statistics"],
    }
    m.write(tmp_path / "ASSESSMENT.json", assessment)
    if change is None:
        m._verify_assessment(tmp_path, "c" * 64)
    else:
        with pytest.raises(ValueError, match="exploratory audit"):
            m._verify_assessment(tmp_path, "c" * 64)
