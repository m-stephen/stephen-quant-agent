"""One shared-claim, fully counted, bounded frozen-model continuation.

Only prepare is metadata/hash-only. Launch must validate the complete fixed plan
and actual Issue184 preregistration before claiming and reserving all22 accounts.
No caller-selectable policy, cost, year, threshold, retry or source override.
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_continuation import (
    BUDGET,
    PRIOR_DEBT,
    account_plans,
    check_reservations,
    execute_continuation,
    reserve_continuation,
    validate_spec,
)
from .flow_response_continuation import (
    VERSION as BACKEND_VERSION,
)
from .flow_response_continuation_audit import audit_complete_continuation, check_completed_native
from .flow_response_continuation_evidence import B17_PLAN, consumed_evidence, continuation_paths
from .flow_response_diagnostic import FAILED_PLAN
from .flow_response_launch import (
    CARD_SHA,
    ISSUE_URL,
    LIMITS,
    ReadOnlyRegistry,
    _bound,
    _resource_preflight,
    code_evidence,
    fetch_preregistration,
    now,
    original_evidence,
    read,
    source_evidence,
    write,
)
from .flow_response_protocol import contract
from .response_supervisor import supervise
from .search_power_dsl import sha256_json

VERSION = "11.21-frozen-continuation-launch-1"
DRIVER = "scripts/run_flow_response_continuation.py"
CLAIM_KEY = sha256_json({"version": VERSION, "failed003": FAILED_PLAN, "consumed_B17": B17_PLAN})


def prepare_plan(worktree):
    paths = continuation_paths(worktree, CLAIM_KEY)
    code = code_evidence(paths["worktree"])
    code["files"][DRIVER] = _bound(paths["worktree"], DRIVER)
    code["sha256"] = sha256_json(code["files"])
    consumed = consumed_evidence(paths)
    sources, calendar = source_evidence(paths["inputs"])
    anchors = original_evidence(paths["original"])
    # This receipt is already byte-bound by failed_account_evidence's inventory.
    old_tids = read(paths["old_operation"] / "RESERVATIONS.json")["trial_ids"]
    spec = {
        "version": BACKEND_VERSION,
        "prior_debt": PRIOR_DEBT,
        "budget": BUDGET,
        "new_fits": 0,
        "validated_alpha": False,
        "accounts": account_plans(),
        "research_contract": contract(),
        "runtime_code_sha256": code["sha256"],
        "anchor_card_sha256": CARD_SHA,
        "consumed_evidence_sha256": sha256_json(consumed),
        "inherited": {
            "root": str(paths["old_operation"]),
            "trial_ids": old_tids,
            "files": {k: v["sha256"] for k, v in consumed["failed003"]["files"].items()},
        },
    }
    validate_spec(spec)
    if consumed["prior_debt"] != PRIOR_DEBT:
        raise ValueError("all consumed history must be inherited")
    return {
        "version": VERSION,
        "claim_key": CLAIM_KEY,
        "paths": {k: str(p) for k, p in paths.items()},
        "spec": spec,
        "evidence": {
            "code": code,
            "consumed": consumed,
            "sources": sources,
            "original": anchors,
            "calendar": calendar,
        },
        "limits": asdict(LIMITS),
        "prior_debt": PRIOR_DEBT,
        "budget": BUDGET,
        "preregistration_issue": ISSUE_URL,
        "automatic_retry": False,
        "validated_alpha": False,
    }


def verify_plan(plan, worktree):
    if sha256_json(plan) != sha256_json(prepare_plan(worktree)):
        raise ValueError("continuation plan differs from actual code/evidence/frozen scope")
    return sha256_json(plan)


def operation_path(plan, digest):
    return Path(plan["paths"]["worktree"]) / f"artifacts/flow-response/continuations/{digest}"


def _reservation(tids):
    return {
        "trial_ids": tids,
        "reserved": BUDGET,
        "prior_debt": PRIOR_DEBT,
        "debt": PRIOR_DEBT + BUDGET,
        "native_trial_ids_sha256": sha256_json(tids),
    }


def launch(plan_path, *, comment_id, worktree):
    plan = read(plan_path)
    digest = verify_plan(plan, worktree)
    comment = fetch_preregistration(comment_id, digest, worktree)
    memory = _resource_preflight()
    output, claim_path = operation_path(plan, digest), Path(plan["paths"]["claim"])
    if output.exists():
        raise FileExistsError("continuation operation exists; no replay")
    write(
        claim_path,
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
        write(output / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim_path)})
        write(output / "PREREGISTRATION.json", comment)
        registry, tids = reserve_continuation(output, plan["spec"])
        check_reservations(registry, tids, plan["spec"], output)
        count = registry.global_trial_count()
        write(output / "RESERVATIONS.json", _reservation(tids))
        bound = {
            "plan": digest,
            "claim": file_sha(claim_path),
            "preregistration": sha256_json(comment),
        }
        for stage in ("backend", "audit"):
            receipts[stage] = supervise(
                [sys.executable, str(Path(worktree) / DRIVER), stage, "--operation", str(output)],
                cwd=worktree,
                output=output / f"supervisor-{stage}",
                limits=LIMITS,
                evidence_hashes=bound,
            )
            receipt = receipts[stage]
            if (
                receipt["outcome"] != "COMPLETED"
                or receipt["exit_code"] != 0
                or receipt["samples"] < 1
            ):
                raise RuntimeError("owned stage did not complete; keep all debt, no retry")
            if read(output / f"supervisor-{stage}/SUPERVISOR.json") != receipt:
                raise ValueError("actual saved supervisor receipt required")
            if stage == "backend":
                check_completed_native(
                    ReadOnlyRegistry(output / "registry.sqlite3"),
                    output,
                    plan["spec"],
                    read(output / "RESULT.json"),
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
                _verify_assessment(output, digest)
        verify_plan(plan, worktree)
        outcome = "COMPLETE_EXPLORATORY_AUDITED"
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
        write(claim_path.with_name(claim_path.stem + ".terminal.json"), terminal)
    return terminal


def _active_stage(stage, operation, worktree):
    if stage not in ("backend", "audit"):
        raise ValueError("only backend/audit stages exist")
    root = Path(operation).resolve(strict=True)
    envelope = read(root / "LAUNCH.json")
    plan, digest = envelope["plan"], verify_plan(envelope["plan"], worktree)
    if root != operation_path(plan, digest).resolve():
        raise ValueError("child is not in the bound continuation operation")
    path = Path(plan["paths"]["claim"])
    claim, comment = read(path), read(root / "PREREGISTRATION.json")
    if (
        file_sha(path) != envelope["claim_sha256"]
        or claim["version"] != VERSION
        or claim["plan_sha256"] != digest
        or Path(claim["operation"]).resolve() != root
        or claim["preregistration_sha256"] != sha256_json(comment)
        or claim["prior_debt"] != PRIOR_DEBT
        or claim["committed_attempt_budget"] != BUDGET
        or path.with_name(path.stem + ".terminal.json").exists()
        or comment["plan_sha256"] != digest
    ):
        raise ValueError("complete active shared claim/preregistration required")
    reservation = read(root / "RESERVATIONS.json")
    tids = reservation["trial_ids"]
    if reservation != _reservation(tids):
        raise ValueError("complete native reservation receipt required")
    return root, plan, digest, tids


def _producer_completion(root):
    completed = read(root / "BACKEND_COMPLETED.json")
    supervisor_path = root / "supervisor-backend/SUPERVISOR.json"
    supervisor = read(supervisor_path)
    if (
        supervisor["outcome"] != "COMPLETED"
        or supervisor["exit_code"] != 0
        or supervisor["samples"] < 1
        or file_sha(supervisor_path) != completed["supervisor_sha256"]
        or file_sha(root / "RESULT.json") != completed["result_sha256"]
        or file_sha(root / "registry.sqlite3") != completed["registry_sha256"]
    ):
        raise ValueError("verified producer exit and immutable outputs required before audit")
    return completed


def _verify_assessment(root, digest):
    completed = _producer_completion(root)
    audit, assessment = read(root / "AUDIT.json"), read(root / "ASSESSMENT.json")
    if (
        audit["pipeline_audit_pass"] is not True
        or audit["validated_alpha"] is not False
        or audit["launch_authorization_verified"] is not False
        or audit["new_native_accounts_checked"] != BUDGET
        or audit["new_fits"] != 0
        or audit["raw_global_trial_lower_bound"] != PRIOR_DEBT + BUDGET
        or audit["statistics"] != contract()["statistics"]
        or audit["result_sha256"] != completed["result_sha256"]
        or audit["native_registry_sha256"] != completed["registry_sha256"]
        or assessment["validated_alpha"] is not False
        or assessment["plan_sha256"] != digest
        or assessment["result_sha256"] != completed["result_sha256"]
        or assessment["audit_sha256"] != file_sha(root / "AUDIT.json")
        or assessment["audited_screen"] != audit["audited_screen"]
        or assessment["statistics"] != contract()["statistics"]
    ):
        raise ValueError("complete exploratory audit/assessment required; cannot certify Alpha")


def run_stage(stage, *, operation, worktree):
    root, plan, digest, tids = _active_stage(stage, operation, worktree)
    # The supervisor parent and this once-only child receipt prevent normal
    # duplicate execution. This is single-user integrity, not an OS security sandbox.
    write(root / f"CHILD_{stage}.json", {"started_at": now(), "plan_sha256": digest})
    if stage == "backend":
        registry = ExperimentRegistry(root / "registry.sqlite3")
        check_reservations(registry, tids, plan["spec"], root)
        execute_continuation(
            registry, tids, plan["spec"], output=root, original_tree=plan["paths"]["original"]
        )
    else:
        completed = _producer_completion(root)
        audit = audit_complete_continuation(
            operation=root,
            input_folder=plan["paths"]["inputs"],
            original_tree=plan["paths"]["original"],
        )
        verify_plan(plan, worktree)
        if (
            audit["pipeline_audit_pass"] is not True
            or audit["validated_alpha"] is not False
            or file_sha(root / "RESULT.json") != completed["result_sha256"]
            or file_sha(root / "registry.sqlite3") != completed["registry_sha256"]
        ):
            raise ValueError("audit must preserve all native outputs and pass")
        write(root / "AUDIT.json", audit)
        write(
            root / "ASSESSMENT.json",
            {
                "audited_screen": audit["audited_screen"],
                "validated_alpha": False,
                "result_sha256": completed["result_sha256"],
                "audit_sha256": file_sha(root / "AUDIT.json"),
                "plan_sha256": digest,
                "statistics": plan["spec"]["research_contract"]["statistics"],
                "launch_evidence": "separately verified active shared claim and fixed GitHub preregistration",
                "interpretation": "reused development screen only; not fresh OOS or Alpha Court",
            },
        )
