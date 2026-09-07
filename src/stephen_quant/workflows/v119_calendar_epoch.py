"""One bounded, preregistered calendar challenge; immutable source lineage."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.discovery.calendar_robustness import (
    CALENDARS,
    VERSION,
    account_summary,
    assess_calendars,
    calendar_targets,
)
from stephen_quant.discovery.incremental_alpha import IncrementalHypothesis, audit_account, execute
from stephen_quant.discovery.reliability_calibration import family_placebo
from stephen_quant.discovery.reliable_research import compound, temporal_selection
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

CLAIM_ROOT = Path(__file__).resolve().parents[3] / "artifacts" / "calendar-challenge" / "claims"
CHALLENGE_SHA = "811af6aa3b2318d1d63d1b9f1e22e806b50ca9190f6a596606cff916037e1510"
SUCCESSOR_SHA = "a449ad26193ecd0aadac9d281bbf2469a9b8e6cb1c4d7b490a68c2ac9f28d1fa"


def plans_for(pack):
    return [
        {
            "item": item,
            "calendar": calendar,
            "cost": cost,
            "identity": sha256_json(
                {"item": item["identity"], "calendar": calendar, "cost": cost, "version": VERSION}
            ),
        }
        for calendar in CALENDARS
        for item in inventory(pack)
        for cost in (1, 2)
    ]


def verify_predecessor(config):
    challenge = Path(config["challenge_dir"]).resolve()
    successor = Path(config["successor_dir"]).resolve()
    if (
        file_sha(challenge / "RESULT.json") != CHALLENGE_SHA
        or file_sha(successor / "RESULT.json") != SUCCESSOR_SHA
    ):
        raise ValueError("predecessor result hash mismatch")
    previous = json.loads((successor / "RESULT.json").read_text(encoding="utf-8"))
    if (
        not previous["engineering_pass"]
        or previous["decision"] != "NO_LEAD_CONTINUE_RESEARCH"
        or previous["raw_global_trial_lower_bound"] != 3184
        or previous["spec"]["source_result_sha256"] != CHALLENGE_SHA
    ):
        raise ValueError("complete predecessor evidence and debt required")
    return challenge, successor, previous


def run(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    parent, frozen_file, frozen, old, pack, inputs = verify_parent(config)
    challenge, successor, _previous = verify_predecessor(config)
    output = Path(config["output_dir"]).resolve()
    roots = (parent, inputs, challenge, successor)
    if any(output == p or p in output.parents or output in p.parents for p in roots):
        raise ValueError("output must be independent of every source/parent")
    if output.exists():
        raise FileExistsError("operation exists; inspect instead of replaying")
    plans = plans_for(pack)
    protected = [frozen_file, *map(Path, config["protected_paths"])]
    for folder in (parent, challenge, successor):
        protected.extend(
            folder / f for f in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json")
        )
    before, _ = protected_digest(protected)
    spec = {
        "version": VERSION,
        "issue": 184,
        "preregistration_comment": 5559351596,
        "pack": [asdict(h) for h in pack],
        "calendars": list(CALENDARS),
        "cost_multipliers": [1, 2],
        "raw_debt_before": 3184,
        "reserved_new_trials": len(plans),
        "prior_result_sha256": file_sha(successor / "RESULT.json"),
        "snapshot_sha256": frozen["snapshot_sha256"],
        "runtime_code_sha256": runtime_code_hash(),
        "protected_before": before,
        "exposure": "reused2023-2024;no2025/2026",
        "calendar_contract": "four fixed phases;ONE netted target-mixture account;cash during ramp-up;no phase optimization",
        "validated_alpha": False,
    }
    write_json(
        CLAIM_ROOT / (SUCCESSOR_SHA + ".json"),
        {
            "output": str(output),
            "spec_sha256": sha256_json(spec),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reserved_trials": len(plans),
        },
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
            "trials": plans,
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
                "continuous_calendar_robustness",
                "challenge calendar luck without choosing best phase",
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
        window = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any(sum(d.date.startswith(y) for d in window) < 200 for y in ("2023", "2024")):
            raise ValueError("incomplete calendar years")
        challenge_result = json.loads((challenge / "RESULT.json").read_text(encoding="utf-8"))
        records, cache, count = {}, {}, 0
        for calendar in CALENDARS:
            records[calendar] = {}
            for item in inventory(pack):
                h = IncrementalHypothesis(**item["hypothesis"])
                targets, coverage = calendar_targets(window, h, item["kind"], calendar, cache)
                if not coverage or not any(c["selected"] for c in coverage):
                    raise ValueError("empty calendar coverage")
                records[calendar][item["name"]] = {}
                for cost in (1, 2):
                    report = execute(window, targets, cost)
                    label = f"{calendar}-{item['name']}-{cost}"
                    summary = account_summary(report)
                    summary.update(
                        audit=audit_account(report),
                        account_sha256=save_account(output, label, report),
                        targets_sha256=sha256_json([asdict(t) for t in targets]),
                    )
                    records[calendar][item["name"]][str(cost)] = summary
                    if calendar == "phase_0" and cost == 2:
                        prior = challenge_result["records"][
                            f"continuous_82-continuous2023-2024-{item['name']}"
                        ]
                        if any(
                            summary[k] != prior[k] for k in ("account_sha256", "targets_sha256")
                        ):
                            raise ValueError("frozen continuous baseline changed")
                    p = next(
                        p
                        for p in plans
                        if p["calendar"] == calendar
                        and p["item"]["name"] == item["name"]
                        and p["cost"] == cost
                    )
                    registry.record_trial_result(
                        tids[p["identity"]], json.dumps(summary, sort_keys=True)
                    )
                    count += 1
                print(
                    json.dumps({"calendar": calendar, "policy": item["name"], "accounts": count}),
                    flush=True,
                )
            write_json(output / "calendars" / (calendar + ".json"), records[calendar])
        assessments, decomposition, matrix = {}, {}, {}
        original = {r["name"]: r for r in old["batches"][0]["candidates"]}
        for h in pack:
            family = {
                c: {
                    kind: records[c][h.name if kind == "candidate" else f"{kind}_{h.field}_h20"][
                        "2"
                    ]
                    for kind in ("candidate", "lowvol", "hash")
                }
                for c in CALENDARS
            }
            assessments[h.name] = assess_calendars(family)
            for c, rows in family.items():
                matrix[h.name + ":" + c] = [
                    a - b
                    for a, b in zip(
                        rows["candidate"]["daily_returns"],
                        rows["lowvol"]["daily_returns"],
                        strict=True,
                    )
                ]
            annual = compound(
                [original[h.name]["years"][y]["2"]["absolute_return"] for y in ("2023", "2024")]
            )
            reset_calendar = family["annual_calendar"]["candidate"]["metrics"]["net_total_return"]
            continuous = family["phase_0"]["candidate"]["metrics"]["net_total_return"]
            decomposition[h.name] = {
                "annual_reset_linked_return": annual,
                "continuous_annual_calendar_return": reset_calendar,
                "continuous_phase0_return": continuous,
                "account_reset_difference_pp": 100 * (annual - reset_calendar),
                "calendar_difference_pp": 100 * (reset_calendar - continuous),
                "total_difference_pp": 100 * (annual - continuous),
                "status": "DESCRIPTIVE_ORDER_DEPENDENT_NOT_CAUSAL",
            }
        try:
            stats = temporal_selection(
                [d.date for d in window], matrix, 3184 + len(plans), holding_period_sessions=20
            )
        except ValueError as exc:
            stats = {"status": "NOT_IDENTIFIABLE", "reason": str(exc)}
        placebo = family_placebo(matrix, seed=184, block=20)
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
        ):
            raise ValueError("runtime or protected evidence changed")
        survivors = [h for h, a in assessments.items() if a["historical_robust_lead"]]
        final = {
            "version": VERSION,
            "issue": 184,
            "spec": spec,
            "records": records,
            "assessments": assessments,
            "decomposition": decomposition,
            "statistics": stats,
            "placebo": placebo,
            "raw_global_trial_lower_bound": 3184 + len(plans),
            "reserved_new_trials": len(plans),
            "completed_new_trials": count,
            "engineering_pass": True,
            "restricted_rows_read": 0,
            "protected_unchanged": True,
            "validated_alpha": False,
            "survivors": survivors,
            "decision": "FREEZE_STAGGERED_LEAD_FOR_EXECUTION_AUDIT"
            if survivors
            else "NO_ROBUST_LEAD_CONTINUE_RESEARCH",
        }
        if survivors:
            write_json(
                output / "FROZEN_LEADS.json",
                {
                    "survivors": survivors,
                    "spec_sha256": sha256_json(spec),
                    "calendar": "staggered_four",
                    "validated_alpha": False,
                },
            )
        write_json(output / "RESULT.json", final)
        print(
            json.dumps(
                {k: final[k] for k in ("decision", "survivors", "raw_global_trial_lower_bound")}
            ),
            flush=True,
        )
        return final
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
