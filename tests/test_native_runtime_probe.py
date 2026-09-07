"""Test orchestration without consuming the twelve real diagnostic processes."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "native_probe", Path(__file__).resolve().parents[1] / "scripts/probe_native_runtime.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_fixed_budget():
    assert len(module.PLAN) == 12
    assert len({tuple(arm.items()) for arm in module.PLAN}) == 12
    assert module.SECONDS == 5
    assert module.PROCESS_TIMEOUT == 15
    for workload in ("frames", "variance"):
        for timer in (0, .05):
            assert [a["replicate"] for a in module.PLAN
                    if a["workload"] == workload and a["timer"] == timer] == [1, 2, 3]


@pytest.mark.parametrize("mode", ["ok", "crash", "timeout", "missing", "no_dump", "spawn"])
def test_owned_probe_records_each_outcome(tmp_path, monkeypatch, mode):
    calls = []

    def execute(command, *, stdout, stderr, timeout, check):
        calls.append(command)
        assert timeout == 15 and check is False
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        if mode == "spawn":
            raise OSError("synthetic spawn refusal")
        if mode != "missing":
            stdout.write(json.dumps({"completed": True, "elapsed_seconds": 5, "iterations": 1}))
        if mode != "no_dump":
            stderr.write("Timeout (0:00:00.050000)!\n")
        return subprocess.CompletedProcess(command, -11 if mode == "crash" else 0)

    monkeypatch.setattr(module.subprocess, "run", execute)
    result = module.run_probe(tmp_path, 1, {"workload": "frames", "timer": .05, "replicate": 1})
    assert len(calls) == 1
    assert result["execution_ok"] is (mode == "ok")
    assert result["timed_out"] is (mode == "timeout")
    assert (tmp_path / "probe-01.json").is_file()
    with pytest.raises(FileExistsError):
        module.run_probe(tmp_path, 1, {"workload": "frames", "timer": .05, "replicate": 1})
    assert len(calls) == 1


@pytest.mark.parametrize("unexpected_dump", [False, True])
def test_timer_off_control_requires_no_scheduled_dump(tmp_path, monkeypatch, unexpected_dump):
    def execute(command, *, stdout, stderr, timeout, check):
        stdout.write(json.dumps({"completed": True, "elapsed_seconds": 5, "iterations": 2}))
        if unexpected_dump:
            stderr.write("Timeout (0:00:00.050000)!\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", execute)
    result = module.run_probe(tmp_path, 1, {"workload": "variance", "timer": 0, "replicate": 1})
    assert result["execution_ok"] is (not unexpected_dump)
    assert result["dump_count"] == int(unexpected_dump)


def test_failure_does_not_expand_budget_or_erase_claim(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(module, "metadata", lambda: {"synthetic_test": True})

    def probe(output, index, arm):
        calls.append((index, arm))
        return {"execution_ok": index != 2}

    monkeypatch.setattr(module, "run_probe", probe)
    output = tmp_path / "diagnostic"
    assert module.run(output) == 1
    assert len(calls) == 12
    result = json.loads((output / "result.json").read_text())
    assert result["executed"] == 12
    assert result["root_cause_proven"] is False
    with pytest.raises(FileExistsError):
        module.run(output)
    assert len(calls) == 12
