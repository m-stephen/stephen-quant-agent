"""One exclusive preregistered cross-stock epoch; every account reserved first."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from run_sparse_events import ANCHOR_RESULT_SHA, CARD_SHA, SNAPSHOT_SHA, Evidence, read

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.peer_information import (
    VERSION,
    contract,
    fit_graph,
    peer_days,
    plans,
    prepared_signals,
    screen,
    stages,
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

PARENT_SHA = "c547a65d23578c30ff91ed7c84365ff057153c9c7ea163b657f02bc1bd30ef18"
CLAIMS = Path(__file__).resolve().parents[1] / "artifacts/peer-information/claims"


def run(config):
    cfg = read(config)
    parent, anchor_dir, original, inputs, output = [
        Path(cfg[k]).resolve()
        for k in ("parent_dir", "anchor_dir", "original_tree", "input_dir", "output_dir")
    ]
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("preregistration required")
    if output.exists() or any(
        output == p or output in p.parents or p in output.parents
        for p in (parent, anchor_dir, original, inputs)
    ):
        raise ValueError("new independent output required")
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    target_path = original / "artifacts/temporal-increments/epoch-001/targets/lowvol.json"
    if (
        file_sha(parent / "RESULT.json") != PARENT_SHA
        or read(parent / "RESULT.json")["raw_global_trial_lower_bound"] != 3506
        or not read(parent / "INDEPENDENT_AUDIT.json")["pass"]
        or file_sha(anchor_dir / "RESULT.json") != ANCHOR_RESULT_SHA
        or not read(anchor_dir / "INDEPENDENT_AUDIT.json")["pass"]
        or file_sha(card_path) != CARD_SHA
    ):
        raise ValueError("parent, debt or anchor mismatch")
    card, anchor_result = read(card_path), read(anchor_dir / "RESULT.json")
    if file_sha(target_path) != card["targets_file_sha256"]["lowvol"]:
        raise ValueError("original targets changed")
    manifest = read(inputs / "manifest.json")
    if (
        sha256_json(manifest["sources"]) != SNAPSHOT_SHA
        or manifest["snapshot_sha256"] != SNAPSHOT_SHA
    ):
        raise ValueError("snapshot mismatch")
    sources = []
    for s in manifest["sources"]:
        source = (inputs / s["file"]).resolve()
        if (
            source.parent != inputs
            or s["max_date"] >= "2025-01-01"
            or file_sha(source) != s["sha256"]
        ):
            raise ValueError("source bounds/hash mismatch")
        sources.append(source)
    protected = [
        parent / "RESULT.json",
        parent / "registry.sqlite3",
        card_path,
        target_path,
        inputs / "manifest.json",
        *sources,
        anchor_dir / "RESULT.json",
        anchor_dir / "registry.sqlite3",
        original / "artifacts/temporal-increments/epoch-001/targets/stable_lowrisk.json",
    ]
    before, _ = protected_digest(protected)
    planned = plans()
    spec = {
        "contract": contract(),
        "plans": planned,
        "parent_sha256": PARENT_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "preregistration_comment": cfg["preregistration_comment"],
        "protected_before": before,
        "protected_files": {str(p): file_sha(p) for p in protected},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(CLAIMS / f"{PARENT_SHA}.json", {"reserved": 50, "spec_sha256": sha256_json(spec)})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {"trials": planned, "spec_sha256": sha256_json(spec)},
    )
    records = {}
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "peer_information",
                "train-only statistical peer gaps against own/common/shuffled controls",
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
                    "2022-01-01",
                    "2023-12-31",
                    "2023-01-01",
                    "2024-12-31",
                    "unused",
                    "unused",
                    fit_stages=() if p["identity"] == "anchor" else stages(),
                ),
                sha256_json(p),
            )[0]
            for p in planned
        }
        if registry.global_trial_count() != 50:
            raise ValueError("native reservation incomplete")
        print(json.dumps({"reserved": 50, "stage": "before_numerical_read"}), flush=True)
        raw_targets = read(target_path)
        if sha256_json(raw_targets) != card["targets_canonical_sha256"]["lowvol"]:
            raise ValueError("anchor semantics changed")
        anchor = tuple(
            TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in raw_targets
        )
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        print(json.dumps({"stage": "loaded", "sessions": len(days)}), flush=True)
        with Evidence(output / "peer_inputs.csv.gz") as evidence:
            panel = peer_days(days, evidence)
        del days
        models, paths = {}, {}
        for year in (2023, 2024):
            models[year] = fit_graph(panel, year)
            paths[year] = output / f"models/{year}.json"
            write_json(paths[year], models[year])
            print(
                json.dumps(
                    {
                        "stage": "graph_fitted",
                        "year": year,
                        "nodes": len(models[year]["nodes"]),
                        "receivers": len(models[year]["graph"]),
                    }
                ),
                flush=True,
            )
        lineages = {}
        for p in planned:
            if p["identity"] != "anchor":
                for y in (2023, 2024):
                    registry.record_model_fit(
                        tids[p["key"]], str(y), model=models[y], artifact_path=paths[y]
                    )
            lineages[p["key"]] = registry.fit_lineage(tids[p["key"]])
        # Shared immutable graph: all48 stage contracts/artifacts must be byte-identical.
        primary = planned[0]["key"]
        if any(
            lineages[p["key"]] != lineages[primary] for p in planned if p["identity"] != "anchor"
        ):
            raise ValueError("shared fit lineage differs")
        cache, diagnostics = prepared_signals(registry, tids[primary], panel, models, paths)
        write_json(output / "coverage.json", diagnostics)
        write_json(output / "calendar.json", [d.date for d in panel])
        window = tuple(d for d in panel if d.date >= "2023-01-01")
        if [d.date for d in window] != [t.trade_date for t in anchor]:
            raise ValueError("continuous calendar mismatch")
        target_sets, hashes = {"anchor-lowvol": anchor}, {}
        sessions = tuple(d.bars for d in window)
        for p in planned:
            key, tk = p["key"], p["identity"] + "-" + p["policy"]
            if tk not in target_sets:
                target_sets[tk] = targets_for(panel, cache, p["group"], p["signal"], p["policy"])
            if tk not in hashes:
                rows = [asdict(t) for t in target_sets[tk]]
                hashes[tk] = sha256_json(rows)
                write_json(output / "targets" / f"{tk}.json", rows)
            report = run_stateful_execution(
                sessions,
                target_sets[tk],
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6 * p["scale"],
                    sell_tax_bps=10 * p["scale"],
                    slippage_bps=30 * p["scale"],
                    rebalance_mode="full_target" if p["identity"] == "anchor" else "target_changes",
                ),
                initial_nav=3_000_000,
            )
            row = {
                **account_summary(report),
                **p,
                "audit": audit_account(report),
                "account_sha256": save_account(output, key, report),
                "target_sha256": hashes[tk],
                "fit_lineage_sha256": lineages[key]["sha256"],
            }
            row["execution"] = {
                "executed_tickets": sum(
                    abs(o.executed_notional) > 1e-8 for d in report.periods for o in d.orders
                ),
                "traded_cny": sum(d.traded_notional_cny for d in report.periods),
                "mean_cash_fraction": sum(d.cash / d.end_nav for d in report.periods)
                / len(report.periods),
                "max_close_weight": max(
                    (m.market_value / d.end_nav for d in report.periods for m in d.marks), default=0
                ),
                "max_actual_positions": max(len(d.marks) for d in report.periods),
                "end_positions": len(report.periods[-1].marks),
            }
            if (
                p["identity"] == "anchor"
                and row["account_sha256"] != anchor_result["records"][key]["account_sha256"]
            ):
                raise ValueError("original anchor replay mismatch")
            records[key] = row
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            write_json(output / "records" / f"{key}.json", row)
            print(
                json.dumps({"completed": len(records), "key": key, "audit": row["audit"]["pass"]}),
                flush=True,
            )
        checks = {}
        for p in planned:
            if p["policy"] == "peer":
                controls = [
                    records[f"{p['identity']}-{c}-{p['roundtrip_bps']}"]
                    for c in ("own", "shuffle", "hash")
                ]
                controls.append(records[f"anchor-lowvol-{p['roundtrip_bps']}"])
                checks.setdefault(p["identity"], {})[str(p["roundtrip_bps"])] = screen(
                    records[p["key"]], controls, diagnostics
                )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("protected evidence or runtime changed")
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "checks": checks,
            "screen_survived": {
                k: all(all(x.values()) for x in v.values()) for k, v in checks.items()
            },
            "targets_sha256": hashes,
            "models_sha256": {str(y): file_sha(p) for y, p in paths.items()},
            "engineering_pass": all(r["audit"]["pass"] for r in records.values()),
            "completed_trials": len(records),
            "reserved_trials": 50,
            "raw_global_trial_lower_bound": 3556,
            "input_rows": evidence.rows,
            "protected_unchanged": True,
            "restricted_rows_read": 0,
            "validated_alpha": False,
            "statistics": {
                "status": "EXPLORATORY_REUSED_HISTORY_NOT_COURT",
                "DSR": None,
                "PBO": None,
                "placebo": None,
            },
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps({"completed": 50, "survivors": result["screen_survived"], "debt": 3556}),
            flush=True,
        )
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {
                "error_type": type(exc).__name__,
                "completed": len(records),
                "reservations_preserved": True,
                "raw_trial_debt": 3556,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
