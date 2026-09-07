"""Read-only source-to-account audit of a completed no-refit continuation.

This verifies numerical reproducibility, not launch authority or usable Alpha.
Inherited native fits remain in the old read-only database. All22 completed new
account Trials must exist before any historical numerical values are loaded.
"""

from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_continuation import (
    BUDGET,
    PRIOR_DEBT,
    VERSION,
    account_plans,
    validate_spec,
    verified_inherited,
)
from .flow_response_epoch_audit import audit_original_anchors, audit_saved_accounts
from .flow_response_history import VerifiedHistoryCache
from .flow_response_launch import ReadOnlyRegistry, read
from .flow_response_model_audit import (
    POLICIES,
    audit_frozen_models,
    audit_generated_targets,
    model_target_evidence,
)
from .flow_response_protocol import screen_records
from .flow_response_source_audit import audit_source_history
from .search_power_dsl import sha256_json


def check_completed_native(registry, root, spec, result):
    """Metadata gate; never accepts partial results or inherited fit impersonation."""
    validate_spec(spec)
    tids = result["trial_ids"]
    keys = {p["key"] for p in account_plans()}
    generated = set(POLICIES) | {"hash", "lowvol"}
    if (
        Path(registry.db_path).resolve() != root / "registry.sqlite3"
        or result["version"] != VERSION
        or result["status"] != "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        or sha256_json(spec) != result["spec_sha256"]
        or sha256_json(spec["inherited"]) != result["inherited_sha256"]
        or registry.global_trial_count() != BUDGET
        or result["reserved_trials"] != BUDGET
        or result["raw_global_trial_lower_bound"] != PRIOR_DEBT + BUDGET
        or result["new_fits"] != 0
        or result["inherited_supervised_models"] != 14
        or result["inherited_native_bindings"] != 28
        or set(tids) != keys
        or len(set(tids.values())) != BUDGET
        or set(result["records"]) != keys
        or set(result["diagnostics"]) != generated
        or set(result["targets_sha256"]) != generated | {"original_lowvol", "original_stable"}
        or result["independent_source_model_target_audit"] != "NOT_RUN"
        or result["validated_alpha"] is not False
        or result["statistics"] != spec["research_contract"]["statistics"]
        or (root / "ABORTED.json").exists()
    ):
        raise ValueError("complete frozen continuation native contract required")
    expected_snapshot = build_composite_snapshot_manifest(
        {
            "inherited_artifacts": sha256_json(spec["inherited"]),
            "anchor_card": spec["anchor_card_sha256"],
            "consumed_attempts": spec["consumed_evidence_sha256"],
        }
    ).snapshot_sha256
    experiments = set()
    with registry.connect() as db:
        if db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 0:
            raise ValueError("continuation has unexpected new fits")
        for plan in account_plans():
            tid = tids[plan["key"]]
            row = db.execute(
                "SELECT t.hyperparams,t.result_json,e.search_space,e.code_version,"
                "e.experiment_id,e.dataset_snapshot_id FROM trials t "
                "JOIN experiments e USING(experiment_id) WHERE t.trial_id=?",
                (tid,),
            ).fetchone()
            if (
                row is None
                or row[1] is None
                or json.loads(row[0]) != plan
                or sha256_json(json.loads(row[1])) != sha256_json(result["records"][plan["key"]])
                or sha256_json(json.loads(row[2])) != sha256_json(spec)
                or row[3] != spec["runtime_code_sha256"]
                or registry.snapshot_sha256(row[5]) != expected_snapshot
            ):
                raise ValueError("completed native account/spec/code/snapshot mismatch")
            experiments.add(row[4])
            fits, sources = registry.fit_lineage(tid), registry.feature_sources(tid)
            record = result["records"][plan["key"]]
            if (
                fits["fits"]
                or fits["stages"]
                or sources["providers"]
                or record["fit_lineage_sha256"] != fits["sha256"]
                or record["feature_sources_sha256"] != sources["sha256"]
            ):
                raise ValueError("native continuation must remain explicitly no-refit")
    if len(experiments) != 1:
        raise ValueError("all22 accounts must belong to one continuation")
    expected_screen = screen_records(
        result["records"], result["diagnostics"], independent_audit_pass=False
    )
    if any(result[k] != v for k, v in expected_screen.items()):
        raise ValueError("unaudited output cannot selectively promote a screen")
    return tids


def audit_complete_continuation(*, operation, input_folder, original_tree):
    """Offline audit; no database/artifact writes and no production numerical calls."""
    root = Path(operation).resolve(strict=True)
    paths = {name: root / name for name in ("RESULT.json", "frozen_spec.json", "registry.sqlite3")}
    if any(root not in p.resolve(strict=True).parents for p in paths.values()):
        raise ValueError("continuation control artifact escaped operation")
    before = {name: file_sha(p) for name, p in paths.items()}
    result, spec = read(paths["RESULT.json"]), read(paths["frozen_spec.json"])
    registry = ReadOnlyRegistry(paths["registry.sqlite3"])
    tids = check_completed_native(registry, root, spec, result)
    old, inherited, _, _, pinned_models = verified_inherited(spec, root)
    old_tids = spec["inherited"]["trial_ids"]
    history_path = inherited / "history/history.json"
    # One immutable decode for source, independent models/targets and accounts.
    # Only VerifiedHistoryCache is accepted; arbitrary supplied matrices are not.
    cache = VerifiedHistoryCache(old, old_tids["response-82"], history_path)
    history, proof = cache.get(old, old_tids["response-82"], history_path)
    if (
        result["history_sha256"] != proof["history_artifact_sha256"]
        or result["models_sha256"] != pinned_models
    ):
        raise ValueError("continuation inherited numerical identities differ")
    source_audit = audit_source_history(
        old,
        old_tids["response-82"],
        history_path=history_path,
        input_folder=input_folder,
        cache=cache,
    )
    models, fingerprints = audit_frozen_models(old, old_tids, inherited, history, proof)
    target_hashes = audit_generated_targets(registry, tids, root, result, history, models)
    if fingerprints != pinned_models or any(
        result["targets_sha256"][policy] != digest for policy, digest in target_hashes.items()
    ):
        raise ValueError("continuation model/target result hash mismatch")
    # Saved outputs of the failed source operation stay frozen, even when its
    # other accounts were incomplete. No fabricated old RESULT is required.
    for policy in generated_policies():
        relative = f"targets/{policy}.json"
        if relative in spec["inherited"]["files"] and sha256_json(read(inherited / relative)) != (
            sha256_json(read(root / relative))
        ):
            raise ValueError("continuation changed a previously saved target")
    audit_original_anchors(original_tree, result, spec)
    accounts, reports = audit_saved_accounts(root, result, tids, history, account_plans())
    # Reconcile the complete saved audit, not just its headline Sharpe/years.
    for key, evidence in accounts.items():
        if sha256_json(evidence) != sha256_json(result["records"][key]["audit"]):
            raise ValueError("saved account audit differs from independent reproduction")
    verified_inherited(spec, root)
    if any(file_sha(p) != before[name] for name, p in paths.items()):
        raise ValueError("continuation control bytes changed during independent audit")
    return {
        "version": VERSION,
        "pipeline_audit_pass": True,
        "validated_alpha": False,
        "launch_authorization_verified": False,
        "result_sha256": before["RESULT.json"],
        "native_registry_sha256": before["registry.sqlite3"],
        "spec_file_sha256": before["frozen_spec.json"],
        "spec_sha256": sha256_json(spec),
        "inherited_sha256": sha256_json(spec["inherited"]),
        "inherited_native_registry_sha256": spec["inherited"]["files"]["registry.sqlite3"],
        "new_native_accounts_checked": BUDGET,
        "new_fits": 0,
        "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
        "source_audit": source_audit,
        "model_target_audit": model_target_evidence(fingerprints, target_hashes, proof),
        "accounts": accounts,
        "full_account_report_sha256": reports,
        "statistics": spec["research_contract"]["statistics"],
        "audited_screen": screen_records(
            result["records"], result["diagnostics"], independent_audit_pass=True
        ),
        "interpretation": "source/model/target/account reproducibility only; reused development,not Court/broker/first-seen certification",
    }


def generated_policies():
    return POLICIES + ("hash", "lowvol")
