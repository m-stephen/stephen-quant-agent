"""Complete frozen-model account continuation, never an empirical authorization.

A separate launcher must bind the reviewed code, consumed claims, preregistration
and one shared claim before calling this backend. The old native registry stays
read-only; inherited fits are never copied into new Trials as newly fitted work.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from stephen_quant.baseline.stateful import run_stateful_execution
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import _finish_account

from .flow_response_accounts import execute_response_account, history_targets
from .flow_response_history import VerifiedHistoryCache
from .flow_response_launch import ReadOnlyRegistry, read, write
from .flow_response_predictor import POLICIES
from .flow_response_protocol import COSTS, contract, plans, screen_records
from .flow_response_replay import load_original_targets
from .search_power_dsl import sha256_json

VERSION = "11.21-frozen-model-continuation-1"
PRIOR_DEBT, BUDGET = 3707, 22


def account_plans():
    return plans()[1:]


def validate_spec(spec):
    if (
        spec["version"] != VERSION
        or spec["prior_debt"] != PRIOR_DEBT
        or spec["budget"] != BUDGET
        or spec["accounts"] != account_plans()
        or sha256_json(spec["research_contract"]) != sha256_json(contract())
        or spec["new_fits"] != 0
        or spec["validated_alpha"] is not False
    ):
        raise ValueError("complete frozen continuation contract required")
    # The inherited contract's old multiplicity prose remains historical. The
    # new native experiment separately binds prior3707 +22, never resets it.
    inherited = spec["inherited"]
    expected = {p["key"] for p in plans()}
    if set(inherited["trial_ids"]) != expected or len(set(inherited["trial_ids"].values())) != 23:
        raise ValueError("all inherited native identities required")
    required = {"registry.sqlite3", "history/history.json"} | {
        f"models/{policy}-{year}.json" for policy in POLICIES for year in (2023, 2024)
    }
    if not required <= set(inherited["files"]):
        raise ValueError("frozen source registry/history/all14 models required")
    for relative, digest in inherited["files"].items():
        if (
            Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("invalid inherited relative path/hash")


def reserve_continuation(output, spec):
    validate_spec(spec)
    path = Path(output) / "registry.sqlite3"
    if path.exists():
        raise FileExistsError("continuation database already exists")
    registry = ExperimentRegistry(path)
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {
                "inherited_artifacts": sha256_json(spec["inherited"]),
                "anchor_card": spec["anchor_card_sha256"],
                "consumed_attempts": spec["consumed_evidence_sha256"],
            }
        )
    )
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            VERSION,
            "All22 frozen-model accounts; no production refit and no fresh-OOS claim",
            sid,
            spec["runtime_code_sha256"],
            json.dumps(spec, sort_keys=True),
        ),
        sha256_json(spec),
    )
    tids = {}
    for plan in account_plans():
        tid, _ = registry.create_trial_deterministic(
            TrialSpec(
                eid,
                plan["key"],
                "inherited-frozen-model",
                json.dumps(plan, sort_keys=True),
                184,
                "unused-no-refit",
                "unused-no-refit",
                "2023-01-01",
                "2024-12-31",
                "unused",
                "unused",
                fit_stages=(),
            ),
            sha256_json(plan),
        )
        registry.declare_feature_sources(tid, ())
        tids[plan["key"]] = tid
    check_reservations(registry, tids, spec, output)
    return registry, tids


def check_reservations(registry, tids, spec, output):
    validate_spec(spec)
    if (
        Path(registry.db_path).resolve() != Path(output).resolve() / "registry.sqlite3"
        or set(tids) != {p["key"] for p in account_plans()}
        or len(set(tids.values())) != BUDGET
        or registry.global_trial_count() != BUDGET
    ):
        raise ValueError("all22 native reservations must belong to this operation")
    with registry.connect() as db:
        for p in account_plans():
            tid = tids[p["key"]]
            row = db.execute(
                "SELECT t.hyperparams,t.result_json,e.search_space FROM trials t "
                "JOIN experiments e ON e.experiment_id=t.experiment_id WHERE t.trial_id=?",
                (tid,),
            ).fetchone()
            if (
                row is None
                or row[1] is not None
                or json.loads(row[0]) != p
                or sha256_json(json.loads(row[2])) != sha256_json(spec)
                or registry.fit_lineage(tid)["stages"]
                or registry.fit_lineage(tid)["fits"]
                or registry.feature_sources(tid)["providers"]
            ):
                raise ValueError("changed, completed or fitted continuation reservation")


def verified_inherited(spec, output):
    """Only called after new complete native reservation checks."""
    root = Path(spec["inherited"]["root"]).resolve(strict=True)
    destination = Path(output).resolve()
    if root == destination or root in destination.parents or destination in root.parents:
        raise ValueError("continuation output must be disjoint from inherited evidence")
    for relative, digest in spec["inherited"]["files"].items():
        path = root / relative
        if root not in path.resolve(strict=True).parents or file_sha(path) != digest:
            raise ValueError("inherited evidence path or bytes changed")
    registry = ReadOnlyRegistry(root / "registry.sqlite3")
    tids = spec["inherited"]["trial_ids"]
    if registry.global_trial_count() != 23:
        raise ValueError("all23 original native reservations required")
    models, paths, fingerprints = {}, {}, {}
    for policy in POLICIES:
        models[policy], paths[policy] = {}, {}
        for year in (2023, 2024):
            path = root / f"models/{policy}-{year}.json"
            model = read(path)
            for cost in COSTS:
                lineage = registry.fit_lineage(tids[f"{policy}-{cost}"])
                if len(lineage["fits"]) != 2:
                    raise ValueError("both inherited annual fits must be complete")
                if not any(f["artifact_sha256"] == file_sha(path) for f in lineage["fits"]):
                    raise ValueError("inherited model missing actual native binding")
            models[policy][year], paths[policy][year] = model, path
            fingerprints[f"{policy}-{year}"] = file_sha(path)
    return registry, root, models, paths, fingerprints


def execute_continuation(registry, tids, spec, *, output, original_tree):
    """All22 accounts once; save partial failures, never retry or certify Alpha."""
    output = Path(output).resolve()
    check_reservations(registry, tids, spec, output)
    original = Path(original_tree).resolve(strict=True)
    if original == output or original in output.parents or output in original.parents:
        raise ValueError("continuation output must be disjoint from original anchors")
    write(output / "BACKEND_CLAIM.json", {"spec_sha256": sha256_json(spec), "reserved": BUDGET})
    records = {}
    try:
        write(output / "frozen_spec.json", spec)
        old, inherited, models, model_paths, model_sha = verified_inherited(spec, output)
        old_tids = spec["inherited"]["trial_ids"]
        history = inherited / "history/history.json"
        cache = VerifiedHistoryCache(old, old_tids["response-82"], history)
        document, _ = cache.get(old, old_tids["response-82"], history)
        calendar = [d for d in document["calendar"] if "2023-01-01" <= d <= "2024-12-31"]
        anchors, anchor_proofs = load_original_targets(
            registry,
            tids,
            original_tree=original,
            card_sha256=spec["anchor_card_sha256"],
            calendar=calendar,
        )
        target_sha, diagnostics = {}, {}
        for policy in POLICIES + ("hash", "lowvol"):
            targets, diagnostic, sessions = history_targets(
                old,
                old_tids[f"{policy}-82"],
                history_path=history,
                policy=policy,
                models=models.get(policy),
                paths=model_paths.get(policy),
                cache=cache,
            )
            target = output / f"targets/{policy}.json"
            write(target, [asdict(t) for t in targets])
            target_sha[policy], diagnostics[policy] = file_sha(target), diagnostic
            # Existing generated targets are frozen inputs, not a new selection.
            saved = inherited / f"targets/{policy}.json"
            if (
                f"targets/{policy}.json" in spec["inherited"]["files"]
                and sha256_json(read(saved)) != sha256_json([asdict(t) for t in targets])
            ):
                raise ValueError("frozen inherited target changed")
            for cost in COSTS:
                # Both original cost bindings are rechecked by the guarded predictor.
                if policy in POLICIES:
                    for year, model in models[policy].items():
                        dates = [d for d in calendar if d.startswith(str(year))]
                        old.assert_prediction_fit(
                            old_tids[f"{policy}-{cost}"],
                            model=model,
                            artifact_path=model_paths[policy][year],
                            signal_date=dates[0],
                            prediction_date=dates[1],
                        )
                key = f"{policy}-{cost}"
                report = execute_response_account(sessions, targets, roundtrip_bps=cost)
                records[key] = _finish_account(
                    registry,
                    tids[key],
                    output,
                    key,
                    report,
                    sessions,
                    targets,
                    cost,
                    target_sha[policy],
                )
        for policy, targets in anchors.items():
            target = output / f"targets/{policy}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(anchor_proofs[policy]["target_bytes"])
            target_sha[policy] = file_sha(target)
            for cost in COSTS:
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
                key = f"{policy}-{cost}"
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
        verified_inherited(spec, output)  # Includes unchanged old native database hash.
        result = {
            "version": VERSION,
            "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
            "reserved_trials": BUDGET,
            "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
            "new_fits": 0,
            "inherited_supervised_models": 14,
            "inherited_native_bindings": 28,
            "trial_ids": tids,
            "spec_sha256": sha256_json(spec),
            "inherited_sha256": sha256_json(spec["inherited"]),
            "models_sha256": model_sha,
            "history_sha256": file_sha(history),
            "targets_sha256": target_sha,
            "records": records,
            "diagnostics": diagnostics,
            "independent_source_model_target_audit": "NOT_RUN",
            "statistics": spec["research_contract"]["statistics"],
            **screen_records(records, diagnostics, independent_audit_pass=False),
        }
        with registry.connect() as db:
            if db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] != 0:
                raise ValueError("continuation must not create fits")
            if (
                db.execute("SELECT count(*) FROM trials WHERE result_json IS NOT NULL").fetchone()[
                    0
                ]
                != 22
            ):
                raise ValueError("all22 native account results required")
        write(output / "RESULT.json", result)
        return result
    except BaseException as exc:
        write(
            output / "ABORTED.json",
            {
                "exception_type": type(exc).__name__,
                "completed_account_keys": sorted(records),
                "reserved_trials": BUDGET,
                "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
                "validated_alpha": False,
                "automatic_retry": False,
            },
        )
        raise
