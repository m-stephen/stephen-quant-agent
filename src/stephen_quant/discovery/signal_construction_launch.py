"""Once-only V12.2 bridge launch, four accounts and no model/parameter search.

Prepare is metadata/hash-only. Actual numerical children require a fixed
Issue204 preregistration, shared exclusive claim and all four native reservations.
Old consumed plans, code, verdicts and fits are never rewritten or replayed.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_continuation_evidence import continuation_paths
from .flow_response_continuation_launch import _producer_completion
from .flow_response_launch import (
    LIMITS,
    REPO,
    ReadOnlyRegistry,
    _bound,
    _env,
    _resource_preflight,
    code_evidence,
    now,
    read,
    source_evidence,
    write,
)
from .response_supervisor import supervise
from .search_power_dsl import sha256_json
from .signal_construction import BUDGET, PRIOR_DEBT, VERSION, contract
from .signal_construction_audit import audit_complete_accounts
from .signal_construction_evidence import PARENT_PLAN, completed_bridge_parent
from .signal_construction_runtime import (
    check_native,
    execute_accounts,
    reserve_accounts,
    validate_spec,
)

ISSUE_URL = f"https://api.github.com/repos/{REPO}/issues/204"
DRIVER = "scripts/run_signal_construction.py"
CLAIM_KEY = sha256_json({"version": VERSION, "parent": PARENT_PLAN, "contract": contract()})


def prepare_plan(worktree):
    paths = continuation_paths(worktree, CLAIM_KEY)
    code = code_evidence(paths["worktree"])
    code["files"][DRIVER] = _bound(paths["worktree"], DRIVER)
    code["sha256"] = sha256_json(code["files"])
    parent = completed_bridge_parent(worktree)
    sources, calendar = source_evidence(paths["inputs"])
    if (
        sources != parent["source_evidence"]
        or calendar != parent["calendar"]
        or parent["prior_debt"] != PRIOR_DEBT
    ):
        raise ValueError("exactly completed parent sources/calendar/debt required")
    spec = {
        "version": VERSION,
        "prior_debt": PRIOR_DEBT,
        "budget": BUDGET,
        "new_fits": 0,
        "validated_alpha": False,
        "research_contract": contract(),
        "runtime_code_sha256": code["sha256"],
        "completed_parent_evidence_sha256": sha256_json(parent),
        "inherited": parent["inherited"],
        "calendar": {"count": len(calendar), "sha256": sha256_json(calendar)},
    }
    validate_spec(spec)
    return {
        "version": VERSION,
        "claim_key": CLAIM_KEY,
        "paths": {k: str(paths[k]) for k in ("worktree", "inputs", "claim")},
        "spec": spec,
        "evidence": {"code": code, "parent": parent, "sources": sources},
        "limits": asdict(LIMITS),
        "prior_debt": PRIOR_DEBT,
        "budget": BUDGET,
        "preregistration_issue": ISSUE_URL,
        "automatic_retry": False,
        "validated_alpha": False,
    }


def verify_plan(plan, worktree):
    if sha256_json(plan) != sha256_json(prepare_plan(worktree)):
        raise ValueError("construction plan differs from code/evidence/frozen scope")
    return sha256_json(plan)


def fetch_preregistration(comment_id, digest, worktree):
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("actual positive Issue204 comment identity required")
    try:
        raw = subprocess.check_output(
            ["gh", "api", "--hostname", "github.com", f"repos/{REPO}/issues/comments/{comment_id}"],
            cwd=worktree,
            env=_env(),
            stderr=subprocess.PIPE,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("GitHub preregistration unavailable; no launch") from exc
    comment = json.loads(raw)
    created = datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(comment["updated_at"].replace("Z", "+00:00"))
    if (
        comment["id"] != comment_id
        or comment["issue_url"] != ISSUE_URL
        or f"V12.2-PREREGISTRATION-SHA256: {digest}" not in comment["body"].splitlines()
        or created.utcoffset() is None
        or updated.utcoffset() is None
        or not created <= updated <= datetime.now(timezone.utc)
    ):
        raise ValueError("construction preregistration identity/plan/time mismatch")
    return {"comment": comment, "fetched_at": now(), "plan_sha256": digest}


def operation_path(plan, digest):
    return Path(plan["paths"]["worktree"]) / f"artifacts/signal-construction/epochs/{digest}"


def reservation(tids):
    return {
        "trial_ids": tids,
        "reserved": BUDGET,
        "prior_debt": PRIOR_DEBT,
        "debt": PRIOR_DEBT + BUDGET,
        "native_trial_ids_sha256": sha256_json(tids),
    }


def verify_audit(root, digest, spec):
    complete = _producer_completion(root)
    result, audit, assessment = (
        read(root / f"{name}.json") for name in ("RESULT", "AUDIT", "ASSESSMENT")
    )
    plan = read(root / "LAUNCH.json")["plan"]
    if sha256_json(plan) != digest or sha256_json(plan["spec"]) != sha256_json(spec):
        raise ValueError("audit launch plan/spec binding mismatch")
    check_native(
        ReadOnlyRegistry(root / "registry.sqlite3"), root, spec, result["trial_ids"], result
    )
    source = audit["source_audit"]
    if (
        source["source_history_audit_pass"] is not True
        or source["sessions_checked"] != 726
        or source["source_numeric_years"] != [2022, 2023, 2024]
        or source["history_artifact_sha256"] != spec["inherited"]["files"]["history/history.json"]
        or source["source_sha256"]
        != {name: plan["evidence"]["sources"][name + ".parquet"] for name in ("daily", "fund_flow")}
        or audit["full_account_report_sha256"]
        != {key: row["full_account_sha256"] for key, row in result["records"].items()}
    ):
        raise ValueError("complete independent source/full-account evidence required")
    for key, row in result["records"].items():
        policy = key.rsplit("-", 1)[0]
        for name, expected in (
            (f"accounts/{key}.jsonl", row["account_sha256"]),
            (f"account_reports/{key}.json", row["full_account_sha256"]),
            (f"targets/{policy}.json", row["target_sha256"]),
        ):
            _bound(root, name, expected)
    if (
        audit["pipeline_audit_pass"] is not True
        or audit["validated_alpha"] is not False
        or audit["launch_authorization_verified"] is not False
        or audit["new_native_accounts_checked"] != BUDGET
        or audit["new_fits"] != 0
        or audit["raw_global_trial_lower_bound"] != PRIOR_DEBT + BUDGET
        or audit["result_sha256"] != complete["result_sha256"]
        or audit["native_registry_sha256"] != complete["registry_sha256"]
        or audit["spec_sha256"] != sha256_json(spec)
        or audit["spec_file_sha256"] != file_sha(root / "frozen_spec.json")
        or audit["history_sha256"] != spec["inherited"]["files"]["history/history.json"]
        or audit["calendar"] != spec["calendar"]
        or audit["models_sha256"] != result["models_sha256"]
        or audit["completed_parent_evidence_sha256"] != spec["completed_parent_evidence_sha256"]
        or audit["independent_target_sha256"] != result["targets_sha256"]
        or set(audit["accounts"]) != set(result["trial_ids"])
        or any(not a["pass"] for a in audit["accounts"].values())
        or audit["statistics"] != contract()["statistics"]
        or assessment
        != {
            "status": "COMPLETE_DIAGNOSTIC_AUDITED",
            "validated_alpha": False,
            "plan_sha256": digest,
            "result_sha256": complete["result_sha256"],
            "audit_sha256": file_sha(root / "AUDIT.json"),
            "statistics": contract()["statistics"],
        }
    ):
        raise ValueError("complete diagnostic audit required; never promote to Alpha")


def launch(plan_path, *, comment_id, worktree):
    plan = read(plan_path)
    digest = verify_plan(plan, worktree)
    comment = fetch_preregistration(comment_id, digest, worktree)
    memory = _resource_preflight()
    output, claim = operation_path(plan, digest), Path(plan["paths"]["claim"])
    if output.exists():
        raise FileExistsError("diagnostic operation exists; no replay")
    write(
        claim,
        {
            "version": VERSION,
            "plan_sha256": digest,
            "operation": str(output),
            "preregistration_sha256": sha256_json(comment),
            "claimed_at": now(),
            "prelaunch_memory": memory,
            "prior_debt": PRIOR_DEBT,
            "committed_attempt_budget": BUDGET,
            "automatic_retry": False,
        },
    )
    outcome, stage, receipts, error, native_error, count = (
        "FAILED",
        "reservation",
        {},
        None,
        None,
        0,
    )
    try:
        output.mkdir(parents=True, exist_ok=False)
        write(output / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim)})
        write(output / "PREREGISTRATION.json", comment)
        registry, tids = reserve_accounts(output, plan["spec"])
        check_native(registry, output, plan["spec"], tids)
        write(output / "RESERVATIONS.json", reservation(tids))
        bound = {"plan": digest, "claim": file_sha(claim), "preregistration": sha256_json(comment)}
        for stage in ("backend", "audit"):
            receipt = supervise(
                [sys.executable, str(Path(worktree) / DRIVER), stage, "--operation", str(output)],
                cwd=worktree,
                output=output / f"supervisor-{stage}",
                limits=LIMITS,
                evidence_hashes=bound,
            )
            receipts[stage] = receipt
            if (
                receipt["outcome"] != "COMPLETED"
                or receipt["exit_code"] != 0
                or receipt["samples"] < 1
            ):
                raise RuntimeError("owned construction stage failed; keep debt and do not retry")
            if read(output / f"supervisor-{stage}/SUPERVISOR.json") != receipt:
                raise ValueError("actual saved resource receipt required")
            if stage == "backend":
                result = read(output / "RESULT.json")
                check_native(
                    ReadOnlyRegistry(output / "registry.sqlite3"),
                    output,
                    plan["spec"],
                    tids,
                    result,
                )
                write(
                    output / "BACKEND_COMPLETED.json",
                    {
                        "result_sha256": file_sha(output / "RESULT.json"),
                        "registry_sha256": file_sha(output / "registry.sqlite3"),
                        "supervisor_sha256": file_sha(
                            output / "supervisor-backend/SUPERVISOR.json"
                        ),
                    },
                )
            else:
                verify_audit(output, digest, plan["spec"])
        verify_plan(plan, worktree)
        outcome = "COMPLETE_DIAGNOSTIC_AUDITED"
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        if (output / "registry.sqlite3").is_file():
            try:
                count = ReadOnlyRegistry(output / "registry.sqlite3").global_trial_count()
            except (OSError, ValueError, sqlite3.Error) as exc:
                count, native_error = None, type(exc).__name__
        terminal = {
            "outcome": outcome,
            "last_stage": stage,
            "plan_sha256": digest,
            "native_reserved": count,
            "committed_attempt_budget": BUDGET,
            "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
            "finished_at": now(),
            "automatic_retry": False,
            "validated_alpha": False,
            "stages": receipts,
            "exception_type": error,
            "native_count_error": native_error,
        }
        write(claim.with_name(claim.stem + ".terminal.json"), terminal)
    return terminal


def run_stage(stage, *, operation, worktree):
    if stage not in ("backend", "audit"):
        raise ValueError("only backend and audit stages exist")
    root = Path(operation).resolve(strict=True)
    envelope = read(root / "LAUNCH.json")
    plan = envelope["plan"]
    digest = verify_plan(plan, worktree)
    claim_path = Path(plan["paths"]["claim"])
    claim, comment = read(claim_path), read(root / "PREREGISTRATION.json")
    if (
        root != operation_path(plan, digest).resolve()
        or file_sha(claim_path) != envelope["claim_sha256"]
        or claim["version"] != VERSION
        or claim["plan_sha256"] != digest
        or Path(claim["operation"]).resolve() != root
        or claim["prior_debt"] != PRIOR_DEBT
        or claim["committed_attempt_budget"] != BUDGET
        or claim["preregistration_sha256"] != sha256_json(comment)
        or comment["plan_sha256"] != digest
        or claim_path.with_name(claim_path.stem + ".terminal.json").exists()
    ):
        raise ValueError("complete active shared construction claim required")
    reserved = read(root / "RESERVATIONS.json")
    tids = reserved["trial_ids"]
    if reserved != reservation(tids):
        raise ValueError("all four native reservation identities required")
    write(root / f"CHILD_{stage}.json", {"started_at": now(), "plan_sha256": digest})
    if stage == "backend":
        registry = ExperimentRegistry(root / "registry.sqlite3")
        execute_accounts(registry, tids, plan["spec"], output=root)
    else:
        completed = _producer_completion(root)
        audit = audit_complete_accounts(operation=root, input_folder=plan["paths"]["inputs"])
        verify_plan(plan, worktree)
        if audit["result_sha256"] != completed["result_sha256"] or (
            audit["native_registry_sha256"] != completed["registry_sha256"]
        ):
            raise ValueError("audit must preserve producer bytes")
        write(root / "AUDIT.json", audit)
        write(
            root / "ASSESSMENT.json",
            {
                "status": "COMPLETE_DIAGNOSTIC_AUDITED",
                "validated_alpha": False,
                "plan_sha256": digest,
                "result_sha256": completed["result_sha256"],
                "audit_sha256": file_sha(root / "AUDIT.json"),
                "statistics": contract()["statistics"],
            },
        )
        verify_audit(root, digest, plan["spec"])
