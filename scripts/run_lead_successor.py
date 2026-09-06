"""Issue184 preregistered low-turnover successor; never an autonomous trading loop."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.discovery.incremental_alpha import batches
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
from stephen_quant.workflows.v117_incremental_epoch import evaluate_batch, inventory
from stephen_quant.workflows.v118_lead_challenge import verify_parent

CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "lead-successor" / "claims"


def run(config_file, challenge_dir, output_dir):
    config = json.loads(Path(config_file).read_text(encoding="utf-8"))
    parent_dir, frozen_file, frozen, _, _, inputs = verify_parent(config)
    challenge_dir, output = Path(challenge_dir).resolve(), Path(output_dir).resolve()
    previous = json.loads((challenge_dir / "RESULT.json").read_text(encoding="utf-8"))
    if (
        previous["decision"] != "PREREGISTER_NEXT_BOUNDED_MECHANISM_EPOCH"
        or not previous["engineering_pass"]
        or previous["stress_survivors"]
    ):
        raise ValueError("successor requires completed engineering and failed stress screen")
    if previous["spec"]["leads_sha256"] != file_sha(frozen_file):
        raise ValueError("challenge lineage mismatch")
    if any(output == p or p in output.parents for p in (parent_dir, inputs, challenge_dir)):
        raise ValueError("successor output must be independent")
    if output.exists():
        raise FileExistsError("successor output already exists; inspect/resume, never rerun")
    # One auto-successor per completed challenge. A failure keeps this claim and
    # its reservations; manual resume must reconcile the existing operation.
    write_json(
        CLAIM_ROOT / (file_sha(challenge_dir / "RESULT.json") + ".json"),
        {
            "output": str(output),
            "parent_sha256": file_sha(challenge_dir / "RESULT.json"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    output.mkdir(parents=True, exist_ok=False)
    pack = batches()[1]
    items = inventory(pack)
    reservations = [
        {"identity": item["identity"], "cost": cost, "name": item["name"]}
        for item in items
        for cost in (0, 1, 2)
    ]
    protected = [
        frozen_file,
        parent_dir / "RESULT.json",
        parent_dir / "registry.sqlite3",
        challenge_dir / "RESULT.json",
        challenge_dir / "registry.sqlite3",
        challenge_dir / "first_read_reservations.json",
        *config["protected_paths"],
    ]
    before, _ = protected_digest(protected)
    debt = previous["raw_global_trial_lower_bound"]
    if debt < 3088:
        raise ValueError("full parent research debt required")
    spec = {
        "issue": 184,
        "version": "11.8.0-successor",
        "pack": [asdict(h) for h in pack],
        "raw_debt_before": debt,
        "reserved_new_trials": len(reservations),
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "source_result_sha256": file_sha(challenge_dir / "RESULT.json"),
        "snapshot_sha256": frozen["snapshot_sha256"],
        "protected_before": before,
        "old_unused_budget": "remains charged; successor newly registered conservatively",
        "exposure": "2023/2024 reused development;2025/2026 forbidden",
        "rationale": "test longer-horizon signal within low-volatility cohort and lower turnover",
        "stop": "one full16-candidate family; no adaptive formulas within this operation",
    }
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
            "trials": reservations,
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
                "conditional60_successor",
                spec["rationale"],
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        trial_ids = {}
        for item in items:
            for cost in (0, 1, 2):
                trial_ids[item["identity"], cost] = registry.create_trial_deterministic(
                    TrialSpec(
                        eid,
                        item["name"],
                        item["identity"],
                        json.dumps({"item": item, "cost": cost}),
                        184,
                        "2022-01-01",
                        "2022-12-31",
                        "2023-01-01",
                        "2023-12-31",
                        "2024-01-01",
                        "2024-12-31",
                    ),
                    f"{item['identity']}:{cost}",
                )[0]
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        result = evaluate_batch(
            days,
            pack,
            output / "batch-01",
            raw_trials=debt + len(reservations),
            registry=registry,
            trial_ids=trial_ids,
        )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("runtime or protected evidence changed")
        leads = [r for r in result["candidates"] if r["assessment"]["suspected_lead"]]
        if leads:
            write_json(
                output / "FROZEN_LEADS.json",
                {"leads": leads, "spec_sha256": sha256_json(spec), "validated_alpha": False},
            )
        final = {
            "version": spec["version"],
            "issue": 184,
            "spec": spec,
            "batches": [result],
            "engineering_pass": True,
            "validated_alpha": False,
            "protected_unchanged": True,
            "raw_global_trial_lower_bound": debt + len(reservations),
            "reserved_new_trials": len(reservations),
            "completed_new_trials": len(reservations),
            "restricted_rows_read": 0,
            "snapshot_sha256": frozen["snapshot_sha256"],
            "decision": "FROZEN_HISTORICAL_LEAD" if leads else "NO_LEAD_CONTINUE_RESEARCH",
        }
        write_json(output / "RESULT.json", final)
        print(
            json.dumps(
                {
                    "decision": final["decision"],
                    "leads": len(leads),
                    "trial_lower_bound": final["raw_global_trial_lower_bound"],
                }
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
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.config, args.challenge, args.output)
