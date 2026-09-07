import json
import os
import sys
from dataclasses import replace

import pytest

from stephen_quant.discovery import response_supervisor as module

LIMITS = module.ResourceLimits(1000, 100, 30)
EVIDENCE = {"synthetic_plan": "a" * 64}


@pytest.fixture
def controlled(monkeypatch):
    class Child:
        pid = 12345
        done = False
        terminated = False
        exit_status = 0

        def poll(self):
            return self.exit_status if self.done else None

        def terminate(self):
            self.terminated, self.done, self.exit_status = True, True, -15

        def wait(self, **kwargs):
            assert self.done
            return self.exit_status

    child, calls = Child(), []

    def spawn(*args, **kwargs):
        calls.append(1)
        assert kwargs["shell"] is False
        assert not ({k.upper() for k in kwargs["env"]} & module._SECRET_ENV)
        return child

    monkeypatch.setenv("ALPHAPAI_API_KEY", "test-secret-never-logged")
    monkeypatch.setenv("ALPHAPAI_BASE_URL", "test-endpoint-never-logged")
    monkeypatch.setattr(module, "_WINDOWS", True)
    monkeypatch.setattr(module, "process_memory", lambda: {"physical_available_bytes": 10000})
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    return child, calls


def run(tmp_path, **kwargs):
    return module.supervise(
        ["synthetic-only-command"],
        cwd=tmp_path,
        output=tmp_path / "operation",
        limits=kwargs.get("limits", LIMITS),
        evidence_hashes=EVIDENCE,
    )


def memory(commit=500, free=1000):
    return {
        "peak_rss_bytes": 400,
        "peak_private_commit_bytes": commit,
        "physical_available_bytes": free,
    }


def test_success_retains_bound_terminal_receipt_and_no_secrets(tmp_path, monkeypatch, controlled):
    child, calls = controlled

    def measure(process):
        assert process is child
        child.done = True
        return memory()

    monkeypatch.setattr(module, "child_process_memory", measure)
    result = run(tmp_path)
    assert result["outcome"] == "COMPLETED" and result["samples"] == 1
    assert not child.terminated and len(calls) == 1 and result["exit_code"] == 0
    start = json.loads((tmp_path / "operation/START.json").read_bytes())
    assert result["plan_sha256"] == module._sha(start)
    assert result["evidence_hashes"] == EVIDENCE
    assert json.loads((tmp_path / "operation/SUPERVISOR.json").read_bytes()) == result
    assert "test-secret" not in json.dumps(result) + json.dumps(start)
    with pytest.raises(FileExistsError):
        run(tmp_path)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "commit,free,reason",
    [
        (1000, 1000, "private_commit_limit"),
        (500, 99, "free_physical_floor"),
        (500, None, "free_memory_measurement_unavailable"),
    ],
)
def test_guard_stops_only_owned_child_and_records_failure(
    tmp_path, monkeypatch, controlled, commit, free, reason
):
    child, _ = controlled
    monkeypatch.setattr(module, "child_process_memory", lambda p: memory(commit, free))
    result = run(tmp_path)
    assert child.terminated and result["outcome"] == "GUARD_STOPPED"
    assert result["reason"] == reason and result["exit_code"] == -15
    assert not result["automatic_retry"] and not result["validated_alpha"]


@pytest.mark.parametrize("exception", [OSError, RuntimeError, MemoryError])
def test_measurement_exception_preserves_terminal_receipt(
    tmp_path, monkeypatch, controlled, exception
):
    child, _ = controlled

    def broken(process):
        raise exception("must not copy this arbitrary message into receipt")

    monkeypatch.setattr(module, "child_process_memory", broken)
    result = run(tmp_path)
    assert child.terminated and result["outcome"] == "FAILED"
    assert result["exception_type"] == exception.__name__
    assert result["exception_stage"] == "owned_measurement"
    assert (tmp_path / "operation/SUPERVISOR.json").is_file()
    assert "arbitrary message" not in json.dumps(result)


def test_timeout_is_a_recorded_guard_stop(tmp_path, monkeypatch, controlled):
    child, _ = controlled
    ticks = iter((0.0, 31.0, 32.0))
    monkeypatch.setattr(module.time, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(module, "child_process_memory", lambda p: memory())
    result = run(tmp_path)
    assert result["reason"] == "time_limit" and child.terminated


@pytest.mark.parametrize("free", [None, 99])
def test_prelaunch_resource_refusal_never_spawns(tmp_path, monkeypatch, controlled, free):
    child, calls = controlled
    monkeypatch.setattr(module, "process_memory", lambda: {"physical_available_bytes": free})
    result = run(tmp_path)
    assert result["outcome"] == "PRELAUNCH_REFUSED" and result["pid"] is None
    assert not calls and not child.terminated


def test_spawn_failure_is_recorded_without_claiming_a_child_exit(tmp_path, monkeypatch, controlled):
    def broken(*args, **kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(module.subprocess, "Popen", broken)
    result = run(tmp_path)
    assert result["exception_stage"] == "spawn"
    assert result["outcome"] == "FAILED" and result["exit_code"] is None


@pytest.mark.parametrize(
    "exit_status,reason", [(7, "child_exit_nonzero"), (0, "no_owned_memory_sample")]
)
def test_fast_or_failed_exit_is_not_resource_certification(
    tmp_path, controlled, exit_status, reason
):
    child, _ = controlled
    child.done, child.exit_status = True, exit_status
    result = run(tmp_path)
    assert result["outcome"] == "FAILED" and result["reason"] == reason
    assert result["observed_peaks"] == {}


def test_interrupt_records_then_propagates(tmp_path, monkeypatch, controlled):
    child, _ = controlled

    def interrupted(p):
        raise KeyboardInterrupt()

    monkeypatch.setattr(module, "child_process_memory", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path)
    assert child.terminated
    result = json.loads((tmp_path / "operation/SUPERVISOR.json").read_bytes())
    assert result["exception_type"] == "KeyboardInterrupt"


def test_cleanup_failure_does_not_claim_child_was_stopped(tmp_path, monkeypatch, controlled):
    child, _ = controlled
    monkeypatch.setattr(module, "child_process_memory", lambda p: memory(2000))

    def broken():
        raise OSError("simulated termination denied; no real process exists")

    monkeypatch.setattr(child, "terminate", broken)
    result = run(tmp_path)
    assert result["outcome"] == "TERMINATION_FAILED" and result["exit_code"] is None
    assert result["exception_stage"] == "cleanup" and not child.done


@pytest.mark.parametrize(
    "limits",
    [
        replace(LIMITS, private_commit_bytes=True),
        replace(LIMITS, minimum_free_physical_bytes=0),
        replace(LIMITS, wall_seconds=float("nan")),
        replace(LIMITS, wall_seconds="30"),
        replace(LIMITS, poll_seconds=2),
    ],
)
def test_invalid_limits_rejected_before_output(tmp_path, limits):
    with pytest.raises(ValueError):
        run(tmp_path, limits=limits)
    assert not (tmp_path / "operation").exists()


def test_unsupported_platform_retains_refusal_not_fake_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_WINDOWS", False)
    result = run(tmp_path)
    assert result["outcome"] == "PRELAUNCH_REFUSED"
    assert result["observed_peaks"] == {} and result["pid"] is None


@pytest.mark.skipif(os.name != "nt", reason="actual owned Windows child only")
def test_actual_hidden_owned_child_has_resource_receipt(tmp_path):
    result = module.supervise(
        [sys.executable, "-c", "import time; time.sleep(.4)"],
        cwd=tmp_path,
        output=tmp_path / "actual-child",
        limits=module.ResourceLimits(1024**3, 1, 10),
        evidence_hashes=EVIDENCE,
    )
    assert result["outcome"] == "COMPLETED" and result["exit_code"] == 0
    assert result["samples"] >= 1 and result["observed_peaks"]["peak_rss_bytes"] > 0
