"""Synthetic one-shot orchestration; never consumes a real-market claim."""

import copy
import json
from pathlib import Path

import pytest
from test_signal_construction_runtime import spec as synthetic_spec

from stephen_quant.discovery import signal_construction_launch as m


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "tree"
    root.mkdir()
    plan = {
        "version": m.VERSION,
        "claim_key": m.CLAIM_KEY,
        "paths": {
            "worktree": str(root),
            "claim": str(tmp_path / "common/once.json"),
            "inputs": str(tmp_path / "inputs"),
        },
        "spec": synthetic_spec(tmp_path / "old"),
        "prior_debt": 3733,
        "budget": 4,
        "validated_alpha": False,
    }
    frozen = copy.deepcopy(plan)
    monkeypatch.setattr(m, "prepare_plan", lambda _: copy.deepcopy(frozen))
    monkeypatch.setattr(m, "fetch_preregistration", lambda i, d, _: {"id": i, "plan_sha256": d})
    monkeypatch.setattr(m, "_resource_preflight", lambda: {"physical_available_bytes": 8 * 1024**3})
    path = root / "plan.json"
    m.write(path, plan)
    return root, path, plan


@pytest.mark.parametrize(
    "field,value", (("prior_debt", 0), ("budget", 2), ("validated_alpha", True))
)
def test_modified_plan_never_consumes_claim(prepared, field, value):
    root, path, plan = prepared
    plan[field] = value
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="differs"):
        m.launch(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("stage", ("fetch_preregistration", "_resource_preflight"))
def test_missing_preregistration_or_resources_does_not_consume(prepared, monkeypatch, stage):
    root, path, plan = prepared

    def reject(*a):
        raise ValueError("synthetic refusal")

    monkeypatch.setattr(m, stage, reject)
    with pytest.raises(ValueError, match="refusal"):
        m.launch(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("outcome", ("FAILED", "GUARD_STOPPED", "PRELAUNCH_REFUSED"))
def test_all_four_reserved_before_child_and_failed_debt_cannot_replay(
    prepared, monkeypatch, outcome
):
    root, path, plan = prepared
    calls = []

    def child(command, **kw):
        calls.append(command)
        output = Path(command[-1])
        assert Path(plan["paths"]["claim"]).is_file()
        reg = m.ReadOnlyRegistry(output / "registry.sqlite3")
        receipt = m.read(output / "RESERVATIONS.json")
        m.check_native(reg, output, plan["spec"], receipt["trial_ids"])
        assert reg.global_trial_count() == receipt["reserved"] == 4
        assert kw["limits"] is m.LIMITS
        return {"outcome": outcome, "exit_code": 1, "samples": 1}

    monkeypatch.setattr(m, "supervise", child)
    with pytest.raises(RuntimeError, match="do not retry"):
        m.launch(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    terminal = m.read(claim.with_name("once.terminal.json"))
    assert terminal["native_reserved"] == terminal["committed_attempt_budget"] == 4
    assert terminal["raw_global_trial_lower_bound"] == 3737
    assert terminal["outcome"] == "FAILED" and not terminal["validated_alpha"]
    with pytest.raises(FileExistsError):
        m.launch(path, comment_id=1, worktree=root)
    assert len(calls) == 1


def test_actual_api_comment_requires_own_version_issue_hash_and_time(tmp_path, monkeypatch):
    obj = {
        "id": 1,
        "issue_url": m.ISSUE_URL,
        "body": "V12.2-PREREGISTRATION-SHA256: " + "d" * 64,
        "created_at": "2020-01-01T00:00:00Z",
        "updated_at": "2020-01-01T00:00:00Z",
    }
    calls = []

    def api(argv, **kw):
        calls.append(argv)
        assert "--hostname" in argv and argv[-1].endswith("/issues/comments/1")
        return json.dumps(obj).encode()

    monkeypatch.setattr(m.subprocess, "check_output", api)
    proof = m.fetch_preregistration(1, "d" * 64, tmp_path)
    assert proof["plan_sha256"] == "d" * 64 and calls
    for key, value in (
        ("body", "V11.21-PREREGISTRATION-SHA256: " + "d" * 64),
        ("issue_url", m.ISSUE_URL.replace("204", "205")),
        ("updated_at", "2099-01-01T00:00:00Z"),
        ("created_at", "2020-01-01T00:00:00"),
    ):
        previous = obj[key]
        obj[key] = value
        with pytest.raises(ValueError):
            m.fetch_preregistration(1, "d" * 64, tmp_path)
        obj[key] = previous


def test_prepare_binds_parent_source_code_and_driver_without_claim(tmp_path, monkeypatch):
    paths = {k: tmp_path / k for k in ("worktree", "claim", "inputs")}
    sources, calendar = {"daily": "a" * 64}, [f"synthetic-{i}" for i in range(726)]
    parent = {
        "source_evidence": sources,
        "calendar": calendar,
        "prior_debt": 3733,
        "inherited": synthetic_spec(tmp_path / "old")["inherited"],
    }
    monkeypatch.setattr(m, "continuation_paths", lambda *a: paths)
    monkeypatch.setattr(m, "code_evidence", lambda _: {"files": {"old.py": "e" * 64}})
    monkeypatch.setattr(m, "_bound", lambda *a: "f" * 64)
    monkeypatch.setattr(m, "completed_bridge_parent", lambda _: parent)
    monkeypatch.setattr(m, "source_evidence", lambda _: (sources, calendar))
    plan = m.prepare_plan(tmp_path)
    assert plan["spec"]["completed_parent_evidence_sha256"] == m.sha256_json(parent)
    assert plan["spec"]["runtime_code_sha256"] == m.sha256_json(plan["evidence"]["code"]["files"])
    assert plan["evidence"]["code"]["files"][m.DRIVER] == "f" * 64
    assert plan["budget"] == 4 and not paths["claim"].exists()
    assert plan["spec"]["calendar"] == {"count": 726, "sha256": m.sha256_json(calendar)}
    monkeypatch.setattr(m, "source_evidence", lambda _: (sources, calendar + ["2025-01-02"]))
    with pytest.raises(ValueError, match="exactly"):
        m.prepare_plan(tmp_path)
