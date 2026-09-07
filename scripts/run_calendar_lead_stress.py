"""One frozen-staggered-lead stress operation, registered before market reads."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.baseline.stateful import StatefulExecutionConfig, run_stateful_execution
from stephen_quant.discovery.calendar_robustness import account_summary, calendar_targets
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.lead_challenge import (
    CHALLENGES,
    delayed_targets,
    lowvol_attribution,
    tail_sensitivity,
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
from stephen_quant.workflows.v117_incremental_epoch import inventory, save_account
from stephen_quant.workflows.v118_lead_challenge import verify_parent

PARENT_SHA = "9fc73f90b3118caaefb93772a27edaf77e3ec7bf08e68b9ffdb2b5aade70b84a"
CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "calendar-lead-stress" / "claims"
SCENARIOS = CHALLENGES[1:5]


def run(config_path, parent_dir, output_dir):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    old_dir, frozen_file, frozen, _, pack, inputs = verify_parent(config)
    parent, output = Path(parent_dir).resolve(), Path(output_dir).resolve()
    if file_sha(parent / "RESULT.json") != PARENT_SHA:
        raise ValueError("frozen calendar parent changed")
    previous = json.loads((parent / "RESULT.json").read_text(encoding="utf-8"))
    if (
        previous["survivors"] != [pack[0].name]
        or not previous["engineering_pass"]
        or previous["raw_global_trial_lower_bound"] != 3256
        or previous["spec"]["runtime_code_sha256"] != runtime_code_hash()
    ):
        raise ValueError("requires frozen staggered lead, runtime and complete debt")
    if any(
        output == p or p in output.parents or output in p.parents for p in (inputs, old_dir, parent)
    ):
        raise ValueError("output must be independent")
    if output.exists():
        raise FileExistsError("operation already exists")
    h = pack[0]
    items = inventory((h,))
    plans = [
        {
            "scenario": asdict(c),
            "item": i,
            "identity": sha256_json(
                {
                    "scenario": asdict(c),
                    "item": i["identity"],
                    "calendar": "staggered_four",
                    "parent": PARENT_SHA,
                }
            ),
        }
        for c in SCENARIOS
        for i in items
    ]
    protected = [
        frozen_file,
        parent / "RESULT.json",
        parent / "registry.sqlite3",
        parent / "first_read_reservations.json",
        parent / "FROZEN_LEADS.json",
        *config["protected_paths"],
    ]
    before, _ = protected_digest(protected)
    spec = {
        "version": "11.9.0-deep",
        "issue": 184,
        "preregistration_comment": 5559458886,
        "source_result_sha256": PARENT_SHA,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "snapshot_sha256": frozen["snapshot_sha256"],
        "calendar": "staggered_four",
        "scenarios": [asdict(c) for c in SCENARIOS],
        "hypothesis": asdict(h),
        "raw_debt_before": 3256,
        "reserved_new_trials": len(plans),
        "protected_before": before,
        "exposure": "historical2023-2024;notindependent;no2025/2026",
        "diagnostics": {"hac_lag": 20, "tail_days": 5},
    }
    write_json(
        CLAIM_ROOT / (PARENT_SHA + ".json"),
        {"output": str(output), "spec_sha256": sha256_json(spec), "reserved_trials": 12},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "trials": plans,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
        },
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": frozen["snapshot_sha256"]}),
            vendor_version=spec["version"],
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "staggered_lead_stress",
                "falsify frozen calendar-robust lead",
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
                    p["item"]["name"],
                    p["item"]["identity"],
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
            for p in plans
        }
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        days = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any(sum(d.date.startswith(y) for d in days) < 200 for y in ("2023", "2024")):
            raise ValueError("incomplete development years")
        targets, cache = {}, {}
        for i in items:
            targets[i["name"]] = calendar_targets(days, h, i["kind"], "staggered_four", cache)[0]
        records, stress_checks, diagnostics = {}, {}, {}
        for c in SCENARIOS:
            records[c.name] = {}
            sessions = tuple(
                tuple(replace(b, capacity_cny=b.capacity_cny * c.capacity_fraction) for b in d.bars)
                for d in days
            )
            for i in items:
                t = delayed_targets(targets[i["name"]], c.delay_sessions)
                report = run_stateful_execution(
                    sessions,
                    t,
                    StatefulExecutionConfig(
                        maximum_position_weight=0.025,
                        commission_bps=6,
                        sell_tax_bps=10,
                        slippage_bps=30 + c.extra_slippage_bps,
                    ),
                    initial_nav=3_000_000,
                )
                summary = account_summary(report)
                summary.update(
                    audit=audit_account(report),
                    account_sha256=save_account(output, f"{c.name}-{i['name']}-2", report),
                    targets_sha256=sha256_json([asdict(row) for row in t]),
                )
                records[c.name][i["name"]] = {"2": summary}
                plan = next(
                    p
                    for p in plans
                    if p["scenario"]["name"] == c.name and p["item"]["name"] == i["name"]
                )
                registry.record_trial_result(
                    tids[plan["identity"]], json.dumps(summary, sort_keys=True)
                )
            candidate = records[c.name][h.name]["2"]
            base = records[c.name][f"lowvol_{h.field}_h20"]["2"]
            hashed = records[c.name][f"hash_{h.field}_h20"]["2"]
            stress_checks[c.name] = {
                "positive_both_years": all(v > 0 for v in candidate["years"].values()),
                "continuous_drawdown": candidate["metrics"]["max_drawdown"] >= -0.25,
                "sharpe": candidate["pooled_sharpe"] >= 0.7,
                "lowvol_increment": candidate["metrics"]["net_total_return"]
                - base["metrics"]["net_total_return"]
                >= 0.03,
                "annual_increment": all(
                    candidate["years"][y] - base["years"][y] >= -0.05 for y in ("2023", "2024")
                ),
                "hash_increment": candidate["metrics"]["net_total_return"]
                > hashed["metrics"]["net_total_return"],
            }
            diagnostics[c.name] = {
                "lowvol_attribution": lowvol_attribution(
                    candidate["daily_returns"], base["daily_returns"], lag=20
                ),
                "tail": tail_sensitivity(candidate["daily_returns"], base["daily_returns"], top=5),
            }
            write_json(
                output / "scenarios" / (c.name + ".json"),
                {
                    "records": records[c.name],
                    "checks": stress_checks[c.name],
                    "diagnostics": diagnostics[c.name],
                },
            )
            print(json.dumps({"scenario": c.name, "checks": stress_checks[c.name]}), flush=True)
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("frozen runtime or evidence changed")
        survived = all(all(checks.values()) for checks in stress_checks.values())
        result = {
            "version": spec["version"],
            "issue": 184,
            "spec": spec,
            "records": records,
            "stress_checks": stress_checks,
            "diagnostics": diagnostics,
            "assessments": {},
            "decomposition": {},
            "survivors": [h.name] if survived else [],
            "validated_alpha": False,
            "engineering_pass": True,
            "restricted_rows_read": 0,
            "protected_unchanged": True,
            "reserved_new_trials": 12,
            "completed_new_trials": 12,
            "raw_global_trial_lower_bound": 3268,
            "statistics": previous["statistics"],
            "placebo": previous["placebo"],
            "statistical_scope": "parent12-calendar family at3256 trials;NOT a certificate or recomputed expanded-family test",
            "decision": "EXECUTION_SOURCE_AUDIT_REQUIRED"
            if survived
            else "COST_FRAGILE_OBSERVATION_ONLY_CONTINUE_MECHANISMS",
        }
        write_json(output / "RESULT.json", result)
        print(json.dumps({"decision": result["decision"], "trial_lower_bound": 3268}), flush=True)
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
    parser.add_argument("--parent", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.config, args.parent, args.output)
