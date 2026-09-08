"""Mock/evidence tests only: never launch the four-cell native diagnostic here."""

import importlib.util
import json
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "account_runtime_diagnostic",
    Path(__file__).resolve().parents[1] / "scripts/diagnose_account_runtime.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CASE = ('<testcase classname="tests.test_flow_response_epoch" '
        'name="test_construction_complete_four_accounts_source_target_account_audit"/>')
GOOD = f'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">{CASE}</testsuite></testsuites>'


@pytest.mark.parametrize("xml", [
    "<testsuites/>", GOOD.replace('tests="1"', 'tests="2"'),
    GOOD.replace(CASE, CASE + CASE), GOOD.replace('errors="0"', 'errors="1"'),
    GOOD.replace('skipped="0"', 'skipped="1"'),
    GOOD.replace('failures="0"', 'failures="1"'),
    GOOD.replace("tests.test_flow_response_epoch", "tests.other"),
    GOOD.replace("test_construction_complete_four_accounts_source_target_account_audit", "other"),
    GOOD.replace("/>", "><skipped/></testcase>"),
    GOOD.replace("/>", "><failure/></testcase>"),
    GOOD.replace("/>", "><error/></testcase>"),
])
def test_exact_single_successful_node_only(tmp_path, xml):
    path = tmp_path / "pytest.xml"
    path.write_text(xml)
    with pytest.raises(ValueError):
        module.junit_one(path)


@pytest.mark.parametrize("trace,log,code,timeout,outcome", [
    (0, "", 0, False, "CONTROL_COMPLETED"),
    (120, "Timeout (0:02:00)!", 0, False, "NOT_REPRODUCED"),
    (120, "", 0, False, "NO_TIMER_EXPOSURE"),
    (0, "Timeout (0:02:00)!", 0, False, "UNEXPECTED_TIMER_EXPOSURE"),
    (120, "SIGSEGV", 255, False, "NATIVE_FAILURE"),
    (120, "SIGABRT", 0, False, "NATIVE_FAILURE"),
    (120, "SIGKILL", 255, False, "KILLED_OOM_UNPROVEN"),
    (0, "", 1, False, "PROCESS_FAILURE"),
    (120, "SIGSEGV", -9, True, "TIMEOUT"),
])
def test_verdict_keeps_failure_and_exposure_separate(tmp_path, trace, log, code, timeout, outcome):
    (tmp_path / "pytest.xml").write_text(GOOD)
    (tmp_path / "pytest.log").write_text(log)
    result = module.verdict(tmp_path, {"returncode": code, "timed_out": timeout}, trace)
    assert result["outcome"] == outcome
    assert not result["validated_alpha"] and not result["root_cause_proven"]
    assert not result["oom_proven"]


def test_missing_junit_is_not_success(tmp_path):
    (tmp_path / "pytest.log").write_text("Timeout (0:02:00)!")
    assert module.verdict(tmp_path, {"returncode": 0, "timed_out": False}, 120)[
        "outcome"] == "INCOMPLETE_OR_FAILED_JUNIT"


@pytest.mark.parametrize("survivor", [False, True])
def test_timeout_kills_whole_owned_group_even_if_parent_exited(tmp_path, monkeypatch, survivor):
    calls, kills = [], []
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)

    def wait(timeout):
        calls.append(timeout)
        if len(calls) == 1 or (survivor and len(calls) == 2):
            raise subprocess.TimeoutExpired("mock", timeout)
        return -9

    def popen(command, **kwargs):
        assert kwargs["start_new_session"] is True
        return SimpleNamespace(pid=123, wait=wait)

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    # GDB123 and inferior456 share SID123, regardless of their different PGIDs.
    snapshots = iter([{123: 10, 456: 20}, {456: 20}, {}])
    monkeypatch.setattr(module, "session_members", lambda sid: next(snapshots))
    monkeypatch.setattr(module, "signal_member",
                        lambda pid, start, sid, sig: kills.append((pid, sig)))
    monkeypatch.setitem(sys.modules, "resource", SimpleNamespace(
        RUSAGE_CHILDREN=-1, getrusage=lambda _: SimpleNamespace(ru_maxrss=100)))
    result = module.supervise(["never executed"], tmp_path, tmp_path, {})
    assert calls == [900, 5, 5]
    assert kills == [(123, signal.SIGTERM), (456, signal.SIGTERM), (456, signal.SIGKILL)]
    assert result["timed_out"] and result["children_maxrss_kib"] == 100
    assert result["cleanup"]["session_cleanup_complete"]


def test_replay_refused_before_output_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    with pytest.raises(ValueError, match="reruns refused"):
        module.run(tmp_path / "cell", "3.10.21", 0)
    assert not (tmp_path / "cell").exists()


def test_preflight_failure_preserved_without_child(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")

    def bad(*args):
        raise ValueError("dependency mismatch")

    monkeypatch.setattr(module, "snapshot", bad)
    with pytest.raises(ValueError, match="dependency mismatch"):
        module.run(tmp_path / "cell", "3.10.21", 120)
    assert (tmp_path / "cell/FAILED.json").exists()
    assert not (tmp_path / "cell/COMMAND.json").exists()
    with pytest.raises(FileExistsError):
        module.run(tmp_path / "cell", "3.10.21", 120)


def test_pin_versions():
    assert module.expected_packages("3.10.21")["numpy"] == "2.2.6"
    assert module.expected_packages("3.12.14")["numpy"] == "2.5.3"
    with pytest.raises(ValueError):
        module.expected_packages("3.12.13")


@pytest.mark.parametrize("changed", [False, True])
def test_mock_orchestration_binds_bytes_and_scrubs_child_env(tmp_path, monkeypatch, changed):
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("ALPHAPAI_API_KEY", "synthetic-secret")
    monkeypatch.setenv("ALPHAPAI_BASE_URL", "synthetic-url")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--irrelevant")
    snapshots = iter([{"synthetic": 1}, {"synthetic": 2 if changed else 1}])
    monkeypatch.setattr(module, "snapshot", lambda *a: next(snapshots))
    calls = []

    def supervise(command, root, output, env):
        calls.append(command)
        assert command[-1] == module.NODE
        assert command.count(module.NODE) == 1
        assert "faulthandler_timeout=120" in command
        assert env["PYTHONMALLOC"] == "debug"
        assert all(k not in env for k in ("ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL", "PYTEST_ADDOPTS"))
        (output / "pytest.log").write_text("Timeout (0:02:00)!")
        (output / "pytest.xml").write_text(GOOD)
        return {"returncode": 0, "timed_out": False}

    monkeypatch.setattr(module, "supervise", supervise)
    output = tmp_path / "cell"
    assert module.run(output, "3.10.21", 120) == int(changed)
    result = json.loads((output / "RESULT.json").read_text())
    assert result["outcome"] == ("BOUND_BYTES_CHANGED" if changed else "NOT_REPRODUCED")
    assert result["artifacts"]["pytest.xml"] == module.sha(output / "pytest.xml")
    assert len(calls) == 1
    with pytest.raises(FileExistsError):
        module.run(output, "3.10.21", 120)
    assert len(calls) == 1


def test_no_fixture_edits_and_standard_ci_remains_in_workflow():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    assert 'python: ["3.10.21", "3.12.14"]' in workflow
    assert 'trace: [0, 120]' in workflow
    assert workflow.count("fail-fast: false") == 2
    assert 'python: "3.10"\n            trace: 120' in workflow
    assert 'python: "3.10"\n            trace: 0' in workflow
    assert 'python: "3.12"\n            trace: 120' in workflow


def test_post_binding_error_preserves_native_failure_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    calls = []

    def snapshot(*a):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("changed package cannot be read")
        return {"synthetic": 1}

    def supervise(command, root, output, env):
        (output / "pytest.log").write_text("SIGSEGV")
        return {"returncode": 255, "timed_out": False, "children_maxrss_kib": 123}

    monkeypatch.setattr(module, "snapshot", snapshot)
    monkeypatch.setattr(module, "supervise", supervise)
    output = tmp_path / "cell"
    assert module.run(output, "3.10.21", 120) == 1
    process = json.loads((output / "PROCESS.json").read_text())
    result = json.loads((output / "RESULT.json").read_text())
    assert process["outcome"] == result["process_outcome"] == "NATIVE_FAILURE"
    assert process["returncode"] == result["returncode"] == 255
    assert process["children_maxrss_kib"] == 123
    assert result["outcome"] == "AFTER_BINDING_FAILURE"
    assert (output / "AFTER_ERROR.json").exists()


@pytest.mark.parametrize("identity", [{456: 20}, {456: 21}, {}, {999: 20}])
def test_pidfd_only_signals_matching_owned_starttime(monkeypatch, identity):
    sent, closed = [], []
    monkeypatch.setattr(module.os, "pidfd_open", lambda pid: 8, raising=False)
    monkeypatch.setattr(module.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(module.signal, "pidfd_send_signal",
                        lambda fd, sig: sent.append((fd, sig)), raising=False)
    monkeypatch.setattr(module, "session_members", lambda sid: identity)
    module.signal_member(456, 20, 123, signal.SIGTERM)
    assert sent == ([(8, signal.SIGTERM)] if identity == {456: 20} else [])
    assert closed == [8]


def test_proc_members_ignore_other_session_and_zombies(tmp_path, monkeypatch):
    for pid, state, pgid, sid, start in [(123, "S", 123, 123, 10),
                                      (456, "S", 456, 123, 20),
                                      (789, "S", 789, 789, 30),
                                      (800, "Z", 800, 123, 40)]:
        folder = tmp_path / str(pid)
        folder.mkdir()
        fields = [state, "1", str(pgid), str(sid)] + ["0"] * 15 + [str(start)]
        (folder / "stat").write_text(f"{pid} (name (with spaces)) " + " ".join(fields))
    real_path = Path
    monkeypatch.setattr(module, "Path", lambda value: tmp_path if value == "/proc" else real_path(value))
    assert module.session_members(123) == {123: 10, 456: 20}
