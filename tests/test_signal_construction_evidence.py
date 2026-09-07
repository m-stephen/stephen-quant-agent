"""Small metadata-only unit fixtures; no market data or fake numerical audit claim.

Ancestor numerical/native audits are stubbed only in these wrapper unit tests;
their real execution is covered by separate complete synthetic E2E tests.
All wrapper file hashing, cross-links and debt checks run on real temporary bytes.
"""

import copy
import json

import pytest

from stephen_quant.discovery import signal_construction_evidence as m
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.qmt.reliable_panel import file_sha


def saved_records(root, policies):
    records = {}
    for policy in policies:
        target = root / f"targets/{policy}.json"
        write(target, {"fixture": policy})
        for cost in (82, 164):
            key = f"{policy}-{cost}"
            account, report = root / f"accounts/{key}.jsonl", root / f"account_reports/{key}.json"
            write(account, {"synthetic": key})
            write(report, {"synthetic": key})
            records[key] = {
                "account_sha256": file_sha(account),
                "full_account_sha256": file_sha(report),
                "target_sha256": file_sha(target),
            }
    return records


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    historical = tmp_path / "worktrees/v11.21-flow-response"
    previous_root = tmp_path / "previous"
    records = saved_records(previous_root, ("response", "risk"))
    write(previous_root / "RESULT.json", {"records": records})
    previous = {
        "root": str(previous_root),
        "files": {"RESULT.json": file_sha(previous_root / "RESULT.json")},
        "inherited": {"synthetic": True},
        "calendar": ["SYNTHETIC"] * 726,
        "source_evidence": {},
        "prior_debt": 3729,
    }
    code_file = historical / "src/frozen.py"
    code_file.parent.mkdir(parents=True)
    code_file.write_text("# synthetic historical code\n")
    code_files = {"src/frozen.py": file_sha(code_file)}
    spec = {"completed_parent_evidence_sha256": m.sha256_json(previous)}
    code = {"commit": m.PARENT_COMMIT, "files": code_files, "sha256": m.sha256_json(code_files)}
    plan = {"spec": spec, "evidence": {"parent": previous, "code": code}}
    digest = m.sha256_json(plan)
    monkeypatch.setattr(m, "PARENT_PLAN", digest)
    root = historical / f"artifacts/portfolio-construction/epochs/{digest}"
    records = saved_records(root, ("global_lowvol", "global_hash"))
    prereg = {"synthetic": True}
    claim = {
        "plan_sha256": digest,
        "operation": str(root),
        "prior_debt": 3729,
        "committed_attempt_budget": 4,
        "preregistration_sha256": m.sha256_json(prereg),
    }
    claim_path = tmp_path / f"claims/{m.PARENT_CLAIM}.json"
    write(claim_path, claim)
    receipt = {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
    terminal = {
        "outcome": "COMPLETE_DIAGNOSTIC_AUDITED",
        "plan_sha256": digest,
        "native_reserved": 4,
        "committed_attempt_budget": 4,
        "raw_global_trial_lower_bound": 3733,
        "validated_alpha": False,
        "automatic_retry": False,
        "stages": {"backend": receipt, "audit": receipt},
    }
    terminal_path = claim_path.with_name(claim_path.stem + ".terminal.json")
    write(terminal_path, terminal)
    values = {
        "LAUNCH.json": {"plan": plan, "claim_sha256": file_sha(claim_path)},
        "RESULT.json": {"records": records, "trial_ids": {}},
        "frozen_spec.json": spec,
        "PREREGISTRATION.json": prereg,
        "AUDIT.json": {},
        "ASSESSMENT.json": {},
        "registry.sqlite3": {"fixture": "native checks covered separately"},
        "supervisor-backend/SUPERVISOR.json": receipt,
        "supervisor-audit/SUPERVISOR.json": receipt,
    }
    for name, value in values.items():
        write(root / name, value)
    monkeypatch.setattr(m, "FILES", {n: file_sha(root / n) for n in values})
    monkeypatch.setattr(m, "CLAIM_SHA", file_sha(claim_path))
    monkeypatch.setattr(m, "TERMINAL_SHA", file_sha(terminal_path))
    paths = {
        "parent": tmp_path / "worktrees/v11.20-gross-net-attribution/artifacts/gross-net/epoch-001",
        "claim": tmp_path / "claims/current.json",
    }
    monkeypatch.setattr(m, "layout", lambda _: paths)
    monkeypatch.setattr(m, "completed_parent_evidence", lambda _: copy.deepcopy(previous))
    monkeypatch.setattr(m, "_git", lambda root, *a: "commit" if a[0] == "cat-file" else "")
    monkeypatch.setattr(m, "ReadOnlyRegistry", lambda _: None)
    monkeypatch.setattr(m, "check_native", lambda *a: None)
    monkeypatch.setattr(m, "verify_audit", lambda *a: None)
    return root, claim_path, terminal_path, code_file, paths, previous


def test_metadata_parent_and_all_eight_saved_comparators(metadata):
    root, _, _, _, _, _ = metadata
    evidence = m.completed_bridge_parent(root)
    assert evidence["prior_debt"] == 3733 and not evidence["validated_alpha"]
    assert evidence["native_completed_accounts"] == 4 and len(evidence["calendar"]) == 726
    grouped = evidence["saved_grouped_comparators"]
    assert len(grouped["files"]) == 11  # RESULT+4compact+4full+2targets.
    assert grouped["purpose"].startswith("read-only")


@pytest.mark.parametrize(
    "fault",
    [
        "claim_operation",
        "prior",
        "budget",
        "terminal_debt",
        "terminal_status",
        "code_bytes",
        "git_drift",
        "result_bytes",
        "account_bytes",
        "path",
    ],
)
def test_metadata_changed_bindings_refuse(metadata, monkeypatch, fault):
    root, claim, terminal, code, paths, _ = metadata
    if fault in {"claim_operation", "prior", "budget"}:
        obj = m.read(claim)
        key, value = {
            "claim_operation": ("operation", str(root.parent / "other")),
            "prior": ("prior_debt", 0),
            "budget": ("committed_attempt_budget", 3),
        }[fault]
        obj[key] = value
        claim.write_text(json.dumps(obj))
        # Rehash both layers: exercise semantic checks, not just byte mismatch.
        monkeypatch.setattr(m, "CLAIM_SHA", file_sha(claim))
        envelope = m.read(root / "LAUNCH.json")
        envelope["claim_sha256"] = file_sha(claim)
        (root / "LAUNCH.json").write_text(json.dumps(envelope))
        m.FILES["LAUNCH.json"] = file_sha(root / "LAUNCH.json")
    elif fault.startswith("terminal_"):
        obj = m.read(terminal)
        obj["raw_global_trial_lower_bound" if fault == "terminal_debt" else "outcome"] = 0
        terminal.write_text(json.dumps(obj))
        monkeypatch.setattr(m, "TERMINAL_SHA", file_sha(terminal))
    elif fault == "git_drift":
        monkeypatch.setattr(
            m, "_git", lambda root, *a: "commit" if a[0] == "cat-file" else "src/frozen.py"
        )
    elif fault == "path":
        paths["parent"] = root / "wrong/artifacts/gross-net/epoch-001"
    else:
        path = {
            "code_bytes": code,
            "result_bytes": root / "RESULT.json",
            "account_bytes": root / "accounts/global_hash-164.jsonl",
        }[fault]
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        m.completed_bridge_parent(root)


@pytest.mark.parametrize(
    "name",
    [
        "RESULT.json",
        "accounts/response-82.jsonl",
        "account_reports/risk-164.json",
        "targets/response.json",
    ],
)
def test_grouped_external_files_are_bound_not_just_summary(metadata, name):
    *_, previous = metadata
    from pathlib import Path

    path = Path(previous["root"]) / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        m.bind_grouped_comparators(previous)
