"""A single registered residual-mechanism epoch. Reused history, no Alpha promotion."""

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
from stephen_quant.discovery.residual_mechanisms import (
    MECHANISMS,
    POLICIES,
    VERSION,
    contract,
    fit_year,
    plans,
    targets_for,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
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

PARENT_SHA = "a201826b127d02a7f4ab165047131a8fc681d02ec8ae45a18c0163196a19a8ef"
CLAIM_ROOT = Path(__file__).resolve().parents[3] / "artifacts" / "residual-mechanisms" / "claims"


def verify_lineage(config):
    old, frozen_file, frozen, _, _, inputs = verify_parent(config)
    parent = Path(config["deep_parent_dir"]).resolve()
    if file_sha(parent / "RESULT.json") != PARENT_SHA:
        raise ValueError("deep parent hash mismatch")
    previous = json.loads((parent / "RESULT.json").read_text(encoding="utf-8"))
    if not previous["engineering_pass"] or previous["raw_global_trial_lower_bound"] != 3268:
        raise ValueError("parent engineering and trial debt required")
    if not json.loads((parent / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))["pass"]:
        raise ValueError("parent independent audit required")
    protected = [frozen_file, *config["protected_paths"]]
    for p in (old, parent, Path(config["calendar_parent_dir"]).resolve()):
        protected.extend(
            p / n for n in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json")
        )
    return inputs, frozen, protected, (old, parent, Path(config["calendar_parent_dir"]).resolve())


def economic_checks(candidate, lowvol, risk_hash):
    return {
        "both_years_positive": all(candidate["years"][y] > 0 for y in ("2023", "2024")),
        "sharpe": candidate["pooled_sharpe"] >= 0.7,
        "drawdown": candidate["metrics"]["max_drawdown"] >= -0.25,
        "lowvol_increment": candidate["metrics"]["net_total_return"]
        - lowvol["metrics"]["net_total_return"]
        >= 0.03,
        "risk_hash_increment": candidate["metrics"]["net_total_return"]
        - risk_hash["metrics"]["net_total_return"]
        >= 0.03,
        "annual_increment": all(
            candidate["years"][y] - lowvol["years"][y] >= -0.05 for y in ("2023", "2024")
        ),
        "account": candidate["audit"]["pass"],
    }


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
        "raw_debt_before": 3268,
        "reserved_new_trials": len(registered),
        "preregistration_comment": config["preregistration_comment"],
        "exposure": "reused2022-2024;2023and2024development;no2025/2026",
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
                "residual_mechanisms",
                "incremental predictive information after train-only risk controls",
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        tids = {
            p["identity"]: registry.create_trial_deterministic(
                TrialSpec(
                    eid,
                    p["policy"],
                    p["identity"],
                    json.dumps(p),
                    184,
                    "2022-01-01",
                    "2022-12-31",
                    "2023-01-01",
                    "2023-12-31",
                    "2024-01-01",
                    "2024-12-31",
                ),
                p["identity"],
            )[0]
            for p in registered
        }
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        window = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any(sum(d.date.startswith(y) for d in window) < 200 for y in ("2023", "2024")):
            raise ValueError("incomplete development years")
        models, cache = {}, {}
        completed = 0
        for year in (2023, 2024):
            models[year] = fit_year(days, year, cache)
            write_json(output / "models" / f"{year}.json", models[year])
            for p in registered:
                if p["kind"] == "fit" and p["year"] == year:
                    registry.record_trial_result(
                        tids[p["identity"]],
                        json.dumps(models[year]["models"][p["policy"]], sort_keys=True),
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
            targets, diagnostics = targets_for(window, models, policy, cache)
            target_diagnostics[policy] = diagnostics
            write_json(output / "targets" / (policy + ".json"), [asdict(t) for t in targets])
            records[policy] = {}
            for cost in (41, 82, 102):
                config_exec = StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=3 if cost == 41 else 6,
                    sell_tax_bps=5 if cost == 41 else 10,
                    slippage_bps=15 if cost == 41 else 30 if cost == 82 else 40,
                )
                report = run_stateful_execution(
                    tuple(d.bars for d in window), targets, config_exec, initial_nav=3_000_000
                )
                summary = account_summary(report)
                summary.update(
                    audit=audit_account(report),
                    account_sha256=save_account(output, f"{policy}-{cost}", report),
                    targets_sha256=sha256_json([asdict(t) for t in targets]),
                )
                records[policy][str(cost)] = summary
                p = next(
                    p
                    for p in registered
                    if p["kind"] == "account" and p["policy"] == policy and p["cost_bps"] == cost
                )
                registry.record_trial_result(
                    tids[p["identity"]], json.dumps(summary, sort_keys=True)
                )
                completed += 1
            write_json(output / "policies" / (policy + ".json"), records[policy])
            print(json.dumps({"policy": policy, "completed": completed}), flush=True)
        checks = {
            m: {
                c: economic_checks(records[m][c], records["lowvol"][c], records["risk_hash"][c])
                for c in ("82", "102")
            }
            for m in MECHANISMS
        }
        matrix = {
            m: [
                a - b
                for a, b in zip(
                    records[m]["82"]["daily_returns"],
                    records["risk_hash"]["82"]["daily_returns"],
                    strict=True,
                )
            ]
            for m in MECHANISMS
        }
        try:
            stats = temporal_selection(
                [d.date for d in window], matrix, 3289, holding_period_sessions=20
            )
        except ValueError as exc:
            stats = {"status": "NOT_IDENTIFIABLE", "reason": str(exc)}
        placebo = family_placebo(matrix, seed=184, block=20)
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
        ):
            raise ValueError("protected source or runtime changed")
        survivors = [m for m in MECHANISMS if all(all(v.values()) for v in checks[m].values())]
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
            "statistical_scope": "diagnostic selection of adaptive walk-forward returns;NOT nested refit CPCV;NOT full-history DSR",
            "reserved_new_trials": 21,
            "completed_new_trials": completed,
            "raw_global_trial_lower_bound": 3289,
            "restricted_rows_read": 0,
            "engineering_pass": True,
            "protected_unchanged": True,
            "validated_alpha": False,
            "survivors": survivors,
            "decision": "FREEZE_HISTORICAL_RESIDUAL_LEAD"
            if survivors
            else "NO_RESIDUAL_LEAD_CONTINUE_RESEARCH",
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
