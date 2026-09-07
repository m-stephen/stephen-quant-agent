"""Full finite *reserved* epoch backend, not an empirical launch authorization.

The production entrypoint must separately verify committed code, fixed parent
evidence, preregistration and a global exclusive claim. This backend is currently
exercised only on synthetic sources. Independent source/model/target auditing is
still pending; an internally consistent account never confers Alpha eligibility.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from stephen_quant.baseline.stateful import run_stateful_execution
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.flow_response_accounts import execute_response_account, history_targets
from stephen_quant.discovery.flow_response_history import (
    VerifiedHistoryCache,
    bind_shared_history_predictor,
    build_history_from_frozen,
    fit_history_predictor,
)
from stephen_quant.discovery.flow_response_predictor import POLICIES
from stephen_quant.discovery.flow_response_protocol import (
    BUDGET,
    COSTS,
    DEBT,
    VERSION,
    check_complete_reservations,
    plans,
    screen_records,
)
from stephen_quant.discovery.flow_response_replay import (
    audit_response_account,
    load_original_targets,
)
from stephen_quant.discovery.gross_net_attribution import execution_summary
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha

from .v114_reliable_epoch import write_json
from .v117_incremental_epoch import save_account


def execute_reserved_epoch(registry, tids, spec, *, output, input_folder, original_tree):
    """Execute all23 native reservations exactly once, preserving partial failures.

    Caller creates the complete native database first. No callback can manufacture
    an independent-audit pass. This function always returns validated_alpha=false.
    """
    output, inputs, original = [Path(p).resolve() for p in (output, input_folder, original_tree)]
    receipt = check_complete_reservations(registry, tids)
    if any(output == p or output in p.parents or p in output.parents for p in (inputs, original)):
        raise ValueError("epoch output must be disjoint from both source roots")
    if Path(registry.db_path).resolve() != output / "registry.sqlite3":
        raise ValueError("operation must own its native database")
    # Match the entire spec to each actual reservation, not just a caller's dict.
    with registry.connect() as conn:
        for tid in tids.values():
            row = conn.execute(
                "SELECT e.search_space FROM experiments e JOIN trials t "
                "ON e.experiment_id=t.experiment_id WHERE t.trial_id=?",
                (tid,),
            ).fetchone()
            if row is None or sha256_json(json.loads(row[0])) != sha256_json(spec):
                raise ValueError("reserved native experiment differs from supplied spec")
    # Exclusive backend claim is not the pending cross-operation empirical claim.
    write_json(output / "BACKEND_CLAIM.json", {"spec_sha256": sha256_json(spec), **receipt})
    records, models_sha, target_sha = {}, {}, {}
    provider = tids["response-provider"]
    try:
        write_json(output / "frozen_spec.json", spec)
        write_json(output / "first_read_reservations.json", {"trials": tids, **receipt})
        calendar = spec["calendar"]
        execution_days = [d for d in calendar if d >= "2023-01-01"]
        anchors, anchor_proofs = load_original_targets(
            registry,
            tids,
            original_tree=original,
            card_sha256=spec["anchor_card_sha256"],
            calendar=execution_days,
        )
        target_dir = output / "targets"
        target_dir.mkdir(exist_ok=False)
        for policy, proof in anchor_proofs.items():
            path = target_dir / f"{policy}.json"
            with path.open("xb") as stream:
                stream.write(proof["target_bytes"])
            target_sha[policy] = file_sha(path)
            if target_sha[policy] != proof["file_sha256"]:
                raise ValueError("original anchor copy must preserve exact bytes")
        consumers = tuple(
            tids[p["key"]] for p in plans()[1:] if not p["response_policy"].startswith("original_")
        )
        history = build_history_from_frozen(
            registry,
            provider,
            consumers,
            input_folder=inputs,
            output_folder=output / "history",
            calendar=calendar,
            manifest_sha256=spec["manifest_sha256"],
        )
        cache = VerifiedHistoryCache(registry, consumers[0], history)
        model_dir = output / "models"
        model_dir.mkdir(exist_ok=False)
        models, paths = {}, {}
        for policy in POLICIES:
            source, other = tids[f"{policy}-82"], tids[f"{policy}-164"]
            models[policy], paths[policy] = {}, {}
            for year in (2023, 2024):
                path = model_dir / f"{policy}-{year}.json"
                models[policy][year] = fit_history_predictor(
                    registry,
                    source,
                    provider,
                    history_path=history,
                    year=year,
                    policy=policy,
                    model_path=path,
                    cache=cache,
                )
                paths[policy][year] = path
                models_sha[f"{policy}-{year}"] = file_sha(path)
            # Both source annual fits must be complete before sharing actual bytes.
            for year in (2023, 2024):
                bind_shared_history_predictor(
                    registry,
                    source,
                    other,
                    provider,
                    history_path=history,
                    model_path=paths[policy][year],
                    year=year,
                    policy=policy,
                    calendar=calendar,
                )
        diagnostics = {}
        for policy in POLICIES + ("hash", "lowvol"):
            prior_targets = None
            for cost in COSTS:
                key, tid = f"{policy}-{cost}", tids[f"{policy}-{cost}"]
                targets, diagnostic, sessions = history_targets(
                    registry,
                    tid,
                    history_path=history,
                    policy=policy,
                    models=models.get(policy),
                    paths=paths.get(policy),
                    cache=cache,
                )
                if prior_targets is None:
                    prior_targets = targets
                    write_json(target_dir / f"{policy}.json", [asdict(t) for t in targets])
                    target_sha[policy] = file_sha(target_dir / f"{policy}.json")
                    diagnostics[policy] = diagnostic
                elif targets != prior_targets or diagnostic != diagnostics[policy]:
                    raise ValueError("cost must not change fitted policy targets or support")
                report = execute_response_account(sessions, targets, roundtrip_bps=cost)
                records[key] = _finish_account(
                    registry, tid, output, key, report, sessions, targets, cost, target_sha[policy]
                )
        # Anchor selection/target bytes remain unchanged; bars use B3 semantics.
        for policy, targets in anchors.items():
            for cost in COSTS:
                key = f"{policy}-{cost}"
                config = replace(
                    report.config,
                    rebalance_mode="full_target",
                    commission_bps=3 * cost // 41,
                    sell_tax_bps=5 * cost // 41,
                    slippage_bps=15 * cost // 41,
                )
                anchored = run_stateful_execution(
                    sessions, targets, config, initial_nav=3_000_000, retain_details=True
                )
                records[key] = _finish_account(
                    registry,
                    tids[key],
                    output,
                    key,
                    anchored,
                    sessions,
                    targets,
                    cost,
                    target_sha[policy],
                )
        supervised_bindings = sum(
            len(registry.fit_lineage(tid)["fits"])
            for key, tid in tids.items()
            if key != "response-provider"
        )
        if len(models_sha) != 14 or supervised_bindings != 28:
            raise ValueError("all14 actual models and28 native cost bindings required")
        for key, digest in models_sha.items():
            if file_sha(model_dir / f"{key}.json") != digest:
                raise ValueError("shared predictor bytes changed during accounts")
        result = {
            "version": VERSION,
            "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
            "reserved_trials": BUDGET,
            "raw_global_trial_lower_bound": DEBT + BUDGET,
            "trial_ids": tids,
            "spec_sha256": sha256_json(spec),
            "models_sha256": models_sha,
            "targets_sha256": target_sha,
            "history_sha256": file_sha(history),
            "provider_fit_lineage_sha256": registry.fit_lineage(provider)["sha256"],
            "records": records,
            "diagnostics": diagnostics,
            "actual_supervised_models": len(models_sha),
            "supervised_native_bindings": supervised_bindings,
            "independent_source_model_target_audit": "NOT_RUN",
            "statistics": spec["contract"]["statistics"],
            **screen_records(records, diagnostics, independent_audit_pass=False),
        }
        with registry.connect() as conn:
            if (
                conn.execute(
                    "SELECT count(*) FROM trials WHERE result_json IS NOT NULL"
                ).fetchone()[0]
                != BUDGET
            ):
                raise ValueError("all23 native trial results required")
        write_json(output / "RESULT.json", result)
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {
                "status": "ABORTED",
                "exception_type": type(exc).__name__,
                "reserved_trials": BUDGET,
                "raw_global_trial_lower_bound": DEBT + BUDGET,
                "completed_account_keys": sorted(records),
                "trial_ids": tids,
                "validated_alpha": False,
            },
        )
        raise


def _finish_account(registry, tid, output, key, report, sessions, targets, cost, target_hash):
    evidence = audit_response_account(
        report, sessions, targets, roundtrip_bps=cost, mode=report.config.rebalance_mode
    )
    summary = account_summary(report)
    if (
        not evidence["pass"]
        or abs(evidence["pooled_sharpe"] - summary["pooled_sharpe"]) > 1e-10
        or any(abs(v - summary["years"][y]) > 1e-10 for y, v in evidence["years"].items())
    ):
        raise ValueError("independent account metrics must reconcile")
    record = {
        "key": key,
        "trial_id": tid,
        "roundtrip_bps": cost,
        **summary,
        "execution": execution_summary(report),
        "audit": evidence,
        "account_sha256": save_account(output, key, report),
        "target_sha256": target_hash,
        "fit_lineage_sha256": registry.fit_lineage(tid)["sha256"],
        "feature_sources_sha256": registry.feature_sources(tid)["sha256"],
    }
    registry.record_trial_result(tid, json.dumps(record, sort_keys=True, allow_nan=False))
    return record
