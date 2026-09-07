"""Exclusive twelve-target zero-cost replay; all paid accounts remain immutable."""

import argparse
import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from audit_pairwise_ranking import native_check
from run_sparse_events import CARD_SHA, SNAPSHOT_SHA, read

from stephen_quant.baseline.stateful import run_stateful_execution
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.gross_net_attribution import (
    BASES,
    DEBT,
    KINDS,
    VERSION,
    attribution,
    execution_config,
    execution_summary,
    frozen_targets,
    plans,
)
from stephen_quant.discovery.incremental_alpha import audit_account
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

PARENT_SHA = "319dcb2dd2e85aa208424c70f4e8e2c2160657f44ab1fae480f3c0a1355c7337"
AUDIT_SHA = "d35a0c906b28e0704c9c7d43df55e9139f0445ace309a1605a78cef3ec2626f7"
CLAIMS = Path(__file__).resolve().parents[1] / "artifacts/gross-net/claims"


def reserve(output, spec):
    registry = ExperimentRegistry(output / "registry.sqlite3")
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
    )
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            "gross_net",
            "frozen-policy cost-path diagnosis",
            sid,
            spec["runtime_code_sha256"],
            json.dumps(spec),
        ),
        sha256_json(spec),
    )
    tids = {
        p["key"]: registry.create_trial_deterministic(
            TrialSpec(
                eid,
                p["key"],
                sha256_json(p),
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
            sha256_json(p),
        )[0]
        for p in spec["plans"]
    }
    if registry.global_trial_count() != 12:
        raise ValueError("all12 native reservations required before numerical read")
    for tid in tids.values():
        if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
            raise ValueError("replay must have explicit no-new-fit contract")
    return registry, tids


def inherited_receipt(parent, result):
    """Validate original fits without invoking a model fit or computing predictions."""
    models = {}
    for b in BASES:
        for k in KINDS:
            tk = f"{b}-{k}"
            models[tk] = {}
            for year in (2023, 2024):
                path = parent / f"models/{tk}-{year}.json"
                if file_sha(path) != result["models_sha256"][f"{tk}-{year}"]:
                    raise ValueError("inherited model bytes changed")
                models[tk][year] = read(path)
    native_check(parent, result, models)
    return {
        "operation_kind": "frozen_target_replay",
        "new_fits": 0,
        "inherited_models": 16,
        "inherited_fit_receipts": 32,
        "parent_result_sha256": PARENT_SHA,
        "parent_registry_sha256": file_sha(parent / "registry.sqlite3"),
        "models_sha256": result["models_sha256"],
        "lineages": {k: r["fit_lineage_sha256"] for k, r in result["records"].items()},
    }


def check_output(output, roots):
    if output.exists():
        raise FileExistsError("operation already exists; no replay retry")
    if any(output == p or output in p.parents or p in output.parents for p in roots):
        raise ValueError("independent output required")


def run(config):
    cfg = read(config)
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("positive preregistration comment required")
    parent, original, inputs, output = [
        Path(cfg[k]).resolve() for k in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    check_output(output, (parent, original, inputs))
    runtime_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if cfg.get("runtime_commit") != runtime_commit:
        raise ValueError("frozen runtime commit required")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("clean committed runtime required")
    aborted = parent.parent / "epoch-001"
    if (
        file_sha(aborted / "ABORTED.json")
        != "3c254b86990b1bc801e58ace3bd8da30a079c162d9ee7bb718e67cf9409bb034"
    ):
        raise ValueError("original failed operation must remain intact")
    for p, digest in (
        (parent / "RESULT.json", PARENT_SHA),
        (parent / "INDEPENDENT_AUDIT.json", AUDIT_SHA),
        (original / "configs/v11.11-frozen-stability-observation.json", CARD_SHA),
    ):
        if file_sha(p) != digest:
            raise ValueError("frozen parent/audit/card mismatch")
    manifest = read(inputs / "manifest.json")
    if (
        manifest["snapshot_sha256"] != SNAPSHOT_SHA
        or sha256_json(manifest["sources"]) != SNAPSHOT_SHA
    ):
        raise ValueError("frozen snapshot mismatch")
    sources = []
    for s in manifest["sources"]:
        p = (inputs / s["file"]).resolve()
        if p.parent != inputs or s["max_date"] >= "2025-01-01" or file_sha(p) != s["sha256"]:
            raise ValueError("source boundary/hash mismatch")
        sources.append(p)
    # Hash-only inventory precedes reservations; no target/model/return decoding yet.
    protected = sorted(
        {
            *map(Path, [inputs / "manifest.json", *sources]),
            *(p for p in parent.rglob("*") if p.is_file()),
            *(p for p in (parent.parent / "epoch-001").rglob("*") if p.is_file()),
            original / "configs/v11.11-frozen-stability-observation.json",
            *(
                original / f"artifacts/temporal-increments/epoch-001/targets/{b}.json"
                for b in ("lowvol", "stable_lowrisk")
            ),
        }
    )
    protected_before, _ = protected_digest(protected)
    spec = {
        "version": VERSION,
        "plans": plans(),
        "reserved_trials": 12,
        "raw_debt_before": DEBT,
        "parent_sha256": PARENT_SHA,
        "parent_audit_sha256": AUDIT_SHA,
        "parent_dir": str(parent),
        "snapshot_sha256": SNAPSHOT_SHA,
        "runtime_commit": runtime_commit,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(__file__),
        "auditor_sha256": file_sha(Path(__file__).with_name("audit_gross_net_attribution.py")),
        "audit_query_sha256": file_sha(Path(__file__).with_name("gross_net_source_audit.sql")),
        "preregistration_comment": cfg["preregistration_comment"],
        "protected_before": protected_before,
        "protected_files": {str(p): file_sha(p) for p in protected},
        "execution_configs": {p["key"]: asdict(execution_config(p)) for p in plans()},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "interpretation": "diagnostic;no-promotion;no2025/26;zero-cost-is-counterfactual",
    }
    write_json(CLAIMS / f"{PARENT_SHA}.json", {"reserved": 12, "spec_sha256": sha256_json(spec)})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    records = {}
    try:
        registry, tids = reserve(output, spec)
        write_json(
            output / "first_read_reservations.json",
            {"trials": plans(), "spec_sha256": sha256_json(spec), "stage": "before_numerical_read"},
        )
        print(json.dumps({"reserved": 12, "debt": DEBT + 12}), flush=True)
        previous = read(parent / "RESULT.json")
        if previous["raw_global_trial_lower_bound"] != DEBT or previous["screen_survived"] != {
            "linear": False,
            "quadratic": False,
        }:
            raise ValueError("inherited debt/verdict mismatch")
        receipt = inherited_receipt(parent, previous)
        write_json(output / "inherited_lineage.json", receipt)
        days, quality = load_frozen_days(inputs)
        window = tuple(d for d in days if d.date >= "2023-01-01")
        calendar, sessions = [d.date for d in window], tuple(d.bars for d in window)
        if len(calendar) != 484 or any(d > "2024-12-31" for d in calendar):
            raise ValueError("fixed484-session development calendar required")
        del days, window
        write_json(output / "calendar.json", calendar)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        target_hashes = {}
        for p in plans():
            key, tk = p["key"], p["target_key"]
            source = parent / f"targets/{tk}.json"
            raw = read(source)
            target_hashes[tk] = previous["targets_sha256"][tk]
            targets = frozen_targets(raw, target_hashes[tk], calendar)
            dest = output / f"targets/{tk}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as f:
                f.write(source.read_bytes())
            report = run_stateful_execution(
                sessions, targets, execution_config(p), initial_nav=3_000_000
            )
            if report.metrics.total_cost != 0:
                raise ValueError("zero-cost configuration violated")
            row = {
                **account_summary(report),
                **p,
                "audit": audit_account(report),
                "account_sha256": save_account(output, key, report),
                "target_sha256": target_hashes[tk],
                "execution": execution_summary(report),
                "fit_lineage_sha256": registry.fit_lineage(tids[key])["sha256"],
                "inherited_receipt_sha256": file_sha(output / "inherited_lineage.json"),
            }
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            records[key] = row
            write_json(output / f"records/{key}.json", row)
            print(
                json.dumps({"completed": len(records), "key": key, "audit": row["audit"]["pass"]}),
                flush=True,
            )
        if (
            protected_digest(protected)[0] != protected_before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(__file__) != spec["driver_sha256"]
        ):
            raise ValueError("source/protected/runtime changed")
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "reference_records": previous["records"],
            "targets_sha256": target_hashes,
            "attribution": attribution({**previous["records"], **records}),
            "completed_trials": 12,
            "reserved_trials": 12,
            "raw_global_trial_lower_bound": DEBT + 12,
            "engineering_pass": all(r["audit"]["pass"] for r in records.values()),
            "protected_unchanged": True,
            "restricted_rows_read": 0,
            "validated_alpha": False,
            "screen_survived": previous["screen_survived"],
            "statistics": {"dsr": None, "pbo": None, "placebo": None, "status": "NOT_RUN"},
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps({"completed": 12, "debt": DEBT + 12, "validated_alpha": False}), flush=True
        )
    except Exception as error:
        write_json(
            output / "ABORTED.json",
            {
                "error_type": type(error).__name__,
                "completed": len(records),
                "raw_trial_debt": DEBT + 12,
                "reservations_preserved": True,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
