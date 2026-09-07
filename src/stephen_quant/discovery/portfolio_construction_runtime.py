"""Four no-fit diagnostic accounts. This backend alone is not launch authority.

The reviewed launcher must first verify the completed parent, frozen code and
preregistration, consume one shared claim, and reserve the entire four-Trial
budget. Neither an attractive outcome nor a failure permits automatic replay.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import _finish_account

from .calendar_robustness import combine_sleeves
from .flow_response_accounts import execute_response_account
from .flow_response_history import VerifiedHistoryCache
from .flow_response_launch import ReadOnlyRegistry, _bound, write
from .flow_response_series import clock
from .flow_response_views import HistoricalSessions
from .portfolio_construction import BUDGET, POLICIES, PRIOR_DEBT, VERSION, contract, select_global
from .search_power_dsl import sha256_json


def account_plans():
    return [
        {**p, "response_policy": p["policy"], "execution_mode": "target_changes"}
        for p in contract()["accounts"]
    ]


def validate_spec(spec):
    if (
        spec["version"] != VERSION
        or spec["prior_debt"] != PRIOR_DEBT
        or spec["budget"] != BUDGET
        or spec["new_fits"] != 0
        or spec["validated_alpha"] is not False
        or spec["accounts"] != account_plans()
        or sha256_json(spec["research_contract"]) != sha256_json(contract())
        or set(spec["history"]) != {"root", "registry_sha256", "history_sha256", "consumer"}
    ):
        raise ValueError("fixed four-account no-fit diagnostic contract required")
    for digest in (
        spec["runtime_code_sha256"],
        spec["completed_parent_evidence_sha256"],
        spec["history"]["registry_sha256"],
        spec["history"]["history_sha256"],
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("raw SHA256 evidence required")
    if not spec["history"]["consumer"] or not Path(spec["history"]["root"]).is_absolute():
        raise ValueError("explicit inherited native consumer and local root required")


def snapshot(spec):
    return build_composite_snapshot_manifest(
        {
            "completed_parent": spec["completed_parent_evidence_sha256"],
            "inherited_history": sha256_json(spec["history"]),
        }
    )


def reserve_accounts(output, spec):
    validate_spec(spec)
    path = Path(output) / "registry.sqlite3"
    if path.exists():
        raise FileExistsError("construction registry exists; no reset or replay")
    registry = ExperimentRegistry(path)
    sid = registry.register_snapshot(snapshot(spec))
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            VERSION,
            "Fixed global40/top60 construction diagnostic; no new Alpha or fitted model",
            sid,
            spec["runtime_code_sha256"],
            json.dumps(spec, sort_keys=True),
        ),
        sha256_json(spec),
    )
    tids = {}
    for p in account_plans():
        tid, _ = registry.create_trial_deterministic(
            TrialSpec(
                eid,
                p["key"],
                "no-fit-construction",
                json.dumps(p, sort_keys=True),
                184,
                "unused-no-fit",
                "unused-no-fit",
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
    """Gate metadata before numerical reads; reconcile all completed native rows."""
    validate_spec(spec)
    root = Path(output).resolve()
    if (
        Path(registry.db_path).resolve() != root / "registry.sqlite3"
        or registry.global_trial_count() != BUDGET
        or set(tids) != {p["key"] for p in account_plans()}
        or len(set(tids.values())) != BUDGET
        or (root / "ABORTED.json").exists()
    ):
        raise ValueError("all four owned native reservations required")
    if result is not None and (
        result["version"] != VERSION
        or result["status"] != "COMPLETE_PENDING_INDEPENDENT_AUDIT"
        or result["spec_sha256"] != sha256_json(spec)
        or result["reserved_trials"] != BUDGET
        or result["raw_global_trial_lower_bound"] != PRIOR_DEBT + BUDGET
        or result["new_fits"] != 0
        or result["trial_ids"] != tids
        or set(result["records"]) != set(tids)
        or set(result["targets_sha256"]) != set(POLICIES)
        or set(result["diagnostics"]) != set(POLICIES)
        or result["history_sha256"] != spec["history"]["history_sha256"]
        or result["statistics"] != contract()["statistics"]
        or result["validated_alpha"] is not False
        or result["independent_source_target_audit"] != "NOT_RUN"
    ):
        raise ValueError("complete diagnostic output required; no Alpha promotion")
    experiments = set()
    with registry.connect() as db:
        if db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("diagnostic must not create any new fits")
        for p in account_plans():
            tid = tids[p["key"]]
            row = db.execute(
                "SELECT t.hyperparams,t.result_json,e.search_space,e.code_version,"
                "e.dataset_snapshot_id,e.experiment_id FROM trials t "
                "JOIN experiments e USING(experiment_id) WHERE t.trial_id=?",
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
                raise ValueError("native account/spec/code/snapshot mismatch")
            experiments.add(row[5])
            fits, sources = registry.fit_lineage(tid), registry.feature_sources(tid)
            if fits["fits"] or fits["stages"] or sources["providers"]:
                raise ValueError("explicit no-fit/no-new-provider native declaration required")
            if result is not None:
                record = result["records"][p["key"]]
                if record["fit_lineage_sha256"] != fits["sha256"] or (
                    record["feature_sources_sha256"] != sources["sha256"]
                ):
                    raise ValueError("completed native lineage changed")
    if len(experiments) != 1:
        raise ValueError("four accounts must share one frozen experiment")


def open_history(spec, output):
    """Called only after a full reservation/completion gate by production/audit."""
    h = spec["history"]
    root, destination = Path(h["root"]).resolve(strict=True), Path(output).resolve()
    if root == destination or root in destination.parents or destination in root.parents:
        raise ValueError("output must be disjoint from inherited historical artifacts")
    _bound(root, "registry.sqlite3", h["registry_sha256"])
    _bound(root, "history/history.json", h["history_sha256"])
    old = ReadOnlyRegistry(root / "registry.sqlite3")
    with old.connect() as db:
        row = db.execute(
            "SELECT hyperparams FROM trials WHERE trial_id=?", (h["consumer"],)
        ).fetchone()
    if row is None or json.loads(row[0]).get("response_policy") != "lowvol":
        raise ValueError("original no-fit lowvol history consumer required")
    if old.fit_lineage(h["consumer"])["stages"] or old.fit_lineage(h["consumer"])["fits"]:
        raise ValueError("inherited consumer cannot be a fitted prediction policy")
    path = root / "history/history.json"
    cache = VerifiedHistoryCache(old, h["consumer"], path)
    document, proof = cache.get(old, h["consumer"], path)
    return old, path, cache, document, proof


def construction_targets(history, policy):
    """Pure fixed-calendar target construction; no numerical source discovery."""
    if policy not in POLICIES:
        raise ValueError("fixed diagnostic policy required")
    calendar = history["calendar"]
    if (
        not calendar
        or list(calendar) != sorted(set(calendar))
        or any(not "2022-01-01" <= d <= "2024-12-31" for d in calendar)
    ):
        raise ValueError("ordered unique frozen 2022-2024 calendar required")
    days = [d for d in calendar if d >= "2023-01-01"]
    if not days:
        raise ValueError("development execution sessions required")
    sleeves, diagnostics = [], []
    for phase in (0, 5, 10, 15):
        previous, targets = (), []
        for i, dt in enumerate(days):
            signal = days[i - 1] if i else None
            refresh = i >= phase + 1 and (i - phase - 1) % 20 == 0
            weights = {}
            if refresh:
                rows = history["ranks"][signal]
                chosen = select_global(rows, policy, previous)
                weights = {name: 0.025 for name in chosen}
                diagnostics.append(
                    {
                        "date": signal,
                        "execution_date": dt,
                        "phase": phase,
                        "eligible": len(rows),
                        "selected": len(chosen),
                        "new_members": len(set(chosen) - set(previous)),
                        "selected_names_sha256": sha256_json(chosen),
                        "selected_mean_vol": sum(rows[n]["vol"] for n in chosen) / len(chosen)
                        if chosen
                        else None,
                        "selected_cell_counts": [
                            sum(rows[n]["cell"] == c for n in chosen) for c in range(20)
                        ],
                    }
                )
                previous = chosen
            targets.append(
                TargetAllocation(
                    dt,
                    clock(signal, "23:59:59") if signal else clock(dt, "08:00:00"),
                    weights,
                    refresh,
                )
            )
        sleeves.append(tuple(targets))
    return combine_sleeves(sleeves), diagnostics, HistoricalSessions(history["bars"], days)


def execute_accounts(registry, tids, spec, *, output):
    output = Path(output).resolve()
    check_native(registry, output, spec, tids)
    write(output / "BACKEND_CLAIM.json", {"spec_sha256": sha256_json(spec), "reserved": BUDGET})
    records = {}
    try:
        write(output / "frozen_spec.json", spec)
        old, path, cache, history, _ = open_history(spec, output)
        targets_sha, diagnostics = {}, {}
        for policy in POLICIES:
            targets, diagnostics[policy], sessions = construction_targets(history, policy)
            target = output / f"targets/{policy}.json"
            write(target, [asdict(t) for t in targets])
            targets_sha[policy] = file_sha(target)
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
        cache.get(old, spec["history"]["consumer"], path)
        _bound(
            Path(spec["history"]["root"]), "registry.sqlite3", spec["history"]["registry_sha256"]
        )
        result = {
            "version": VERSION,
            "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
            "reserved_trials": BUDGET,
            "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
            "new_fits": 0,
            "trial_ids": tids,
            "spec_sha256": sha256_json(spec),
            "history_sha256": spec["history"]["history_sha256"],
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
                "reserved_trials": BUDGET,
                "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
                "validated_alpha": False,
                "automatic_retry": False,
            },
        )
        raise
