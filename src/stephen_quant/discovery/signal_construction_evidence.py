"""Read-only completed V11.22 evidence for the frozen V12.2 bridge.

Preserves the original historical code, claim and numerical verdict. Hashing
completed evidence is not permission to run another account or decode history.
The launcher must separately freeze current code and reserve all four Trials.
"""

from pathlib import Path

from .flow_response_launch import ReadOnlyRegistry, _bound, _git, layout, read
from .portfolio_construction_evidence import completed_parent_evidence
from .portfolio_construction_launch import verify_audit
from .portfolio_construction_runtime import check_native
from .search_power_dsl import sha256_json

PARENT_PLAN = "632253b6620c9fba7ac8c244857121c8aa3029f62f8c050142f502caa8ff315a"
PARENT_COMMIT = "dbd1a3f0623a5199f51b5ea63cc3e40bf17b3334"
PARENT_CLAIM = "f341c8c6fe5cc0ae6f92f0c5f996af3dad3ee344214e35110b5a6581132e7955"
CLAIM_SHA = "ad3288ffaea930328fd96d100d13111b2bf08b49984febad241e3f4555de4bf0"
TERMINAL_SHA = "3aea79c64e78499ad27a04bfb7f00a3f903d3397c4c1665209acdeffdc9df84a"
FILES = {
    "LAUNCH.json": "97cca6ffc0b062762dc0b274a29c04f96bc2fd038f317e3540665079f424b8cb",
    "RESULT.json": "c5070db5ee9c9d6df8f2f051ce6c2c8f2e1e93bb1177c60698d925af33e6c7ba",
    "AUDIT.json": "f1099e9451f2ec61a26499684f368e0bdcf7432d085b734017a3494273b5cf3b",
    "ASSESSMENT.json": "1b55749e8d78d6ee884e4d083289ff7003f54eb5cd17e29c3b995149c26e6593",
    "registry.sqlite3": "f60821fa6155da727dbe48174924870875695e61ffbfd93c2d98c9e5bc6a2f23",
    "frozen_spec.json": "850409221fbeea2e0671ad98747b750132640954dc98c7505e22671f97db959f",
    "supervisor-backend/SUPERVISOR.json": "afe11a1ac42cb7f22bd63289c636c60c23ac9aea822deb5a2cba3947665f2368",
    "supervisor-audit/SUPERVISOR.json": "f59da4a814bed0f466ff89f44336e4458914ee0acbc6fbdcb2862d05fb299a65",
}


def bind_grouped_comparators(previous):
    """Hash only the four predeclared saved response/risk comparators; no rerun."""
    root = Path(previous["root"])
    digest = _bound(root, "RESULT.json", previous["files"]["RESULT.json"])
    result = read(root / "RESULT.json")
    files = {"RESULT.json": digest}
    for policy in ("response", "risk"):
        for cost in (82, 164):
            key = f"{policy}-{cost}"
            row = result["records"][key]
            for name, bound in (
                (f"accounts/{key}.jsonl", row["account_sha256"]),
                (f"account_reports/{key}.json", row["full_account_sha256"]),
                (f"targets/{policy}.json", row["target_sha256"]),
            ):
                files[name] = _bound(root, name, bound)
    return {"root": str(root), "files": files, "purpose": "read-only explanatory; not primary"}


def completed_bridge_parent(worktree):
    """Bind actual completed lower bound3733, without rewriting old plans."""
    paths = layout(worktree)
    historical = paths["parent"].parents[2].parent / "v11.21-flow-response"
    root = historical / f"artifacts/portfolio-construction/epochs/{PARENT_PLAN}"
    claim_path = paths["claim"].with_name(PARENT_CLAIM + ".json")
    files = {name: _bound(root, name, digest) for name, digest in FILES.items()}
    claim_sha = _bound(claim_path.parent, claim_path.name, CLAIM_SHA)
    terminal_sha = _bound(claim_path.parent, claim_path.stem + ".terminal.json", TERMINAL_SHA)
    envelope, claim = read(root / "LAUNCH.json"), read(claim_path)
    terminal = read(claim_path.with_name(claim_path.stem + ".terminal.json"))
    plan, spec, result = (
        envelope["plan"],
        read(root / "frozen_spec.json"),
        read(root / "RESULT.json"),
    )
    previous = completed_parent_evidence(historical)
    if (
        sha256_json(plan) != PARENT_PLAN
        or envelope["claim_sha256"] != claim_sha
        or claim["plan_sha256"] != PARENT_PLAN
        or Path(claim["operation"]).resolve() != root.resolve()
        or claim["prior_debt"] != 3729
        or claim["committed_attempt_budget"] != 4
        or sha256_json(spec) != sha256_json(plan["spec"])
        or sha256_json(previous) != spec["completed_parent_evidence_sha256"]
        or sha256_json(previous) != sha256_json(plan["evidence"]["parent"])
        or terminal["outcome"] != "COMPLETE_DIAGNOSTIC_AUDITED"
        or terminal["plan_sha256"] != PARENT_PLAN
        or terminal["native_reserved"] != 4
        or terminal["committed_attempt_budget"] != 4
        or terminal["raw_global_trial_lower_bound"] != 3733
        or terminal["validated_alpha"] is not False
        or terminal["automatic_retry"] is not False
        or claim["preregistration_sha256"] != sha256_json(read(root / "PREREGISTRATION.json"))
    ):
        raise ValueError("completed four-account parent claim/debt/evidence mismatch")
    code = plan["evidence"]["code"]
    if (
        code["commit"] != PARENT_COMMIT
        or code["sha256"] != sha256_json(code["files"])
        or _git(historical, "cat-file", "-t", PARENT_COMMIT) != "commit"
        or set(_git(historical, "diff", "--name-only", PARENT_COMMIT, "HEAD", "--").splitlines())
        & set(code["files"])
    ):
        raise ValueError("unchanged historical runtime required; no silent rebind")
    for name, digest in code["files"].items():
        _bound(historical, name, digest)
    check_native(
        ReadOnlyRegistry(root / "registry.sqlite3"), root, spec, result["trial_ids"], result
    )
    verify_audit(root, PARENT_PLAN, spec)
    for stage in ("backend", "audit"):
        receipt = read(root / f"supervisor-{stage}/SUPERVISOR.json")
        if (
            receipt != terminal["stages"][stage]
            or receipt["outcome"] != "COMPLETED"
            or receipt["exit_code"] != 0
            or receipt["samples"] < 1
        ):
            raise ValueError("actual complete parent supervised receipts required")
    for key, row in result["records"].items():
        policy = key.rsplit("-", 1)[0]
        for name, digest in (
            (f"accounts/{key}.jsonl", row["account_sha256"]),
            (f"account_reports/{key}.json", row["full_account_sha256"]),
            (f"targets/{policy}.json", row["target_sha256"]),
        ):
            files[name] = _bound(root, name, digest)
    return {
        "root": str(root),
        "plan_sha256": PARENT_PLAN,
        "files": files,
        "claim_sha256": claim_sha,
        "terminal_sha256": terminal_sha,
        "code": {"commit": PARENT_COMMIT, "raw_code_sha256": code["sha256"]},
        "previous": previous,
        "prior_debt": 3733,
        "native_completed_accounts": 4,
        "inherited": previous["inherited"],
        "calendar": previous["calendar"],
        "source_evidence": previous["source_evidence"],
        "saved_grouped_comparators": bind_grouped_comparators(previous),
        "validated_alpha": False,
    }
