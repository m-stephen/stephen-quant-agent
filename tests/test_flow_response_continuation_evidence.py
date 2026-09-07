"""Consumed evidence validation on synthetic bytes and a real temporary ledger."""

import json

import pytest

from stephen_quant.discovery import flow_response_continuation_evidence as m
from stephen_quant.discovery.flow_response_diagnostic import reserve_diagnostic
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.qmt.reliable_panel import file_sha


def replace_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def diagnostic(tmp_path, monkeypatch):
    root, trace = tmp_path / "diagnostic", tmp_path / "trace"
    root.mkdir()
    plan = {
        "code": {"sha256": "a" * 64},
        "contract": {"key": "synthetic-risk"},
        "failed003": {
            "inventory_sha256": "b" * 64,
            "files": {
                k: {"sha256": "c" * 64}
                for k in ("history/history.json", "targets/risk.json", "registry.sqlite3")
            },
        },
    }
    plan_sha = m.sha256_json(plan)
    monkeypatch.setattr(m, "B17_PLAN", plan_sha)
    registry, tid = reserve_diagnostic(root, plan)
    # Intentionally not JSON: evidence preparation must hash, never decode accounts.
    (root / "UNVERIFIED_ACCOUNT.json").write_bytes(b"SYNTHETIC ACCOUNT RAW BYTES")
    result = {
        "plan_sha256": plan_sha,
        "trial_id": tid,
        "engineering_pass": False,
        "validated_alpha": False,
        "new_fits": 0,
        "raw_global_trial_lower_bound": 3707,
        "corrected_audit": {"pass": True},
        "original_audit": {"reproduced": True},
        "account_sha256": file_sha(root / "UNVERIFIED_ACCOUNT.json"),
    }
    registry.record_trial_result(tid, json.dumps(result))
    write(root / "RESULT.json", result)
    write(
        root / "supervisor/SUPERVISOR.json", {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
    )
    claim = tmp_path / "claims/synthetic.json"
    write(
        claim,
        {
            "plan_sha256": plan_sha,
            "operation": str(root),
            "prior_debt": 3706,
            "committed_attempt_budget": 1,
        },
    )
    terminal = claim.with_name("synthetic.terminal.json")
    write(
        terminal,
        {
            "outcome": "UNRESOLVED",
            "raw_global_trial_lower_bound": 3707,
            "native_reserved": 1,
            "committed_attempt_budget": 1,
        },
    )
    write(root / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim)})
    write(trace / "trace_b17_saved_fills.py", {"synthetic_script": True})
    write(trace / "b17-readonly-trace-plan.json", {"synthetic_plan": True})
    write(
        trace / "b17-readonly-trace-result.json",
        {
            "status": "READONLY_CUMULATIVE_TRACE_EXPLAINED",
            "original_b17_verdict": "UNRESOLVED (same-day criterion retained)",
            "protected_unchanged": True,
            "validated_alpha": False,
            "new_fits": 0,
            "new_account_executions": 0,
            "new_empirical_trials": 0,
        },
    )
    paths = {"diagnostic": root, "diagnostic_claim": claim, "trace": trace}
    pin(monkeypatch, paths)
    return paths, registry, tid


def pin(monkeypatch, paths):
    """Test-only stand-in for fixed real archived SHA constants, not a runtime hook."""
    root, trace, claim = paths["diagnostic"], paths["trace"], paths["diagnostic_claim"]
    monkeypatch.setattr(m, "B17_FILES", {name: file_sha(root / name) for name in m.B17_FILES})
    monkeypatch.setattr(m, "TRACE_FILES", {name: file_sha(trace / name) for name in m.TRACE_FILES})
    monkeypatch.setattr(m, "B17_CLAIM_SHA", file_sha(claim))
    monkeypatch.setattr(m, "B17_TERMINAL_SHA", file_sha(claim.with_name("synthetic.terminal.json")))


def test_consumed_diagnostic_keeps_original_verdict_and_reads_no_account_values(diagnostic):
    paths, _, _ = diagnostic
    before = dict(m.B17_FILES)
    evidence = m.diagnostic_evidence(paths)
    assert evidence["original_verdict"] == "UNRESOLVED"
    assert evidence["native_trials"] == 1 and evidence["new_fits"] == 0
    assert evidence["raw_global_trial_lower_bound"] == 3707
    assert evidence["files"] == before


@pytest.mark.parametrize(
    "name",
    ["RESULT.json", "registry.sqlite3", "UNVERIFIED_ACCOUNT.json", "supervisor/SUPERVISOR.json"],
)
def test_any_changed_archived_bytes_rejected_before_native_read(diagnostic, monkeypatch, name):
    paths, _, _ = diagnostic
    with (paths["diagnostic"] / name).open("ab") as stream:
        stream.write(b"\n")

    def forbidden(*a):
        raise AssertionError("changed bytes reached native ledger")

    monkeypatch.setattr(m, "ReadOnlyRegistry", forbidden)
    with pytest.raises(ValueError, match="bytes changed"):
        m.diagnostic_evidence(paths)


@pytest.mark.parametrize(
    "change",
    [
        "promoted",
        "debt",
        "fit",
        "unreproduced",
        "native_result",
        "native_plan",
        "trace_trial",
        "trace_promoted",
    ],
)
def test_reissued_evidence_cannot_change_historical_meaning(diagnostic, monkeypatch, change):
    paths, registry, tid = diagnostic
    root = paths["diagnostic"]
    result = m.read(root / "RESULT.json")
    if change == "promoted":
        result["engineering_pass"] = True
    elif change == "debt":
        result["raw_global_trial_lower_bound"] = 3706
    elif change == "fit":
        result["new_fits"] = 1
    elif change == "unreproduced":
        result["original_audit"]["reproduced"] = False
    elif change == "native_result":
        with registry.connect() as db:
            db.execute("UPDATE trials SET result_json='{}' WHERE trial_id=?", (tid,))
    elif change == "native_plan":
        with registry.connect() as db:
            db.execute("UPDATE experiments SET search_space='{}'")
    else:
        path = paths["trace"] / "b17-readonly-trace-result.json"
        trace = m.read(path)
        if change == "trace_trial":
            trace["new_empirical_trials"] = 1
        else:
            trace["original_b17_verdict"] = "PASS"
        replace_json(path, trace)
    replace_json(root / "RESULT.json", result)
    pin(monkeypatch, paths)
    with pytest.raises(ValueError):
        m.diagnostic_evidence(paths)


def test_no_historical_failure_debt_can_be_discarded(monkeypatch):
    monkeypatch.setattr(m, "parent_evidence", lambda _: {})
    monkeypatch.setattr(m, "failed_epoch_evidence", lambda *a: {"inherited_debt": 3683})
    monkeypatch.setattr(m, "failed_account_evidence", lambda _: {"native_count": 23})
    monkeypatch.setattr(m, "diagnostic_evidence", lambda _: {"native_trials": 1})
    paths = {"parent": "unused", "failed_epoch": "unused", "failed_claim": "unused"}
    assert m.consumed_evidence(paths)["prior_debt"] == 3707
    monkeypatch.setattr(m, "failed_account_evidence", lambda _: {"native_count": 22})
    with pytest.raises(ValueError, match="consumed attempts"):
        m.consumed_evidence(paths)


def test_independent_worktrees_share_exactly_one_continuation_claim(tmp_path, monkeypatch):
    from stephen_quant.discovery.flow_response_continuation_launch import CLAIM_KEY

    old = tmp_path / "shared/flow-response/epochs/old"
    diagnostic_claim = tmp_path / "shared/claims/diagnostic.json"
    monkeypatch.setattr(
        m, "_paths", lambda w: {"worktree": w, "old_operation": old, "claim": diagnostic_claim}
    )
    first = m.continuation_paths(tmp_path / "tree-a", CLAIM_KEY)
    second = m.continuation_paths(tmp_path / "tree-b", CLAIM_KEY)
    assert first["claim"] == second["claim"] == diagnostic_claim.with_name(CLAIM_KEY + ".json")
    assert first["diagnostic_claim"] == diagnostic_claim.with_name(m.DIAGNOSTIC_CLAIM + ".json")
    assert first["diagnostic"] == old.parent.parent / ("account-diagnostics/" + m.B17_PLAN)
