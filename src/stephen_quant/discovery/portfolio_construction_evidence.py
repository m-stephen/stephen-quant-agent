"""Read-only completed-B22 evidence, not permission to execute another account.

An old completed plan belongs to its historical Git commit. Rebuilding that plan
against today's HEAD would reject harmless new modules, or tempt callers to
silently rebind history. Instead preserve its canonical identity, original file
bytes, native results, shared terminal, and independent assessment explicitly.
"""

from __future__ import annotations

from pathlib import Path

from .flow_response_continuation_audit import check_completed_native
from .flow_response_continuation_evidence import consumed_evidence, continuation_paths
from .flow_response_continuation_launch import _verify_assessment
from .flow_response_launch import ReadOnlyRegistry, _bound, _git, read
from .portfolio_construction import (
    PARENT_ASSESSMENT,
    PARENT_AUDIT,
    PARENT_PLAN,
    PARENT_RESULT,
    PRIOR_DEBT,
    contract,
)
from .search_power_dsl import sha256_json

COMMIT = "89ecd36e1f3fff2c9493a3a599eb139397c064aa"
CLAIM_KEY = "b97e34f50360863291d7efb3ac6425bf0d7a0909435dea0112151630353b01e0"
CLAIM_SHA = "ec59835fdc978ff7efbc52f9d835abe53be4b7695dfe28ccf3b0bc6dfd4b0d28"
TERMINAL_SHA = "b0f272e73dd684f5e54e918ef6e332105a2b9dbb7b86759ed4d8603b56caa057"
FILES = {
    "RESULT.json": PARENT_RESULT,
    "AUDIT.json": PARENT_AUDIT,
    "ASSESSMENT.json": PARENT_ASSESSMENT,
    "registry.sqlite3": "8be3d9bbcc5e4fb9536afe4034c7dab3a0fdd6ecadee27c9f867ab2524c13baa",
    "frozen_spec.json": "77c9f74e62c034d09eeb17ea2f846e7a75b455078dd98da6cccb0e8f3c3a0a24",
    "supervisor-backend/SUPERVISOR.json": "ca088721907a8dc17e6f1e63a1702c10a24d8b791d075b73e12d77b4a0c6f9b8",
    "supervisor-audit/SUPERVISOR.json": "2fd341483190a948becf3cb98faad40e03079c82abdac6376b989dc36cdf0700",
}


def verify_historical_code(worktree, code):
    """Keep old raw-byte provenance; new files do not rewrite the old commit.

    Git's text normalization can differ from working-file CRLF bytes. We do not
    hash decoded `git show` text as if it were the executed file. Both the raw
    runtime hash and unchanged tracked history of each original file are needed.
    """
    if code["commit"] != COMMIT or code["sha256"] != sha256_json(code["files"]):
        raise ValueError("original completed runtime code identity required")
    if _git(worktree, "cat-file", "-t", COMMIT) != "commit":
        raise ValueError("original runtime Git commit unavailable")
    changed = set(_git(worktree, "diff", "--name-only", COMMIT, "HEAD", "--").splitlines())
    if changed & set(code["files"]):
        raise ValueError("historical code changed; requires a separately reviewed migration")
    for relative, digest in code["files"].items():
        _bound(worktree, relative, digest)
    return {"commit": COMMIT, "raw_code_sha256": code["sha256"], "files": len(code["files"])}


def completed_parent_evidence(worktree):
    """Hash metadata/saved completed results only; never decode raw history."""
    paths = continuation_paths(worktree, CLAIM_KEY)
    root = paths["worktree"] / f"artifacts/flow-response/continuations/{PARENT_PLAN}"
    files = {relative: _bound(root, relative, digest) for relative, digest in FILES.items()}
    claim_path = paths["claim"]
    claim_sha = _bound(claim_path.parent, claim_path.name, CLAIM_SHA)
    terminal_sha = _bound(claim_path.parent, claim_path.stem + ".terminal.json", TERMINAL_SHA)
    envelope, claim = read(root / "LAUNCH.json"), read(claim_path)
    plan = envelope["plan"]
    terminal = read(claim_path.with_name(claim_path.stem + ".terminal.json"))
    result, spec = read(root / "RESULT.json"), read(root / "frozen_spec.json")
    consumed = consumed_evidence(paths)
    if (
        sha256_json(plan) != PARENT_PLAN
        or envelope["claim_sha256"] != claim_sha
        or claim["plan_sha256"] != PARENT_PLAN
        or Path(claim["operation"]).resolve() != root.resolve()
        or claim["prior_debt"] != 3707
        or claim["committed_attempt_budget"] != 22
        or sha256_json(spec) != sha256_json(plan["spec"])
        or sha256_json(consumed) != spec["consumed_evidence_sha256"]
        or consumed["prior_debt"] + 22 != PRIOR_DEBT
        or terminal["outcome"] != "COMPLETE_EXPLORATORY_AUDITED"
        or terminal["plan_sha256"] != PARENT_PLAN
        or terminal["native_reserved"] != 22
        or terminal["committed_attempt_budget"] != 22
        or terminal["raw_global_trial_lower_bound"] != PRIOR_DEBT
        or terminal["validated_alpha"] is not False
        or terminal["automatic_retry"] is not False
        or claim["preregistration_sha256"] != sha256_json(read(root / "PREREGISTRATION.json"))
    ):
        raise ValueError("exact completed parent claim, debt and native evidence required")
    code = verify_historical_code(paths["worktree"], plan["evidence"]["code"])
    check_completed_native(ReadOnlyRegistry(root / "registry.sqlite3"), root, spec, result)
    _verify_assessment(root, PARENT_PLAN)
    for stage in ("backend", "audit"):
        receipt = read(root / f"supervisor-{stage}/SUPERVISOR.json")
        if (
            receipt != terminal["stages"][stage]
            or receipt["outcome"] != "COMPLETED"
            or receipt["exit_code"] != 0
            or receipt["samples"] < 1
        ):
            raise ValueError("completed parent supervised stages required")
    # Reuse all four completed comparators read-only; no replay or new winners.
    for key in contract()["comparators"]:
        row = result["records"][key]
        policy = key.rsplit("-", 1)[0]
        for relative, digest in (
            (f"accounts/{key}.jsonl", row["account_sha256"]),
            (f"account_reports/{key}.json", row["full_account_sha256"]),
            (f"targets/{policy}.json", row["target_sha256"]),
        ):
            files[relative] = _bound(root, relative, digest)
    return {
        "root": str(root),
        "plan_sha256": PARENT_PLAN,
        "files": files,
        "claim_sha256": claim_sha,
        "terminal_sha256": terminal_sha,
        "code": code,
        "consumed_evidence_sha256": sha256_json(consumed),
        "native_completed_accounts": 22,
        "prior_debt": PRIOR_DEBT,
        "inherited": spec["inherited"],
        "source_evidence": plan["evidence"]["sources"],
        "calendar": plan["evidence"]["calendar"],
        "validated_alpha": False,
    }
