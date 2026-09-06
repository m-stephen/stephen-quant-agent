"""Registered execution-only falsification of the frozen V11.11 allocation lead."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.lead_challenge import (
    Challenge,
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
from stephen_quant.workflows.v117_incremental_epoch import save_account
from stephen_quant.workflows.v1111_temporal_epoch import verify_lineage

PARENT_SHA = "858f7b70436feaf146f9e807e1889a1a6e4756e3e8e433a7e6f1cf50e7fb6021"
CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts/stability-challenge/claims"
CARD = Path("configs/v11.11-frozen-stability-observation.json")
SCENARIOS = (
    Challenge("baseline_82"),
    Challenge("cost_102", extra_slippage_bps=10),
    Challenge("cost_132", extra_slippage_bps=25),
    Challenge("quarter_capacity", capacity_fraction=0.25),
    Challenge("delay_one", delay_sessions=1),
)
POLICIES = ("stable_lowrisk", "lowvol")


def screen(a, b):
    return {
        "account": a["audit"]["pass"] and b["audit"]["pass"],
        "both_years_positive": all(a["years"][y] > 0 for y in ("2023", "2024")),
        "sharpe": a["pooled_sharpe"] >= 0.7,
        "drawdown": a["metrics"]["max_drawdown"] >= -0.25,
        "increment": a["metrics"]["net_total_return"] - b["metrics"]["net_total_return"] >= 0.03,
        "annual_increment": all(a["years"][y] - b["years"][y] >= -0.05 for y in ("2023", "2024")),
    }


def run(config_path, parent_dir, output_dir, preregistration):
    if type(preregistration) is not int or preregistration <= 0:
        raise ValueError("preregistration comment required")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    inputs, frozen, protected, ancestors = verify_lineage(config)
    parent, output = Path(parent_dir).resolve(), Path(output_dir).resolve()
    card = json.loads(CARD.read_text(encoding="utf-8"))
    previous = json.loads((parent / "RESULT.json").read_text(encoding="utf-8"))
    if (
        file_sha(parent / "RESULT.json") != PARENT_SHA
        or card["source_result_sha256"] != PARENT_SHA
        or previous["raw_global_trial_lower_bound"] != 3310
        or not previous["engineering_pass"]
        or card["runtime_code_sha256"] != runtime_code_hash()
        or card["snapshot_sha256"] != frozen["snapshot_sha256"]
        or not json.loads((parent / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))["pass"]
    ):
        raise ValueError("frozen parent/card/runtime/debt mismatch")
    if any(
        output == p or p in output.parents or output in p.parents
        for p in (inputs, parent, *ancestors)
    ):
        raise ValueError("independent output required")
    if output.exists():
        raise FileExistsError("operation exists; never replay")
    protected = [
        *protected,
        CARD,
        *(
            parent / n
            for n in (
                "RESULT.json",
                "registry.sqlite3",
                "first_read_reservations.json",
                "NATIVE_FIT_LINEAGE.json",
            )
        ),
        *(parent / "targets" / (p + ".json") for p in POLICIES),
    ]
    before, _ = protected_digest(protected)
    plans = [
        {
            "scenario": asdict(c),
            "policy": p,
            "identity": sha256_json(
                {
                    "scenario": asdict(c),
                    "policy": p,
                    "parent": PARENT_SHA,
                    "version": "11.11.0-deep",
                }
            ),
        }
        for c in SCENARIOS
        for p in POLICIES
    ]
    spec = {
        "version": "11.11.0-deep",
        "issue": 184,
        "preregistration_comment": preregistration,
        "source_result_sha256": PARENT_SHA,
        "card_sha256": file_sha(CARD),
        "snapshot_sha256": frozen["snapshot_sha256"],
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "raw_debt_before": 3310,
        "reserved_new_trials": 10,
        "scenarios": [asdict(c) for c in SCENARIOS],
        "screen": "ALL scenarios: each year>0,SR>=.7,MDD>=-.25,total delta>=.03,each year delta>=-.05",
        "diagnostics": {
            "hac_lag": 20,
            "top_positive_active_days": 5,
            "interpretation": "descriptive not selection-adjusted; no trading rule",
        },
        "exposure": "reused2023-2024; no2025/2026; allocation chosen after observed return",
        "protected_before": before,
        "validated_alpha": False,
    }
    write_json(
        CLAIM_ROOT / (PARENT_SHA + ".json"),
        {"output": str(output), "spec_sha256": sha256_json(spec), "reserved_trials": 10},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "trials": plans,
            "spec_sha256": sha256_json(spec),
            "created_at": datetime.now(timezone.utc).isoformat(),
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
                "stability_challenge",
                "falsify frozen stable allocation",
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
                    "unused",
                    "unused",
                    "2023-01-01",
                    "2024-12-31",
                    "unused",
                    "unused",
                    fit_stages=(),
                ),
                p["identity"],
            )[0]
            for p in plans
        }
        targets = {}
        for policy in POLICIES:
            path = parent / "targets" / (policy + ".json")
            if file_sha(path) != card["targets_file_sha256"][policy]:
                raise ValueError("frozen target bytes changed")
            saved = json.loads(path.read_text(encoding="utf-8"))
            if sha256_json(saved) != card["targets_canonical_sha256"][policy]:
                raise ValueError("frozen target semantics changed")
            targets[policy] = tuple(
                TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in saved
            )
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        window = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any([d.date for d in window] != [t.trade_date for t in targets[p]] for p in POLICIES):
            raise ValueError("frozen target calendar mismatch")
        records, checks, diagnostics, completed = {}, {}, {}, 0
        for c in SCENARIOS:
            records[c.name] = {}
            sessions = tuple(
                tuple(replace(b, capacity_cny=b.capacity_cny * c.capacity_fraction) for b in d.bars)
                for d in window
            )
            for policy in POLICIES:
                plan = next(
                    p for p in plans if p["scenario"]["name"] == c.name and p["policy"] == policy
                )
                tid = tids[plan["identity"]]
                if registry.fit_lineage(tid) != {
                    "stages": [],
                    "fits": [],
                    "sha256": sha256_json([]),
                }:
                    raise ValueError("explicit unfitted contract required")
                ts = delayed_targets(targets[policy], c.delay_sessions)
                write_json(output / "targets" / f"{c.name}-{policy}.json", [asdict(t) for t in ts])
                report = run_stateful_execution(
                    sessions,
                    ts,
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
                    account_sha256=save_account(output, f"{c.name}-{policy}", report),
                    targets_sha256=sha256_json([asdict(t) for t in ts]),
                    fit_lineage_sha256=registry.fit_lineage(tid)["sha256"],
                )
                if c.name in ("baseline_82", "cost_102"):
                    cost = "82" if c.name == "baseline_82" else "102"
                    if (
                        summary["account_sha256"]
                        != previous["records"][policy][cost]["account_sha256"]
                    ):
                        raise ValueError("unchanged policy failed exact parent replay")
                records[c.name][policy] = summary
                registry.record_trial_result(tid, json.dumps(summary, sort_keys=True))
                completed += 1
            a, b = records[c.name]["stable_lowrisk"], records[c.name]["lowvol"]
            checks[c.name] = screen(a, b)
            diagnostics[c.name] = {
                "lowvol_attribution": lowvol_attribution(
                    a["daily_returns"], b["daily_returns"], lag=20
                ),
                "tail": tail_sensitivity(a["daily_returns"], b["daily_returns"], top=5),
                "fee_saving_cny": b["metrics"]["total_cost"] - a["metrics"]["total_cost"],
                "net_pnl_difference_cny": a["metrics"]["final_nav"] - b["metrics"]["final_nav"],
                "attribution_limit": "cash accounting only; not a zero-fee counterfactual or causal decomposition",
            }
            write_json(
                output / "scenarios" / (c.name + ".json"),
                {
                    "records": records[c.name],
                    "checks": checks[c.name],
                    "diagnostics": diagnostics[c.name],
                },
            )
            print(
                json.dumps({"scenario": c.name, "completed": completed, "checks": checks[c.name]}),
                flush=True,
            )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("frozen runtime/evidence changed")
        survived = all(all(v.values()) for v in checks.values())
        result = {
            "version": spec["version"],
            "spec": spec,
            "records": records,
            "checks": checks,
            "diagnostics": diagnostics,
            "reserved_new_trials": 10,
            "completed_new_trials": completed,
            "raw_global_trial_lower_bound": 3320,
            "restricted_rows_read": 0,
            "protected_unchanged": True,
            "engineering_pass": all(v["account"] for v in checks.values()),
            "validated_alpha": False,
            "decision": "ALLOCATION_OBSERVATION_REQUIRES_INDEPENDENT_EXECUTION_AND_STYLE_EVIDENCE"
            if survived
            else "ALLOCATION_STRESS_FAILED_CONTINUE_BOUNDED_MECHANISMS",
            "stress_survived": survived,
            "statistics": {
                "status": "NOT_IDENTIFIABLE",
                "reason": "one post-selected allocation; no full-history independent Court",
            },
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps({"decision": result["decision"], "raw_trial_lower_bound": 3320}), flush=True
        )
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {"error_type": type(exc).__name__, "error": str(exc), "reservations_preserved": True},
        )
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--parent", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--preregistration", type=int, required=True)
    args = p.parse_args()
    run(args.config, args.parent, args.output, args.preregistration)
