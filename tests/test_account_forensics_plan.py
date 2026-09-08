"""Metadata-only plan tests; all parent evidence is a temporary synthetic fixture."""

import copy
import json
import subprocess
from types import SimpleNamespace

import pytest
from test_account_forensics_inputs import synthetic_calendar

from stephen_quant.discovery import account_forensics_plan as plan
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def preparation(tmp_path, monkeypatch):
    root = tmp_path / "tree"
    source = root / "src/stephen_quant/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("# synthetic code\n", encoding="utf-8")
    driver = root / plan.DRIVER
    driver.parent.mkdir()
    driver.write_text("# synthetic driver\n", encoding="utf-8")
    original = tmp_path / "old-producer"
    original.mkdir()
    calendar = synthetic_calendar()
    old_plan = {"evidence": {"parent": {"calendar": calendar}},
                "spec": {"calendar": {"count": 726, "sha256": sha256_json(calendar)}}}
    launch = original / "LAUNCH.json"
    launch.write_text(json.dumps({"plan": old_plan}), encoding="utf-8")
    evidence = {"bindings": {"operation": {"root": str(original), "files": {"LAUNCH.json": file_sha(launch)}}}}
    monkeypatch.setattr(plan, "PLAN", sha256_json(old_plan))
    monkeypatch.setattr(plan, "CLAIM_KEY", sha256_json(plan.scope()))
    fixed_paths = {"worktree": root, "claim": tmp_path / "shared" / f"{plan.CLAIM_KEY}.json",
                   "operations": root / "artifacts/account-forensics/epochs"}
    monkeypatch.setattr(plan, "paths", lambda _: fixed_paths)
    monkeypatch.setattr(plan, "completed_inputs", lambda _: copy.deepcopy(evidence))
    def code(_):
        files = {"src/stephen_quant/example.py": file_sha(source)}
        return {"commit": "a" * 40, "files": files, "sha256": sha256_json(files)}
    monkeypatch.setattr(plan, "code_evidence", code)
    monkeypatch.setattr(plan, "runtime_evidence", lambda: {"synthetic_runtime": True})
    return root, source, driver, launch


def test_metadata_plan_fixed_scope_and_code_independent_claim(preparation):
    root, source, _, _ = preparation
    prepared = plan.prepare_plan(root)
    before = sha256_json(prepared)
    assert plan.verify_plan(prepared, root) == before
    assert prepared["scope"]["new_accounts"] == 0
    assert prepared["scope"]["raw_global_trial_lower_bound"] == 3737
    assert len(prepared["source_calendar"]) == 726
    assert len(prepared["scope"]["account_keys"]) == 12
    assert prepared["limits"]["wall_seconds"] == 14400
    assert prepared["limits"]["private_commit_bytes"] == 10 * 1024**3
    assert prepared["package_code"] == {"example.py": file_sha(source)}
    assert plan.operation_path(prepared).name == before
    source.write_text("# changed code\n", encoding="utf-8")
    after = plan.prepare_plan(root)
    assert sha256_json(after) != before
    assert after["claim_key"] == prepared["claim_key"]  # changing code cannot buy a new slot.
    with pytest.raises(ValueError):
        plan.verify_plan(prepared, root)


@pytest.mark.parametrize("bad", ["debt", "budget", "scope", "calendar", "limits", "claim", "runtime", "package", "original_bytes", "driver_bytes"])
def test_modified_plan_or_original_binding_rejected(preparation, bad):
    root, _, driver, original = preparation
    prepared = plan.prepare_plan(root)
    if bad == "debt":
        prepared["scope"]["raw_global_trial_lower_bound"] = 0
    elif bad == "budget":
        prepared["scope"]["new_accounts"] = 1
    elif bad == "scope":
        prepared["scope"]["account_keys"].pop()
    elif bad == "calendar":
        prepared["source_calendar"][0] = "2022-01-01"
    elif bad == "limits":
        prepared["limits"]["wall_seconds"] = 28800
    elif bad == "claim":
        prepared["claim_key"] = "b" * 64
    elif bad == "runtime":
        prepared["runtime"]["synthetic_runtime"] = False
    elif bad == "package":
        prepared["package_code"] = {}
    elif bad == "original_bytes":
        original.write_text("{}", encoding="utf-8")
    else:
        driver.write_text("# changed driver", encoding="utf-8")
    with pytest.raises(ValueError):
        plan.verify_plan(prepared, root)


def comment():
    return {"id": 123, "issue_url": plan.ISSUE_URL,
            "body": f"V12.3-FORENSICS-PLAN-SHA256: {'a'*64}\n{plan.RISK_LINE}",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}


@pytest.mark.parametrize("bad", ["id", "issue", "digest", "risk", "naive", "future", "reversed"])
def test_preregistration_requires_exact_scope_and_explicit_risk(bad):
    obj = comment()
    if bad == "id":
        obj["id"] = 123.0
    elif bad == "issue":
        obj["issue_url"] = plan.ISSUE_URL + "0"
    elif bad == "digest":
        obj["body"] = obj["body"].replace("a" * 64, "b" * 64)
    elif bad == "risk":
        obj["body"] = obj["body"].splitlines()[0]
    elif bad == "naive":
        obj["created_at"] = "2026-01-01T00:00:00"
    elif bad == "future":
        obj["updated_at"] = "9999-01-01T00:00:00Z"
    else:
        obj["updated_at"] = "2025-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        plan.validate_preregistration(obj, 123, "a" * 64)


def test_actual_api_fetch_is_fixed_and_bound(monkeypatch, tmp_path):
    calls = []
    def fetch(command, **kwargs):
        calls.append((command, kwargs))
        return json.dumps(comment()).encode()
    monkeypatch.setattr(plan.subprocess, "check_output", fetch)
    value = plan.fetch_preregistration(123, "a" * 64, tmp_path)
    assert value["comment"] == comment()
    assert calls[0][0] == ["gh", "api", "--hostname", "github.com", "repos/m-stephen/stephen-quant-agent/issues/comments/123"]
    assert calls[0][1]["timeout"] == 30
    assert "ALPHAPAI_API_KEY" not in calls[0][1]["env"]


def test_unavailable_api_does_not_fall_back_to_caller_approval(monkeypatch, tmp_path):
    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(plan.subprocess, "check_output", failed)
    with pytest.raises(ValueError, match="unavailable"):
        plan.fetch_preregistration(123, "a" * 64, tmp_path)


@pytest.mark.parametrize("value", [False, 0, -1, "123"])
def test_invalid_comment_identity_refused_without_network(monkeypatch, tmp_path, value):
    def unexpected(*args, **kwargs):
        raise AssertionError("network must not be invoked")
    monkeypatch.setattr(plan.subprocess, "check_output", unexpected)
    with pytest.raises(ValueError):
        plan.fetch_preregistration(value, "a" * 64, tmp_path)


def test_runtime_evidence_hashes_actual_native_bytes(monkeypatch, tmp_path):
    binary = tmp_path / "synthetic.pyd"
    binary.write_bytes(b"synthetic native byte fixture")
    monkeypatch.setattr(plan.importlib.util, "find_spec", lambda _: SimpleNamespace(origin=str(binary)))
    value = plan.runtime_evidence()
    assert set(value["native_binaries"]) == {"numpy", "duckdb"}
    assert all(v["sha256"] == file_sha(binary) for v in value["native_binaries"].values())
