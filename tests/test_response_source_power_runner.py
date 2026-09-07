"""Synthetic orchestration safeguards; no market inputs or model search."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/run_response_source_power.py"
    spec = importlib.util.spec_from_file_location("response_source_power_test_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_case_rejects_changed_frozen_plan_before_source_generation(tmp_path, runner, monkeypatch):
    (tmp_path / "CALIBRATION_PLAN.json").write_text('{"version":1}', encoding="utf-8")
    monkeypatch.setattr(runner, "fixed_plan", lambda: {"version": 2})

    def forbidden(*args, **kwargs):
        pytest.fail("source generation reached despite a changed frozen plan")

    monkeypatch.setattr(runner, "write_synthetic_sources", forbidden)
    with pytest.raises(ValueError, match="code/plan changed"):
        runner.run_case(tmp_path, "planted")
    assert not (tmp_path / "planted").exists()


def test_existing_operation_cannot_be_replayed(tmp_path, runner, monkeypatch):
    monkeypatch.setattr(runner, "fixed_plan", lambda: pytest.fail("existing output accepted"))
    with pytest.raises(FileExistsError):
        runner.run(tmp_path)


def test_failed_child_retains_evidence_and_does_not_retry(tmp_path, runner, monkeypatch):
    output = tmp_path / "failed"
    calls = []
    monkeypatch.setattr(runner, "fixed_plan", lambda: {"version": 1})
    monkeypatch.setenv("ALPHAPAI_API_KEY", "synthetic-secret-never-forward")
    monkeypatch.setenv("ALPHAPAI_BASE_URL", "synthetic-endpoint-never-forward")

    def failed(args, **kwargs):
        calls.append(args[-1])
        assert "ALPHAPAI_API_KEY" not in kwargs["env"]
        assert "ALPHAPAI_BASE_URL" not in kwargs["env"]
        assert kwargs["check"] is False
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(runner.subprocess, "run", failed)
    with pytest.raises(RuntimeError, match="preserve all artifacts"):
        runner.run(output)
    assert calls == ["planted"]
    evidence = json.loads((output / "CALIBRATION_ABORTED.json").read_bytes())
    assert evidence == {
        "children": [{"case": "planted", "exit_code": 7}],
        "empirical_trial_delta": 0,
    }
    assert (output / "CALIBRATION_PLAN.json").exists()
    assert not (output / "CALIBRATION_RESULT.json").exists()


@pytest.mark.parametrize("power_pass", [False, True])
def test_pair_keeps_negative_results_and_never_claims_alpha(
    tmp_path, runner, monkeypatch, power_pass
):
    output = tmp_path / "paired"
    calls = []
    monkeypatch.setattr(runner, "fixed_plan", lambda: {"version": 1})

    def completed(args, **kwargs):
        case = args[-1]
        calls.append(case)
        (output / case).mkdir()
        runner.write_json(
            output / case / "ASSESSMENT.json",
            {"case": case, "source_power_checks_pass": power_pass or case == "null"},
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", completed)
    runner.run(output)
    result = json.loads((output / "CALIBRATION_RESULT.json").read_bytes())
    assert calls == ["planted", "null"]
    assert set(result["cases"]) == {"planted", "null"}
    assert result["all_source_power_checks_pass"] is power_pass
    assert result["synthetic_native_reservations"] == 46
    assert result["empirical_trial_delta"] == 0
    assert result["validated_alpha"] is False
