"""Synthetic completed files only; no market sources or numerical launch."""

import json
from pathlib import Path

import pytest

from stephen_quant.discovery import account_forensics_evidence as evidence
from stephen_quant.qmt.reliable_panel import file_sha


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return file_sha(path)


def group(root, name):
    records, files = {}, {}
    policies = (evidence.GROUPED_ARCHIVE_POLICIES if name == "grouped"
                else evidence.GROUPS[name])
    for policy in policies:
        for cost in (82, 164):
            key = f"{policy}-{cost}"
            row = {}
            for relative, field in (
                (f"accounts/{key}.jsonl", "account_sha256"),
                (f"account_reports/{key}.json", "full_account_sha256"),
                (f"targets/{policy}.json", "target_sha256"),
            ):
                files[relative] = row[field] = put(root, relative, {"synthetic": relative})
            records[key] = row
    files["RESULT.json"] = put(root, "RESULT.json", {"records": records})
    return {"root": str(root), "files": files}


@pytest.mark.parametrize("name", list(evidence.GROUPS))
def test_fixed_complete_group(tmp_path, name):
    bound = group(tmp_path, name)
    result = evidence.fixed_accounts(name, tmp_path, bound["files"])
    assert len(result["accounts"]) == 4
    assert len(result["files"]) == 11
    assert all(key.startswith(name + "/") for key in result["accounts"])
    assert len(result["archive_account_keys"]) == (22 if name == "grouped" else 4)
    assert "account_reports/shuffle-82.json" not in result["files"]


@pytest.mark.parametrize("change", ["omit", "extra", "contradiction", "changed_bytes"])
def test_account_selection_and_tampering_rejected(tmp_path, change):
    bound = group(tmp_path, "grouped")
    result = json.loads((tmp_path / "RESULT.json").read_text())
    if change == "omit":
        result["records"].pop("risk-164")
    elif change == "extra":
        result["records"]["posthoc-82"] = result["records"]["risk-82"]
    elif change == "contradiction":
        result["records"]["risk-82"]["account_sha256"] = "a" * 64
    else:
        put(tmp_path, "accounts/risk-82.jsonl", {"changed": True})
    bound["files"]["RESULT.json"] = put(tmp_path, "RESULT.json", result)
    with pytest.raises(ValueError):
        evidence.fixed_accounts("grouped", tmp_path, bound["files"])


@pytest.mark.parametrize("name", ["../outside", "a/../../outside"])
def test_escape_refused_before_bound_read(tmp_path, monkeypatch, name):
    monkeypatch.setattr(evidence, "_bound", lambda *a: pytest.fail("must not read escaped path"))
    with pytest.raises(ValueError, match="nonescaping"):
        evidence.bind_files(tmp_path, {name: "a" * 64})


def test_absolute_refused(tmp_path):
    with pytest.raises(ValueError):
        evidence.bind_files(tmp_path, {str(tmp_path / "outside"): "a" * 64})


@pytest.mark.parametrize("digest", [None, True, "A" * 64, "g" * 64, "abc"])
def test_bad_hash_refused(tmp_path, digest):
    with pytest.raises(ValueError, match="SHA-256"):
        evidence.bind_files(tmp_path, {"input.json": digest})


def test_after_hash_detects_change_without_writing(tmp_path):
    digest = put(tmp_path, "source.json", {"v": 1})
    manifest = {"bindings": {"sources": evidence.bind_files(tmp_path, {"source.json": digest})}}
    assert evidence.verify_unchanged(manifest)["input_bytes_unchanged"]
    new_hash = put(tmp_path, "source.json", {"v": 2})
    with pytest.raises(ValueError):
        evidence.verify_unchanged(manifest)
    assert file_sha(tmp_path / "source.json") == new_hash


@pytest.fixture
def completed(tmp_path, monkeypatch):
    shared = tmp_path / "claims"
    producer = tmp_path / "worktrees/v12.2-signal-construction"
    # Synthetic plan uses a fixed placeholder; only the lower-level plan hash seam is mocked.
    root = producer / f"artifacts/signal-construction/epochs/{evidence.PLAN}"
    current = group(root, "construction")
    parent = group(tmp_path / "baseline", "global_baselines")
    parent["saved_grouped_comparators"] = group(tmp_path / "grouped", "grouped")
    history = tmp_path / "history"
    inherited = {"root": str(history), "files": {
        "history/history.json": put(history, "history/history.json", {"synthetic": True})}}
    inputs = tmp_path / "inputs"
    sources = {name: put(inputs, name, {"synthetic": name})
               for name in ("daily.parquet", "fund_flow.parquet", "manifest.json")}
    spec = {"inherited": inherited}
    plan = {"paths": {"worktree": str(producer), "inputs": str(inputs)}, "spec": spec,
            "evidence": {"code": {"commit": evidence.COMMIT}, "parent": parent,
                         "sources": sources}}
    original_sha = evidence.sha256_json
    monkeypatch.setattr(evidence, "sha256_json",
                        lambda obj: evidence.PLAN if obj == plan else original_sha(obj))
    prereg = {"synthetic_preregistration": True}
    claim = {"plan_sha256": evidence.PLAN, "operation": str(root), "prior_debt": 3733,
             "committed_attempt_budget": 4, "preregistration_sha256": original_sha(prereg)}
    claim_sha = put(shared, f"{evidence.CLAIM}.json", claim)
    terminal = {"plan_sha256": evidence.PLAN, "outcome": "COMPLETE_DIAGNOSTIC_AUDITED",
                "native_reserved": 4, "committed_attempt_budget": 4,
                "raw_global_trial_lower_bound": 3737, "validated_alpha": False,
                "automatic_retry": False,
                "stages": {stage: {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
                           for stage in ("backend", "audit")}}
    terminal_sha = put(shared, f"{evidence.CLAIM}.terminal.json", terminal)
    files = {"RESULT.json": current["files"]["RESULT.json"]}
    for name, obj in {"LAUNCH.json": {"plan": plan, "claim_sha256": claim_sha},
                      "frozen_spec.json": spec, "PREREGISTRATION.json": prereg,
                      **{f"supervisor-{s}/SUPERVISOR.json": v
                         for s, v in terminal["stages"].items()}}.items():
        files[name] = put(root, name, obj)
    monkeypatch.setattr(evidence, "FILES", files)
    monkeypatch.setattr(evidence, "CLAIM_SHA", claim_sha)
    monkeypatch.setattr(evidence, "TERMINAL_SHA", terminal_sha)
    monkeypatch.setattr(evidence, "layout", lambda _: {"claim": shared / "unused.json"})
    calls = []

    def verify(p, tree):
        assert p == plan and Path(tree) == producer
        calls.append("plan")
        return evidence.PLAN

    monkeypatch.setattr(evidence, "verify_plan", verify)
    monkeypatch.setattr(evidence, "verify_audit", lambda *a: calls.append("audit"))
    return root, shared, terminal, files, calls


def test_completed_twelve_account_manifest_no_numerical_run(completed, tmp_path):
    _, _, _, _, calls = completed
    result = evidence.completed_inputs(tmp_path / "new-forensic-tree")
    assert calls == ["plan", "audit"]
    assert result["account_count"] == 12
    assert result["new_accounts"] == result["new_fits"] == result["new_predictions"] == 0
    assert result["raw_global_trial_lower_bound"] == 3737
    assert not result["validated_alpha"]
    assert evidence.verify_unchanged(result)["input_bytes_unchanged"]


@pytest.mark.parametrize("field,value", [
    ("outcome", "FAILED"), ("native_reserved", 3),
    ("raw_global_trial_lower_bound", 3733), ("validated_alpha", True),
    ("automatic_retry", True), ("plan_sha256", "a" * 64),
])
def test_terminal_contract_rejects_before_verifier(completed, monkeypatch, tmp_path, field, value):
    _, shared, terminal, _, calls = completed
    terminal[field] = value
    monkeypatch.setattr(evidence, "TERMINAL_SHA",
                        put(shared, f"{evidence.CLAIM}.terminal.json", terminal))
    with pytest.raises(ValueError, match="identity/debt/terminal"):
        evidence.completed_inputs(tmp_path)
    assert calls == []


def test_receipt_disagreement_rejects(completed, tmp_path):
    root, _, _, files, _ = completed
    files["supervisor-audit/SUPERVISOR.json"] = put(
        root, "supervisor-audit/SUPERVISOR.json",
        {"outcome": "COMPLETED", "exit_code": 0, "samples": 2})
    with pytest.raises(ValueError, match="supervised"):
        evidence.completed_inputs(tmp_path)


@pytest.mark.parametrize("verifier", ["verify_plan", "verify_audit"])
def test_verifier_failure_propagates(completed, monkeypatch, tmp_path, verifier):
    def failed(*a):
        raise ValueError("upstream rejected evidence")
    monkeypatch.setattr(evidence, verifier, failed)
    with pytest.raises(ValueError, match="upstream rejected"):
        evidence.completed_inputs(tmp_path)


def test_two_costs_cannot_disagree_on_shared_target(tmp_path):
    group(tmp_path, "construction")
    result = json.loads((tmp_path / "RESULT.json").read_text())
    result["records"]["global_risk-82"]["target_sha256"] = "a" * 64
    digest = put(tmp_path, "RESULT.json", result)
    with pytest.raises(ValueError, match="inconsistent targets"):
        evidence.fixed_accounts("construction", tmp_path, {"RESULT.json": digest})


def test_nonselected_archive_files_need_not_exist(tmp_path):
    bound = group(tmp_path, "grouped")
    selected = evidence.fixed_accounts("grouped", tmp_path, bound["files"])
    for name in set(bound["files"]) - set(selected["files"]):
        (tmp_path / name).unlink()  # Synthetic fixture files, never research artifacts.
    result = evidence.fixed_accounts("grouped", tmp_path, selected["files"])
    assert len(result["archive_account_keys"]) == 22
    assert len(result["accounts"]) == 4
    assert len(result["files"]) == 11
