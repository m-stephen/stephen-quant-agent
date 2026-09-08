"""Mocked launch-control contracts only; not the new supervised numerical E2E."""

import copy
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from stephen_quant.discovery import account_forensics_launch as runner
from stephen_quant.discovery.account_forensics_acceptance import read
from stephen_quant.discovery.account_forensics_plan import (
    CLAIM_KEY,
    ISSUE_URL,
    RISK_LINE,
    operation_path,
    scope,
)
from stephen_quant.discovery.flow_response_launch import LIMITS, now, write
from stephen_quant.discovery.response_supervisor import _sha
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def control(tmp_path, monkeypatch):
    root = tmp_path / "worktree"
    root.mkdir()
    (root / "fixture.py").write_text("# synthetic fixture", encoding="utf-8")
    fixed = {"worktree": root, "operations": root / "artifacts/account-forensics/epochs",
             "claim": tmp_path / "shared" / f"{CLAIM_KEY}.json"}
    code = {"files": {"fixture.py": file_sha(root / "fixture.py")}}
    plan = {"paths": {k: str(v) for k, v in fixed.items()}, "scope": scope(), "claim_key": CLAIM_KEY,
            "limits": asdict(LIMITS), "code": code, "runtime": {"synthetic": True}, "input_evidence": {},
            "calendar_binding": {"synthetic": True}, "source_calendar": [], "package_code": {}}
    plan_path = root / "plan.json"
    write(plan_path, plan)
    prereg = {"plan_sha256": sha256_json(plan), "fetched_at": now(), "comment": {"id": 123,
        "issue_url": ISSUE_URL,
        "body": f"V12.3-FORENSICS-PLAN-SHA256: {sha256_json(plan)}\n{RISK_LINE}",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}}
    monkeypatch.setattr(runner, "paths", lambda _: fixed)
    monkeypatch.setattr(runner, "require_host", lambda: None)
    monkeypatch.setattr(runner, "verify_plan", lambda p, _: sha256_json(p))
    monkeypatch.setattr(runner, "fetch_preregistration", lambda *a: prereg)
    monkeypatch.setattr(runner, "resource_guard", lambda _: {"synthetic": True})
    monkeypatch.setattr(runner, "code_snapshot", lambda _: code)
    monkeypatch.setattr(runner, "runtime_evidence", lambda: plan["runtime"])
    monkeypatch.setattr(runner, "verify_unchanged", lambda _: {"synthetic": True})
    acceptance, report = {"synthetic_acceptance": True}, {"synthetic_report": True}
    monkeypatch.setattr(runner, "_artifact_acceptance", lambda *a: acceptance)
    monkeypatch.setattr(runner, "verify_reports", lambda *a: report)
    calls = []
    def supervised(command, *, cwd, output, limits, evidence_hashes):
        calls.append((command, limits))
        assert fixed["claim"].is_file()  # consumed before starting a child.
        output.mkdir()
        start = {"command_sha256": _sha(command), "limits": asdict(limits),
                 "evidence_hashes": evidence_hashes, "automatic_retry": False, "started_at": now()}
        write(output / "START.json", start)
        receipt = {"outcome": "COMPLETED", "exit_code": 0, "evidence_hashes": evidence_hashes,
            "automatic_retry": False, "validated_alpha": False, "samples": 2, "pid": 123,
            "observed_peaks": {"peak_private_commit_bytes": 1},
            "minimum_free_physical_bytes": 8 * 1024**3, "plan_sha256": _sha(start)}
        write(output / "SUPERVISOR.json", receipt)
        operation = output.parent
        write(operation / "WORKER_STARTED.json", {"started_at": now(), "plan_sha256": sha256_json(plan),
                                                  "pid": 123, "automatic_retry": False})
        write(operation / "ACCEPTANCE.json", acceptance)
        rendered = operation / "saved-report/reader-report/RENDERED.json"
        write(rendered, report)
        write(operation / "WORKER_TERMINAL.json", {"outcome": runner.CHILD_SUCCESS,
            "plan_sha256": sha256_json(plan), "acceptance_sha256": file_sha(operation / "ACCEPTANCE.json"),
            "rendered_sha256": file_sha(rendered), "report": report, "automatic_retry": False,
            "validated_alpha": False})
        return receipt
    monkeypatch.setattr(runner, "supervise", supervised)
    return SimpleNamespace(root=root, fixed=fixed, plan=plan, path=plan_path, calls=calls, supervise=supervised)


def test_parent_only_success_and_once_only_shared_claim(control):
    result = runner.launch(control.path, comment_id=123, worktree=control.root)
    assert result["outcome"] == runner.SUCCESS and result["validated_alpha"] is False
    assert len(control.calls) == 1
    assert 0 < control.calls[0][1].wall_seconds <= LIMITS.wall_seconds
    operation = operation_path(control.plan)
    assert read(operation / "FINAL.json") == result
    assert read(control.fixed["claim"].with_suffix(".terminal.json")) == result
    with pytest.raises(FileExistsError):
        runner.launch(control.path, comment_id=123, worktree=control.root)
    assert len(control.calls) == 1


@pytest.mark.parametrize("bad", ["child_exit", "guard", "missing_receipt", "wrong_command", "wrong_pid", "altered_code", "report_mismatch", "parent_deadline"])
def test_no_partial_or_failed_child_can_become_final_success(control, monkeypatch, bad):
    def sabotage(*args, **kwargs):
        receipt = control.supervise(*args, **kwargs)
        operation = kwargs["output"].parent
        if bad in ("child_exit", "guard"):
            receipt["exit_code"] = 1
            receipt["outcome"] = "GUARD_STOPPED" if bad == "guard" else "FAILED"
            (kwargs["output"] / "SUPERVISOR.json").write_text(json.dumps(receipt))
        elif bad == "missing_receipt":
            (operation / "ACCEPTANCE.json").unlink()
        elif bad == "wrong_command":
            start = read(kwargs["output"] / "START.json")
            start["command_sha256"] = "a" * 64
            (kwargs["output"] / "START.json").write_text(json.dumps(start))
            receipt["plan_sha256"] = _sha(start)
            (kwargs["output"] / "SUPERVISOR.json").write_text(json.dumps(receipt))
        elif bad == "wrong_pid":
            path = operation / "WORKER_STARTED.json"
            start = read(path)
            start["pid"] = 999
            path.write_text(json.dumps(start))
        elif bad == "altered_code":
            monkeypatch.setattr(runner, "code_snapshot", lambda _: {})
        elif bad == "report_mismatch":
            monkeypatch.setattr(runner, "verify_reports", lambda *a: {"changed": True})
        else:
            def expired(_):
                raise ValueError("shared forensic deadline exhausted")
            monkeypatch.setattr(runner, "resource_guard", expired)
        return receipt
    monkeypatch.setattr(runner, "supervise", sabotage)
    with pytest.raises((ValueError, FileNotFoundError)):
        runner.launch(control.path, comment_id=123, worktree=control.root)
    assert read(control.fixed["claim"].with_suffix(".terminal.json"))["outcome"] == "FAILED"
    assert len(control.calls) == 1
    with pytest.raises((FileExistsError, ValueError)):
        runner.launch(control.path, comment_id=123, worktree=control.root)
    assert len(control.calls) == 1


def test_existing_shared_terminal_blocks_different_code_plan(control):
    write(control.fixed["claim"].with_suffix(".terminal.json"), {"old_failure": True})
    changed = copy.deepcopy(control.plan)
    changed["runtime"] = {"changed": True}
    changed_path = control.root / "changed-plan.json"
    write(changed_path, changed)
    with pytest.raises(FileExistsError):
        runner.launch(changed_path, comment_id=123, worktree=control.root)
    assert control.calls == []


@pytest.mark.parametrize("platform,version", [("linux", (3, 10, 9)), ("win32", (3, 12, 0)), ("win32", (3, 10, 21))])
def test_unreviewed_production_interpreter_refused(monkeypatch, platform, version):
    monkeypatch.setattr(runner, "sys", SimpleNamespace(platform=platform, version_info=version))
    with pytest.raises(ValueError):
        runner.require_host()


@pytest.mark.parametrize("bad", ["deadline", "private", "free", "measurement"])
def test_parent_resource_budget_is_not_reset(monkeypatch, bad):
    monkeypatch.setattr(runner, "monotonic", lambda: 14401.0 if bad == "deadline" else 3.0)
    values = {"peak_private_commit_bytes": 1, "physical_available_bytes": 8 * 1024**3}
    if bad == "private":
        values["peak_private_commit_bytes"] = LIMITS.private_commit_bytes
    elif bad == "free":
        values["physical_available_bytes"] = 1
    elif bad == "measurement":
        values["peak_private_commit_bytes"] = None
    monkeypatch.setattr(runner, "process_memory", lambda: values)
    with pytest.raises(ValueError):
        runner.resource_guard(0)


@pytest.fixture
def worker(control, monkeypatch):
    plan = control.plan
    root = operation_path(plan)
    root.mkdir(parents=True)
    prereg = runner.fetch_preregistration(123, sha256_json(plan), control.root)
    stamp = now()
    claim = {"version": "V12.3", "claim_key": CLAIM_KEY, "plan_sha256": sha256_json(plan),
        "operation": str(root), "preregistration_sha256": sha256_json(prereg), "scope": scope(),
        "started_at": stamp, "automatic_retry": False}
    write(control.fixed["claim"], claim)
    write(root / "PREREGISTRATION.json", prereg)
    envelope = {"plan": plan, "claim_sha256": file_sha(control.fixed["claim"]),
        "started_at": stamp, "deadline_at": (datetime.fromisoformat(stamp) + timedelta(seconds=LIMITS.wall_seconds)).isoformat(),
        "launcher_pid": 987, "child_limits": asdict(LIMITS)}
    write(root / "LAUNCH.json", envelope)
    command = [runner.sys.executable, str(control.root / runner.DRIVER), "worker", "--operation", str(root)]
    write(root / "supervisor/START.json", {"command_sha256": _sha(command), "limits": asdict(LIMITS),
        "evidence_hashes": runner._bindings(plan, envelope["claim_sha256"]), "automatic_retry": False})
    monkeypatch.setattr(runner.os, "getppid", lambda: 987)
    stages = []
    def build(*args, **kwargs):
        assert (root / "WORKER_STARTED.json").is_file()
        stages.append("build")
        kwargs["output"].mkdir()
    def accept(*args):
        stages.append("accept")
        return {"synthetic_acceptance": True}
    def render(saved, acceptance):
        assert read(root / "ACCEPTANCE.json") == acceptance
        stages.append("render")
        write(saved / "reader-report/RENDERED.json", {"synthetic_report": True})
    def verify(*args):
        stages.append("verify")
        return {"synthetic_report": True}
    monkeypatch.setattr(runner, "build_saved_report", build)
    monkeypatch.setattr(runner, "_artifact_acceptance", accept)
    monkeypatch.setattr(runner, "write_reports", render)
    monkeypatch.setattr(runner, "verify_reports", verify)
    return SimpleNamespace(root=root, control=control, stages=stages)


def test_worker_orders_all_steps_and_never_writes_parent_success(worker):
    runner.run_worker(worker.root, worker.control.root)
    assert worker.stages == ["build", "accept", "render", "verify"]
    assert read(worker.root / "WORKER_TERMINAL.json")["outcome"] == runner.CHILD_SUCCESS
    assert not (worker.root / "FINAL.json").exists()
    assert not worker.control.fixed["claim"].with_suffix(".terminal.json").exists()
    with pytest.raises(FileExistsError):
        runner.run_worker(worker.root, worker.control.root)
    assert worker.stages == ["build", "accept", "render", "verify"]


@pytest.mark.parametrize("method,stage", [("build_saved_report", "saved_report"),
    ("_artifact_acceptance", "external_artifact_acceptance"), ("write_reports", "bilingual_report"),
    ("verify_reports", "report_readback")])
def test_worker_failure_consumes_marker_and_preserves_exact_stage(worker, monkeypatch, method, stage):
    def failed(*args, **kwargs):
        raise ValueError("synthetic stage failure")
    monkeypatch.setattr(runner, method, failed)
    with pytest.raises(ValueError):
        runner.run_worker(worker.root, worker.control.root)
    terminal = read(worker.root / "WORKER_TERMINAL.json")
    assert terminal["outcome"] == "FAILED" and terminal["stage"] == stage
    assert (worker.root / "WORKER_STARTED.json").exists()
    assert not (worker.root / "FINAL.json").exists()
    with pytest.raises(FileExistsError):
        runner.run_worker(worker.root, worker.control.root)


@pytest.mark.parametrize("bad", ["parent", "missing_supervisor", "extra_stage_budget", "wrong_command"])
def test_unsupervised_or_rebudgeted_worker_refused_before_marker(worker, monkeypatch, bad):
    if bad == "parent":
        monkeypatch.setattr(runner.os, "getppid", lambda: 999)
    elif bad == "missing_supervisor":
        (worker.root / "supervisor/START.json").unlink()
    elif bad == "wrong_command":
        path = worker.root / "supervisor/START.json"
        obj = read(path)
        obj["command_sha256"] = "a" * 64
        path.write_text(json.dumps(obj))
    else:
        path = worker.root / "LAUNCH.json"
        obj = read(path)
        obj["child_limits"]["wall_seconds"] = LIMITS.wall_seconds * 2
        path.write_text(json.dumps(obj))
    with pytest.raises((ValueError, FileNotFoundError)):
        runner.run_worker(worker.root, worker.control.root)
    assert not (worker.root / "WORKER_STARTED.json").exists()
    assert worker.stages == []
