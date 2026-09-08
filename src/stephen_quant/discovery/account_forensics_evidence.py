"""Read-only V12.3 input bindings; never launch an account or predict a score."""

from pathlib import Path

from .flow_response_launch import _bound, layout, read
from .search_power_dsl import sha256_json
from .signal_construction_launch import verify_audit, verify_plan

PLAN = "ace020b075d872f3a6a78d91934b788adc6192109574b32e031bdcdd4e710b98"
COMMIT = "75602e12e2cc1b81b814146af1e8b9e67072afdd"
CLAIM = "78add5bdb1b5993e8647517ae88d93308acfe9b23f20227c183047da194a5757"
CLAIM_SHA = "e314fa1be3bb442ec50dfeae11f01ff3b0aef57530bde30142461b1d2289f188"
TERMINAL_SHA = "e055cef0997bd100dfd6e441c8995c971cf49dc25660e7ee90d732319ba78365"
FILES = {
    "LAUNCH.json": "e2955f11871d8a2ac04e520dcd7bf535a1e550aefd2888cac5f00c27f5aa5968",
    "RESULT.json": "67e4558edada509d15b2e957fbd8229e01a77699c9fb35cd6390d448f193cc08",
    "AUDIT.json": "e4d141c35e1f444ff9e45380204a8ffe583dca2eea8229ed700f50ababf194c5",
    "ASSESSMENT.json": "066218f6b9fb3bab1869d40cde44803587c3614ac2aaee3db3c853a9dd7978cb",
    "registry.sqlite3": "175cdc1a44a72250e7ce9fb1396d79889ee46ca982c4caf8b6386cf5996e520b",
    "frozen_spec.json": "a53684dda951278feea3801f2500de72363b4060ba0da84c00cab8cd69161856",
    "BACKEND_COMPLETED.json": "e40d95927c926bcf3ff6e30d2607121afa6e64c8a0134c31963caafef6b7eeec",
    "PREREGISTRATION.json": "48e557382eb0e22ba817727705456ecc09db4449703fe327cb1a3c71aa8be50c",
    "supervisor-backend/SUPERVISOR.json": "9c3e85f8ce40f8f36a489616c4eefa348be2605c031e7056287042859af34d7d",
    "supervisor-audit/SUPERVISOR.json": "f7b9647b3cf9eb5f32d1a9842ee492e5d3c00b663ab60bd7cd798eccae816a82",
}
GROUPS = {
    "construction": ("global_response", "global_risk"),
    "grouped": ("response", "risk"),
    "global_baselines": ("global_lowvol", "global_hash"),
}


def bind_files(root, expected):
    """Explicit allowlist only. Return portable names; reject escapes before reading."""
    root = Path(root).resolve()
    if not expected:
        raise ValueError("nonempty frozen file bindings required")
    for name, digest in expected.items():
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("relative nonescaping evidence path required")
        if not (root / candidate).resolve().is_relative_to(root):
            raise ValueError("resolved evidence path escapes frozen root")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("canonical SHA-256 required")
        _bound(root, name, digest)
    return {"root": str(root), "files": dict(sorted(expected.items()))}


def fixed_accounts(group, root, expected):
    """Bind every prespecified account, compact ledger and target before decoding."""
    if group not in GROUPS:
        raise ValueError("unregistered account group")
    root = Path(root)
    bind_files(root, {"RESULT.json": expected["RESULT.json"]})
    result = read(root / "RESULT.json")
    keys = {f"{policy}-{cost}" for policy in GROUPS[group] for cost in (82, 164)}
    if set(result["records"]) != keys:
        raise ValueError("all four fixed accounts required; no comparator selection")
    files, accounts = {"RESULT.json": expected["RESULT.json"]}, {}
    for key in sorted(keys):
        row, policy = result["records"][key], key.rsplit("-", 1)[0]
        names = {
            f"accounts/{key}.jsonl": row["account_sha256"],
            f"account_reports/{key}.json": row["full_account_sha256"],
            f"targets/{policy}.json": row["target_sha256"],
        }
        for name, digest in names.items():
            if name in expected and expected[name] != digest:
                raise ValueError("result and frozen account bindings disagree")
            if name in files and files[name] != digest:
                raise ValueError("same policy cannot reference inconsistent targets")
        files.update(names)
        accounts[f"{group}/{key}"] = {
            "key": key,
            "report": f"account_reports/{key}.json",
            "ledger": f"accounts/{key}.jsonl",
            "target": f"targets/{policy}.json",
        }
    return {**bind_files(root, files), "accounts": accounts}


def completed_inputs(worktree):
    """Verify the untouched producer, not V12.3's different code; no numerical rerun."""
    shared = layout(worktree)["claim"].parent
    producer = shared.parent / "worktrees/v12.2-signal-construction"
    root = producer / f"artifacts/signal-construction/epochs/{PLAN}"
    operation = bind_files(root, FILES)
    claims = bind_files(shared, {f"{CLAIM}.json": CLAIM_SHA,
                                f"{CLAIM}.terminal.json": TERMINAL_SHA})
    envelope = read(root / "LAUNCH.json")
    plan = envelope["plan"]
    claim = read(shared / f"{CLAIM}.json")
    terminal = read(shared / f"{CLAIM}.terminal.json")
    if (
        sha256_json(plan) != PLAN
        or plan["evidence"]["code"]["commit"] != COMMIT
        or Path(plan["paths"]["worktree"]).resolve() != producer.resolve()
        or envelope["claim_sha256"] != CLAIM_SHA
        or claim["plan_sha256"] != PLAN
        or Path(claim["operation"]).resolve() != root.resolve()
        or claim["prior_debt"] != 3733
        or claim["committed_attempt_budget"] != 4
        or claim["preregistration_sha256"] != sha256_json(read(root / "PREREGISTRATION.json"))
        or terminal["plan_sha256"] != PLAN
        or terminal["outcome"] != "COMPLETE_DIAGNOSTIC_AUDITED"
        or terminal["native_reserved"] != 4
        or terminal["committed_attempt_budget"] != 4
        or terminal["raw_global_trial_lower_bound"] != 3737
        or terminal["validated_alpha"] is not False
        or terminal["automatic_retry"] is not False
    ):
        raise ValueError("completed V12.2 identity/debt/terminal mismatch")
    if verify_plan(plan, producer) != PLAN:
        raise ValueError("untouched producer plan required")
    verify_audit(root, PLAN, plan["spec"])
    for stage in ("backend", "audit"):
        receipt = read(root / f"supervisor-{stage}/SUPERVISOR.json")
        if (
            receipt != terminal["stages"][stage]
            or receipt["outcome"] != "COMPLETED"
            or receipt["exit_code"] != 0
            or receipt["samples"] < 1
        ):
            raise ValueError("completed supervised evidence required")
    parent = plan["evidence"]["parent"]
    grouped = parent["saved_grouped_comparators"]
    groups = {
        "construction": fixed_accounts("construction", root, FILES),
        "grouped": fixed_accounts("grouped", grouped["root"], grouped["files"]),
        "global_baselines": fixed_accounts("global_baselines", parent["root"], parent["files"]),
    }
    inherited = plan["spec"]["inherited"]
    history = bind_files(inherited["root"], {
        "history/history.json": inherited["files"]["history/history.json"]})
    sources = bind_files(plan["paths"]["inputs"], {
        name: plan["evidence"]["sources"][name]
        for name in ("daily.parquet", "fund_flow.parquet", "manifest.json")
    })
    return {
        "version": "V12.3", "parent_plan_sha256": PLAN, "producer_commit": COMMIT,
        "bindings": {"operation": operation, "claims": claims, "history": history,
                     "sources": sources, **groups},
        "account_count": 12, "source_sessions": 726, "execution_sessions": 484,
        "new_accounts": 0, "new_fits": 0, "new_predictions": 0,
        "raw_global_trial_lower_bound": 3737, "validated_alpha": False,
    }


def verify_unchanged(evidence):
    """Re-hash all explicit inputs after reporting; never bless altered originals."""
    for binding in evidence["bindings"].values():
        bind_files(binding["root"], binding["files"])
    return {"input_bytes_unchanged": True, "evidence_sha256": sha256_json(evidence)}
