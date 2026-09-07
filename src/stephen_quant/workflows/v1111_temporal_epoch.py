"""Single-use registered temporal-information epoch; no formal Alpha promotion."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.baseline.stateful import StatefulExecutionConfig, run_stateful_execution
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.reliability_calibration import family_placebo
from stephen_quant.discovery.reliable_research import temporal_selection
from stephen_quant.discovery.residual_execution import fit_stages
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.temporal_increments import (
    MECHANISMS,
    POLICIES,
    VERSION,
    contract,
    fit_year,
    plans,
    targets_for,
    temporal_days,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha, load_frozen_days
from stephen_quant.workflows.v114_reliable_epoch import (
    protected_digest,
    runtime_code_hash,
    write_json,
)
from stephen_quant.workflows.v117_incremental_epoch import save_account
from stephen_quant.workflows.v118_lead_challenge import verify_parent
from stephen_quant.workflows.v1110_residual_epoch import economic_checks

PARENT_SHA = "6559581264e706f932df02c7ec1cc41e15980501cf6313f80a438337a622e2b2"
DEBT = 3289
CLAIM_ROOT = Path(__file__).resolve().parents[3] / "artifacts" / "temporal-increments" / "claims"


def verify_lineage(config):
    old, frozen_file, frozen, _, _, inputs = verify_parent(config)
    parent = Path(config["residual_parent_dir"]).resolve()
    if file_sha(parent / "RESULT.json") != PARENT_SHA:
        raise ValueError("residual parent hash mismatch")
    previous = json.loads((parent / "RESULT.json").read_text(encoding="utf-8"))
    if not previous["engineering_pass"] or previous["raw_global_trial_lower_bound"] != DEBT:
        raise ValueError("parent engineering and cumulative debt required")
    if not json.loads((parent / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))["pass"]:
        raise ValueError("parent independent audit required")
    protected = [frozen_file, *config["protected_paths"]]
    for p in (old, parent):
        protected.extend(
            p / n for n in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json")
        )
    return inputs, frozen, protected, (old, parent)


def run(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if (
        type(config.get("preregistration_comment")) is not int
        or config["preregistration_comment"] <= 0
    ):
        raise ValueError("positive preregistration comment required")
    inputs, frozen, protected, parents = verify_lineage(config)
    output = Path(config["output_dir"]).resolve()
    if any(output == p or p in output.parents or output in p.parents for p in (inputs, *parents)):
        raise ValueError("independent output required")
    if output.exists():
        raise FileExistsError("operation exists; inspect without replay")
    registered = [
        {**p, "identity": sha256_json({"plan": p, "contract": contract(), "version": VERSION})}
        for p in plans()
    ]
    before, _ = protected_digest(protected)
    spec = {
        "version": VERSION,
        "issue": 184,
        "contract": contract(),
        "source_result_sha256": PARENT_SHA,
        "snapshot_sha256": frozen["snapshot_sha256"],
        "runtime_code_sha256": runtime_code_hash(),
        "protected_before": before,
        "raw_debt_before": DEBT,
        "reserved_new_trials": len(registered),
        "preregistration_comment": config["preregistration_comment"],
        "exposure": contract()["exposure"],
        "validated_alpha": False,
    }
    write_json(
        CLAIM_ROOT / (PARENT_SHA + ".json"),
        {
            "output": str(output),
            "spec_sha256": sha256_json(spec),
            "reserved_trials": len(registered),
        },
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "trials": registered,
            "spec_sha256": sha256_json(spec),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": frozen["snapshot_sha256"]}),
            vendor_version=VERSION,
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "temporal_increments",
                "path information within fixed low-risk allocation",
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        tids = {}
        for p in registered:
            stages = (
                fit_stages((p["year"],))
                if p["kind"] == "fit"
                else (fit_stages() if p["policy"] in MECHANISMS else ())
            )
            train_end = f"{p['year'] - 1}-12-31" if p["kind"] == "fit" else "2023-12-31"
            trial = TrialSpec(
                eid,
                p["policy"],
                p["identity"],
                json.dumps(p),
                184,
                "2022-01-01",
                train_end,
                "2023-01-01",
                "2024-12-31",
                "unused",
                "unused",
                fit_stages=stages,
            )
            tids[p["identity"]] = registry.create_trial_deterministic(trial, p["identity"])[0]
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        days, coverage = temporal_days(days)
        write_json(output / "TEMPORAL_COVERAGE.json", coverage)
        window = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any(sum(d.date.startswith(y) for d in window) < 200 for y in ("2023", "2024")):
            raise ValueError("incomplete development years")
        models, model_paths, cache = {}, {}, {}
        completed = 0
        for year in (2023, 2024):
            models[year] = fit_year(days, year, cache)
            model_paths[year] = output / "models" / f"{year}.json"
            write_json(model_paths[year], models[year])
            for p in registered:
                is_fit = p["kind"] == "fit" and p["year"] == year
                is_account = p["kind"] == "account" and p["policy"] in MECHANISMS
                if is_fit or is_account:
                    tid = tids[p["identity"]]
                    registry.record_model_fit(
                        tid, str(year), model=models[year], artifact_path=model_paths[year]
                    )
                    if is_fit:
                        registry.record_trial_result(
                            tid, json.dumps(models[year]["models"][p["policy"]], sort_keys=True)
                        )
                        completed += 1
            print(
                json.dumps(
                    {
                        "fitted_year": year,
                        "cutoff": models[year]["fit_cutoff"],
                        "completed": completed,
                    }
                ),
                flush=True,
            )
        records, target_diagnostics = {}, {}
        for policy in POLICIES:
            records[policy] = {}
            for cost in (41, 82, 102):
                p = next(
                    p
                    for p in registered
                    if p["kind"] == "account" and p["policy"] == policy and p["cost_bps"] == cost
                )
                tid = tids[p["identity"]]
                # Every account, not merely the fit Trial, must be bound before use.
                targets, diagnostics = targets_for(
                    registry, tid, window, models, policy, model_paths, cache
                )
                target_hash = sha256_json([asdict(t) for t in targets])
                if cost == 41:
                    write_json(
                        output / "targets" / (policy + ".json"), [asdict(t) for t in targets]
                    )
                    target_diagnostics[policy] = diagnostics
                elif records[policy]["41"]["targets_sha256"] != target_hash:
                    raise ValueError("cost scenario changed frozen target policy")
                cfg = StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=3 if cost == 41 else 6,
                    sell_tax_bps=5 if cost == 41 else 10,
                    slippage_bps=15 if cost == 41 else 30 if cost == 82 else 40,
                )
                report = run_stateful_execution(
                    tuple(d.bars for d in window), targets, cfg, initial_nav=3_000_000
                )
                summary = account_summary(report)
                summary.update(
                    audit=audit_account(report),
                    account_sha256=save_account(output, f"{policy}-{cost}", report),
                    targets_sha256=target_hash,
                    fit_lineage_sha256=registry.fit_lineage(tid)["sha256"],
                )
                records[policy][str(cost)] = summary
                registry.record_trial_result(tid, json.dumps(summary, sort_keys=True))
                completed += 1
            write_json(output / "policies" / (policy + ".json"), records[policy])
            print(json.dumps({"policy": policy, "completed": completed}), flush=True)
        checks = {
            m: {
                c: economic_checks(
                    records[m][c], records["lowvol"][c], records["stable_lowrisk"][c]
                )
                for c in ("82", "102")
            }
            for m in MECHANISMS
        }
        # Legacy key risk_hash_increment now explicitly refers to stable_lowrisk.
        for row in checks.values():
            for values in row.values():
                values["stable_lowrisk_increment"] = values.pop("risk_hash_increment")
        matrix = {
            m: [
                a - b
                for a, b in zip(
                    records[m]["82"]["daily_returns"],
                    records["stable_lowrisk"]["82"]["daily_returns"],
                    strict=True,
                )
            ]
            for m in MECHANISMS
        }
        distinct = len({sha256_json(v) for v in matrix.values() if any(abs(x) > 1e-14 for x in v)})
        if distinct < 2:
            stats = {
                "status": "NOT_IDENTIFIABLE",
                "reason": "fewer_than_two_distinct_nonzero_active_paths",
            }
        else:
            stats = temporal_selection(
                [d.date for d in window], matrix, DEBT + len(registered), holding_period_sessions=20
            )
        placebo = family_placebo(matrix, seed=184, block=20)
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
        ):
            raise ValueError("protected source or runtime changed")
        survivors = [m for m in MECHANISMS if all(all(v.values()) for v in checks[m].values())]
        bindings = {p["identity"]: registry.fit_lineage(tids[p["identity"]]) for p in registered}
        write_json(output / "NATIVE_FIT_LINEAGE.json", bindings)
        result = {
            "version": VERSION,
            "issue": 184,
            "spec": spec,
            "models": models,
            "records": records,
            "checks": checks,
            "target_diagnostics": target_diagnostics,
            "statistics": stats,
            "placebo": placebo,
            "distinct_nonzero_active_paths": distinct,
            "statistical_scope": "reused_history_adaptive_return_matrix_diagnostic;NOT_nested_refit_CPCV_or_full_history_DSR",
            "reserved_new_trials": len(registered),
            "completed_new_trials": completed,
            "raw_global_trial_lower_bound": DEBT + len(registered),
            "restricted_rows_read": 0,
            "native_fit_lineage_sha256": file_sha(output / "NATIVE_FIT_LINEAGE.json"),
            "engineering_pass": all(
                r["audit"]["pass"] for costs in records.values() for r in costs.values()
            ),
            "protected_unchanged": True,
            "validated_alpha": False,
            "survivors": survivors,
            "decision": "FREEZE_TEMPORAL_HISTORICAL_LEAD"
            if survivors
            else "NO_TEMPORAL_LEAD_CONTINUE_RESEARCH",
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps(
                {k: result[k] for k in ("decision", "survivors", "raw_global_trial_lower_bound")}
            ),
            flush=True,
        )
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {"error_type": type(exc).__name__, "error": str(exc), "reservations_preserved": True},
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
