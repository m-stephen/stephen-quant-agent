"""Fixed, read-only consumed-attempt evidence for the no-refit continuation.

Preparing evidence hashes is not numerical backtesting or permission to replay
any failed attempt. The original diagnostic remains UNRESOLVED permanently.
"""

from __future__ import annotations

import json
from pathlib import Path

from .flow_response_diagnostic import CLAIM_KEY as DIAGNOSTIC_CLAIM
from .flow_response_diagnostic import FAILED_PLAN, _paths, failed_account_evidence
from .flow_response_failure import failed_epoch_evidence
from .flow_response_launch import ReadOnlyRegistry, _bound, parent_evidence, read
from .search_power_dsl import sha256_json

B17_PLAN = "80e6132fa1c45e7ed0e9aae06defb0cb1298073667e95b3a75b7fcc6388071ac"
# Actual archived claim bytes, not the claim key or a newly generated receipt.
B17_CLAIM_SHA = "0124b69574fcddb06fa314d7dd2d4207e2f99e2841bc124d7005a05da611eec1"
B17_TERMINAL_SHA = "8e9b37d4cd2b3e7631c3fd1ecf792d45ddbf1862302e44cfdd63ef6a0cf08dd6"
B17_FILES = {
    "RESULT.json": "52a3e2ddbe5b90753d0f7a078158a7aae7d93fa776e94d5cf3a3f337a82cc0e8",
    "registry.sqlite3": "a8b26f47e8848f3fc086919361e5da6bc5ccb572a730287c0c8da2ea1c1b7d38",
    "UNVERIFIED_ACCOUNT.json": "7ee205b643e8ea58e2d16594fda2931e14ee514d978aa99d7271f831d9e91d78",
    "supervisor/SUPERVISOR.json": "989fad2d911f2dd8687c859346072710872b59250387ecb9748493433d182d72",
}
TRACE_FILES = {
    "trace_b17_saved_fills.py": "94e9dbc17bbd955d84dd108680a152753d931703fc915661d074b5f120bfcccd",
    "b17-readonly-trace-plan.json": "e187a4d946e315120087dc7c383df92e448a212d837be7810c273b877bf6284a",
    "b17-readonly-trace-result.json": "ff4dba9ed1aa367325075315604083beee773a9da3aa2cf8993329023bfabf0b",
}


def continuation_paths(worktree, claim_key):
    paths = _paths(worktree)
    artifacts = paths["old_operation"].parent.parent
    paths["diagnostic"] = artifacts / f"account-diagnostics/{B17_PLAN}"
    paths["diagnostic_claim"] = paths["claim"].with_name(DIAGNOSTIC_CLAIM + ".json")
    paths["trace"] = artifacts / "checkpoints"
    paths["claim"] = paths["claim"].with_name(claim_key + ".json")
    return paths


def diagnostic_evidence(paths):
    root, claim_path = Path(paths["diagnostic"]), Path(paths["diagnostic_claim"])
    files = {name: _bound(root, name, digest) for name, digest in B17_FILES.items()}
    terminal_path = claim_path.with_name(claim_path.stem + ".terminal.json")
    claim_sha = _bound(claim_path.parent, claim_path.name, B17_CLAIM_SHA)
    terminal_sha = _bound(claim_path.parent, terminal_path.name, B17_TERMINAL_SHA)
    launch, result = read(root / "LAUNCH.json"), read(root / "RESULT.json")
    claim, terminal = read(claim_path), read(terminal_path)
    supervisor = read(root / "supervisor/SUPERVISOR.json")
    if (
        sha256_json(launch["plan"]) != B17_PLAN
        or launch["claim_sha256"] != claim_sha
        or claim["plan_sha256"] != B17_PLAN
        or Path(claim["operation"]).resolve() != root.resolve()
        or claim["prior_debt"] != 3706
        or claim["committed_attempt_budget"] != 1
        or terminal["outcome"] != "UNRESOLVED"
        or terminal["raw_global_trial_lower_bound"] != 3707
        or terminal["native_reserved"] != 1
        or terminal["committed_attempt_budget"] != 1
        or result["plan_sha256"] != B17_PLAN
        or result["engineering_pass"] is not False
        or result["validated_alpha"] is not False
        or result["new_fits"] != 0
        or result["raw_global_trial_lower_bound"] != 3707
        or result["corrected_audit"]["pass"] is not True
        or result["original_audit"]["reproduced"] is not True
        or result["account_sha256"] != files["UNVERIFIED_ACCOUNT.json"]
        or supervisor["outcome"] != "COMPLETED"
        or supervisor["exit_code"] != 0
        or supervisor["samples"] < 1
    ):
        raise ValueError("original consumed UNRESOLVED diagnostic evidence required")
    registry = ReadOnlyRegistry(root / "registry.sqlite3")
    with registry.connect() as db:
        rows = db.execute(
            "SELECT t.trial_id,t.result_json,e.search_space FROM trials t "
            "JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if (
            len(rows) != 1
            or rows[0][0] != result["trial_id"]
            or rows[0][1] is None
            or sha256_json(json.loads(rows[0][1])) != sha256_json(result)
            or sha256_json(json.loads(rows[0][2])) != B17_PLAN
            or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 0
            or registry.fit_lineage(rows[0][0])["stages"]
            or registry.feature_sources(rows[0][0])["providers"]
        ):
            raise ValueError("exactly one completed native no-refit diagnostic required")
    traces = {name: _bound(paths["trace"], name, digest) for name, digest in TRACE_FILES.items()}
    trace = read(Path(paths["trace"]) / "b17-readonly-trace-result.json")
    if (
        trace["status"] != "READONLY_CUMULATIVE_TRACE_EXPLAINED"
        or trace["original_b17_verdict"] != "UNRESOLVED (same-day criterion retained)"
        or trace["protected_unchanged"] is not True
        or trace["validated_alpha"] is not False
        or any(
            trace[k] != 0 for k in ("new_fits", "new_account_executions", "new_empirical_trials")
        )
    ):
        raise ValueError("append-only zero-Trial cumulative explanation required")
    return {
        "files": files,
        "claim_sha256": claim_sha,
        "terminal_sha256": terminal_sha,
        "trace_files": traces,
        "native_trials": 1,
        "new_fits": 0,
        "original_verdict": "UNRESOLVED",
        "trace_trial_delta": 0,
        "raw_global_trial_lower_bound": 3707,
    }


def consumed_evidence(paths):
    parent = parent_evidence(paths["parent"])
    first = failed_epoch_evidence(paths["failed_epoch"], paths["failed_claim"])
    second = failed_account_evidence(paths)
    diagnostic = diagnostic_evidence(paths)
    if first["inherited_debt"] + second["native_count"] + diagnostic["native_trials"] != 3707:
        raise ValueError("all consumed attempts must remain in inherited debt")
    return {
        "parent": parent,
        "failed002": first,
        "failed003": second,
        "B17": diagnostic,
        "failed003_plan_sha256": FAILED_PLAN,
        "prior_debt": 3707,
    }
