"""Fixed metadata plan for once-only read-only forensics; no account execution."""

import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_acceptance import digest, exact, expected_outputs, read
from .account_forensics_evidence import COMMIT, PLAN, completed_inputs
from .account_forensics_inputs import execution_calendar
from .flow_response_launch import LIMITS, REPO, _bound, _env, code_evidence, layout, now
from .search_power_dsl import sha256_json

DRIVER = "scripts/run_account_forensics.py"
ISSUE_URL = f"https://api.github.com/repos/{REPO}/issues/206"
RISK_LINE = "V12.3-RUNTIME-RISK: ACKNOWLEDGED_NOT_ROOT_CAUSE_FIXED"


def scope():
    names, _ = expected_outputs()
    return {"version": "V12.3", "parent_plan_sha256": PLAN, "original_producer_commit": COMMIT,
            "account_keys": names, "account_count": 12, "raw_global_trial_lower_bound": 3737,
            "new_accounts": 0, "new_fits": 0, "new_predictions": 0,
            "source_years": [2022, 2023, 2024], "execution_years": [2023, 2024],
            "source_truth_verified": False, "validated_alpha": False,
            "automatic_retry": False, "scope": "fixed_saved_account_forensics_not_research_search"}


CLAIM_KEY = sha256_json(scope())


def runtime_evidence():
    binaries = {}
    for label, module in (("duckdb", "_duckdb"), ("numpy", "numpy._core._multiarray_umath")):
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise ValueError("actual native runtime binary required")
        path = Path(spec.origin).resolve(strict=True)
        binaries[label] = {"path": str(path), "sha256": file_sha(path)}
    return {"python": sys.version, "platform": sys.platform,
            "executable": str(Path(sys.executable).resolve(strict=True)),
            "executable_sha256": file_sha(sys.executable), "native_binaries": binaries}


def paths(worktree):
    original = layout(worktree)
    root = original["worktree"]
    return {"worktree": root, "claim": original["claim"].parent / f"{CLAIM_KEY}.json",
            "operations": root / "artifacts/account-forensics/epochs"}


def prepare_plan(worktree):
    """Bind completed evidence and its already saved calendar, not financial queries.

    completed_inputs also validates the untouched original producer's metadata
    contract. No new forensics or history decoding occurs in this preparation.
    """
    fixed_paths = paths(worktree)
    root = fixed_paths["worktree"]
    code = code_snapshot(root)
    evidence = completed_inputs(root)
    binding = evidence["bindings"]["operation"]
    _bound(binding["root"], "LAUNCH.json", binding["files"]["LAUNCH.json"])
    original = read(Path(binding["root"]) / "LAUNCH.json")["plan"]
    exact(sha256_json(original), PLAN)
    calendar = original["evidence"]["parent"]["calendar"]
    calendar_binding = original["spec"]["calendar"]
    execution_calendar(calendar, frozen=calendar_binding)
    prefix = "src/stephen_quant/"
    package = {p[len(prefix):]: h for p, h in code["files"].items() if p.startswith(prefix)}
    if not package:
        raise ValueError("complete frozen package map required")
    return {"version": "V12.3", "scope": scope(), "claim_key": CLAIM_KEY,
            "paths": {k: str(v) for k, v in fixed_paths.items()},
            "input_evidence": evidence, "source_calendar": calendar, "calendar_binding": calendar_binding,
            "code": code, "package_code": package, "runtime": runtime_evidence(),
            "limits": asdict(LIMITS), "preregistration_issue": ISSUE_URL,
            "required_runtime_risk_line": RISK_LINE, "automatic_retry": False, "validated_alpha": False}


def code_snapshot(root):
    code = code_evidence(root)
    code["files"][DRIVER] = _bound(root, DRIVER)
    code["sha256"] = sha256_json(code["files"])
    return code


def verify_plan(plan, worktree):
    exact(plan, prepare_plan(worktree))
    return sha256_json(plan)


def operation_path(plan):
    return Path(plan["paths"]["operations"]) / sha256_json(plan)


def validate_preregistration(comment, comment_id, plan_sha):
    digest(plan_sha)
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("actual positive Issue206 comment identity required")
    exact(comment["id"], comment_id)
    exact(comment["issue_url"], ISSUE_URL)
    lines = comment["body"].splitlines()
    if f"V12.3-FORENSICS-PLAN-SHA256: {plan_sha}" not in lines or RISK_LINE not in lines:
        raise ValueError("exact plan and unresolved-runtime-risk acknowledgement required")
    created, updated = [datetime.fromisoformat(comment[k].replace("Z", "+00:00"))
                        for k in ("created_at", "updated_at")]
    if created.utcoffset() is None or updated.utcoffset() is None or not created <= updated <= datetime.now(timezone.utc):
        raise ValueError("valid aware preregistration timestamps required")


def fetch_preregistration(comment_id, plan_sha, worktree):
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("actual positive Issue206 comment identity required")
    try:
        raw = subprocess.check_output(
            ["gh", "api", "--hostname", "github.com", f"repos/{REPO}/issues/comments/{comment_id}"],
            cwd=worktree, env=_env(), stderr=subprocess.PIPE, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Issue206 preregistration unavailable; no launch") from exc
    comment = json.loads(raw)
    validate_preregistration(comment, comment_id, plan_sha)
    return {"comment": comment, "fetched_at": now(), "plan_sha256": plan_sha}
