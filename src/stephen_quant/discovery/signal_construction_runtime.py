"""Four native no-refit bridge accounts; this backend is NOT launch authority.

Only a separately reviewed once-only launcher may call this with real sources.
All four reservations precede numerical reads. The original model registry and
history stay read-only; inherited fits are not copied as newly fitted evidence.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import _finish_account

from .flow_response_accounts import execute_response_account
from .flow_response_continuation import verified_inherited
from .flow_response_history import VerifiedHistoryCache
from .flow_response_launch import write
from .flow_response_predictor import POLICIES as ORIGINAL_POLICIES
from .flow_response_protocol import plans as original_plans
from .search_power_dsl import sha256_json
from .signal_construction import BUDGET, POLICIES, PRIOR_DEBT, VERSION, contract, frozen_targets


def require_hash(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("raw SHA256 binding required")


def validate_spec(spec):
    if (
        set(spec)
        != {
            "version",
            "prior_debt",
            "budget",
            "new_fits",
            "validated_alpha",
            "research_contract",
            "runtime_code_sha256",
            "completed_parent_evidence_sha256",
            "inherited",
            "calendar",
        }
        or spec["version"] != VERSION
        or spec["prior_debt"] != PRIOR_DEBT
        or spec["budget"] != BUDGET
        or spec["new_fits"] != 0
        or spec["validated_alpha"] is not False
        or sha256_json(spec["research_contract"]) != sha256_json(contract())
    ):
        raise ValueError("frozen four-account bridge specification required")
    for key in ("runtime_code_sha256", "completed_parent_evidence_sha256"):
        require_hash(spec[key])
    inherited = spec["inherited"]
    if (
        not Path(inherited["root"]).is_absolute()
        or set(inherited["trial_ids"]) != {p["key"] for p in original_plans()}
        or len(set(inherited["trial_ids"].values())) != 23
    ):
        raise ValueError("complete original23 native identities required")
    required = {"registry.sqlite3", "history/history.json"} | {
        f"models/{p}-{year}.json" for p in ORIGINAL_POLICIES for year in (2023, 2024)
    }
    if not required <= set(inherited["files"]):
        raise ValueError("original model/history byte bindings required")
    for relative, digest in inherited["files"].items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("relative inherited artifact required")
        require_hash(digest)
    calendar = spec["calendar"]
    if (
        set(calendar) != {"count", "sha256"}
        or type(calendar["count"]) is not int
        or calendar["count"] != 726
    ):
        raise ValueError("original complete726-day calendar required")
    require_hash(calendar["sha256"])


def snapshot(spec):
    return build_composite_snapshot_manifest(
        {
            "completed_parent": spec["completed_parent_evidence_sha256"],
            "inherited": sha256_json(spec["inherited"]),
            "calendar": spec["calendar"]["sha256"],
        }
    )


def reserve_accounts(output, spec):
    validate_spec(spec)
    path = Path(output) / "registry.sqlite3"
    if path.exists():
        raise FileExistsError("native bridge reservations exist; no replay")
    registry = ExperimentRegistry(path)
    sid = registry.register_snapshot(snapshot(spec))
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            VERSION,
            "Four frozen-signal construction accounts, no new fits or Alpha promotion",
            sid,
            spec["runtime_code_sha256"],
            json.dumps(spec, sort_keys=True),
        ),
        sha256_json(spec),
    )
    tids = {}
    for p in contract()["accounts"]:
        tid, _ = registry.create_trial_deterministic(
            TrialSpec(
                eid,
                p["key"],
                "inherited-frozen-model",
                json.dumps(p, sort_keys=True),
                184,
                "unused-no-refit",
                "unused-no-refit",
                "2023-01-01",
                "2024-12-31",
                "unused",
                "unused",
                fit_stages=(),
            ),
            sha256_json(p),
        )
        registry.declare_feature_sources(tid, ())
        tids[p["key"]] = tid
    check_native(registry, output, spec, tids)
    return registry, tids


def check_native(registry, output, spec, tids, result=None):
    validate_spec(spec)
    root = Path(output).resolve()
    if (
        Path(registry.db_path).resolve() != root / "registry.sqlite3"
        or registry.global_trial_count() != 4
        or set(tids) != {p["key"] for p in contract()["accounts"]}
        or len(set(tids.values())) != 4
        or (root / "ABORTED.json").exists()
    ):
        raise ValueError("all four owned native reservations required")
    if result is not None and (
        result["version"] != VERSION
        or result["status"] != "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        or result["spec_sha256"] != sha256_json(spec)
        or result["reserved_trials"] != 4
        or result["raw_global_trial_lower_bound"] != 3737
        or result["new_fits"] != 0
        or result["trial_ids"] != tids
        or set(result["records"]) != set(tids)
        or set(result["targets_sha256"]) != set(POLICIES)
        or set(result["diagnostics"]) != set(POLICIES)
        or result["history_sha256"] != spec["inherited"]["files"]["history/history.json"]
        or result["calendar"] != spec["calendar"]
        or result["models_sha256"]
        != {
            f"{p}-{year}": spec["inherited"]["files"][f"models/{p}-{year}.json"]
            for p in ORIGINAL_POLICIES
            for year in (2023, 2024)
        }
        or result["statistics"] != contract()["statistics"]
        or result["validated_alpha"] is not False
        or result["independent_source_target_audit"] != "NOT_RUN"
    ):
        raise ValueError("complete native diagnostic result required; never Alpha promotion")
    experiments = set()
    with registry.connect() as db:
        if db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("bridge cannot create fits")
        for p in contract()["accounts"]:
            tid = tids[p["key"]]
            row = db.execute(
                "SELECT t.hyperparams,t.result_json,e.search_space,e.code_version,"
                "e.dataset_snapshot_id,e.experiment_id FROM trials t JOIN experiments e USING(experiment_id) WHERE t.trial_id=?",
                (tid,),
            ).fetchone()
            if (
                row is None
                or json.loads(row[0]) != p
                or sha256_json(json.loads(row[2])) != sha256_json(spec)
                or row[3] != spec["runtime_code_sha256"]
                or registry.snapshot_sha256(row[4]) != snapshot(spec).snapshot_sha256
                or (result is None and row[1] is not None)
                or (
                    result is not None
                    and (
                        row[1] is None
                        or sha256_json(json.loads(row[1]))
                        != sha256_json(result["records"][p["key"]])
                    )
                )
            ):
                raise ValueError("native policy/code/snapshot/result binding mismatch")
            experiments.add(row[5])
            fits, sources = registry.fit_lineage(tid), registry.feature_sources(tid)
            if fits["fits"] or fits["stages"] or sources["providers"]:
                raise ValueError("new trial cannot impersonate inherited fit/provider")
            if result is not None:
                r = result["records"][p["key"]]
                if (
                    r["fit_lineage_sha256"] != fits["sha256"]
                    or r["feature_sources_sha256"] != sources["sha256"]
                ):
                    raise ValueError("completed native lineage differs")
    if len(experiments) != 1:
        raise ValueError("one four-account experiment required")


def open_inputs(spec, output):
    # Caller must first pass check_native; this helper reads numerical sources.
    old, root, models, paths, fingerprints = verified_inherited(spec, output)
    consumer = spec["inherited"]["trial_ids"]["response-82"]
    path = root / "history/history.json"
    cache = VerifiedHistoryCache(old, consumer, path)
    history, proof = cache.get(old, consumer, path)
    calendar = list(history["calendar"])
    if {"count": len(calendar), "sha256": sha256_json(calendar)} != spec["calendar"]:
        raise ValueError("complete frozen calendar binding differs")
    # Explicitly check BOTH inherited cost consumers before reuse of shared targets.
    for policy in ("response", "risk"):
        for year in (2023, 2024):
            days = [d for d in calendar if d.startswith(str(year))]
            if len(days) < 2:
                raise ValueError("complete annual prediction sessions required")
            for cost in (82, 164):
                old.assert_prediction_fit(
                    spec["inherited"]["trial_ids"][f"{policy}-{cost}"],
                    model=models[policy][year],
                    artifact_path=paths[policy][year],
                    signal_date=days[0],
                    prediction_date=days[1],
                )
    return old, root, models, paths, fingerprints, cache, history, proof


def execute_accounts(registry, tids, spec, *, output):
    output = Path(output).resolve()
    check_native(registry, output, spec, tids)
    write(output / "BACKEND_CLAIM.json", {"spec_sha256": sha256_json(spec), "reserved": BUDGET})
    records = {}
    try:
        write(output / "frozen_spec.json", spec)
        old, root, models, paths, fingerprints, cache, _history, _ = open_inputs(spec, output)
        diagnostics, targets_sha = {}, {}
        for policy in POLICIES:
            original = policy.removeprefix("global_")
            targets, diagnostic, sessions = frozen_targets(
                old,
                spec["inherited"]["trial_ids"][f"{original}-82"],
                history_path=root / "history/history.json",
                policy=policy,
                models=models[original],
                paths=paths[original],
                cache=cache,
            )
            target_path = output / f"targets/{policy}.json"
            write(target_path, [asdict(t) for t in targets])
            targets_sha[policy], diagnostics[policy] = file_sha(target_path), diagnostic
            for cost in (82, 164):
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
                    targets_sha[policy],
                )
        cache.get(old, spec["inherited"]["trial_ids"]["response-82"], root / "history/history.json")
        verified_inherited(spec, output)
        result = {
            "version": VERSION,
            "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
            "reserved_trials": 4,
            "raw_global_trial_lower_bound": 3737,
            "new_fits": 0,
            "trial_ids": tids,
            "spec_sha256": sha256_json(spec),
            "history_sha256": file_sha(root / "history/history.json"),
            "calendar": spec["calendar"],
            "models_sha256": fingerprints,
            "records": records,
            "targets_sha256": targets_sha,
            "diagnostics": diagnostics,
            "independent_source_target_audit": "NOT_RUN",
            "validated_alpha": False,
            "statistics": contract()["statistics"],
        }
        check_native(registry, output, spec, tids, result)
        write(output / "RESULT.json", result)
        return result
    except BaseException as exc:
        write(
            output / "ABORTED.json",
            {
                "exception_type": type(exc).__name__,
                "completed_account_keys": sorted(records),
                "reserved_trials": 4,
                "raw_global_trial_lower_bound": 3737,
                "validated_alpha": False,
                "automatic_retry": False,
            },
        )
        raise
