"""Exclusive 44-account conditional-risk epoch; freeze and reserve before values."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from run_sparse_events import CARD_SHA, SNAPSHOT_SHA, Evidence, read

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.conditional_risk import (
    BASES,
    VERSION,
    contract,
    daily_predictions,
    fit_model,
    market_states,
    overlay_targets,
    plans,
    proxy_labels,
    screen,
    stages,
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

PARENT_SHA = "948ab8dc763fbfc319153ef956c107bc57d7cac111ee7995fa85b2b132276aa5"
CLAIMS = Path(__file__).resolve().parents[1] / "artifacts/conditional-risk/claims"


def controls_for(p, records):
    base, identity, cost = p["base"], p["identity"], p["roundtrip_bps"]
    return [records[f"{identity}-{c}-{cost}"] for c in ("fixed", "lag20", "shuffle")] + [
        records[f"{base}-{c}-{cost}"] for c in ("risk_only", "unscaled", "original")
    ]


def run(config):
    cfg = read(config)
    parent, original, inputs, output = [
        Path(cfg[k]).resolve() for k in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("preregistration required")
    if output.exists() or any(
        output == p or output in p.parents or p in output.parents
        for p in (parent, original, inputs)
    ):
        raise ValueError("new independent output required; never retry")
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    targets_paths = {
        b: original / f"artifacts/temporal-increments/epoch-001/targets/{b}.json" for b in BASES
    }
    if (
        file_sha(parent / "RESULT.json") != PARENT_SHA
        or not read(parent / "INDEPENDENT_AUDIT.json")["pass"]
    ):
        raise ValueError("parent evidence mismatch")
    if (
        read(parent / "RESULT.json")["raw_global_trial_lower_bound"] != 3556
        or file_sha(card_path) != CARD_SHA
    ):
        raise ValueError("parent debt/card mismatch")
    card = read(card_path)
    for b, p in targets_paths.items():
        if file_sha(p) != card["targets_file_sha256"][b]:
            raise ValueError("original target bytes changed")
    manifest = read(inputs / "manifest.json")
    if (
        sha256_json(manifest["sources"]) != SNAPSHOT_SHA
        or manifest["snapshot_sha256"] != SNAPSHOT_SHA
    ):
        raise ValueError("snapshot mismatch")
    sources = []
    for s in manifest["sources"]:
        p = (inputs / s["file"]).resolve()
        if p.parent != inputs or s["max_date"] >= "2025-01-01" or file_sha(p) != s["sha256"]:
            raise ValueError("source boundary/hash mismatch")
        sources.append(p)
    protected = [
        parent / "RESULT.json",
        parent / "INDEPENDENT_AUDIT.json",
        parent / "registry.sqlite3",
        card_path,
        *targets_paths.values(),
        inputs / "manifest.json",
        *sources,
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
        "auditor_sha256": file_sha(Path(__file__).with_name("audit_conditional_risk.py")),
        "audit_query_sha256": file_sha(
            Path(__file__).with_name("conditional_risk_source_audit.sql")
        ),
        "preregistration_comment": cfg["preregistration_comment"],
        "protected_before": before,
        "protected_files": {str(p): file_sha(p) for p in protected},
        "original_target_files": {b: str(p) for b, p in targets_paths.items()},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(CLAIMS / f"{PARENT_SHA}.json", {"reserved": 44, "spec_sha256": sha256_json(spec)})
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
                "conditional_risk",
                "train-only risk/cash allocation over unchanged frozen stock targets",
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
                    fit_stages=() if p["policy"] in ("original", "unscaled") else stages(),
                ),
                sha256_json(p),
            )[0]
            for p in planned
        }
        if registry.global_trial_count() != 44:
            raise ValueError("native reservation incomplete")
        print(json.dumps({"reserved": 44, "stage": "before_numerical_read"}), flush=True)
        anchors = {}
        for b, p in targets_paths.items():
            raw = read(p)
            if sha256_json(raw) != card["targets_canonical_sha256"][b]:
                raise ValueError("original target semantics changed")
            anchors[b] = tuple(
                TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in raw
            )
        days, quality = load_frozen_days(inputs)
        calendar = [d.date for d in days]
        write_json(output / "DATA_PREFLIGHT.json", quality)
        write_json(output / "calendar.json", calendar)
        states = market_states(days)
        write_json(output / "states.json", states)
        with Evidence(output / "proxy_components.csv.gz") as evidence:
            labels = proxy_labels(days, states, evidence)
        write_json(output / "proxy_labels.json", labels)
        print(
            json.dumps({"stage": "labels_built", "sessions": len(days), "labels": len(labels)}),
            flush=True,
        )
        models = {a: {} for a in ("direct", "shuffle")}
        paths = {a: {} for a in models}
        for alignment, model_set in models.items():
            for year in (2023, 2024):
                m = fit_model(labels, calendar, year, alignment == "shuffle")
                model_set[year] = m
                paths[alignment][year] = output / f"models/{alignment}-{year}.json"
                write_json(paths[alignment][year], m)
                print(
                    json.dumps(
                        {
                            "stage": "fit",
                            "alignment": alignment,
                            "year": year,
                            "samples": m["training_signal_dates"],
                        }
                    ),
                    flush=True,
                )
        lineages = {}
        representatives = {}
        for p in planned:
            a = "shuffle" if p["policy"] == "shuffle" else "direct"
            if p["policy"] not in ("original", "unscaled"):
                for y in (2023, 2024):
                    registry.record_model_fit(
                        tids[p["key"]], str(y), model=models[a][y], artifact_path=paths[a][y]
                    )
                representatives.setdefault(a, p["key"])
            lineages[p["key"]] = registry.fit_lineage(tids[p["key"]])
            if (
                p["policy"] not in ("original", "unscaled")
                and lineages[p["key"]] != lineages[representatives[a]]
            ):
                raise ValueError("shared model lineage mismatch")
        predictions = {
            a: daily_predictions(
                registry, tids[representatives[a]], states, calendar, models[a], paths[a]
            )
            for a in models
        }
        for a, p in predictions.items():
            write_json(output / f"predictions-{a}.json", p)
        window = tuple(d for d in days if d.date >= "2023-01-01")
        if any([t.trade_date for t in a] != [d.date for d in window] for a in anchors.values()):
            raise ValueError("base execution calendar mismatch")
        target_sets = {}
        target_hashes = {}
        diagnostics = {}
        sessions = tuple(d.bars for d in window)
        for p in planned:
            key = p["key"]
            tk = key.rsplit("-", 1)[0]
            if tk not in target_sets:
                if p["policy"] in ("original", "unscaled"):
                    target_sets[tk] = anchors[p["base"]]
                else:
                    a = "shuffle" if p["policy"] == "shuffle" else "direct"
                    target_sets[tk], diagnostics[tk] = overlay_targets(
                        anchors[p["base"]], predictions[a], p["rule"], p["policy"]
                    )
                raw = [asdict(t) for t in target_sets[tk]]
                target_hashes[tk] = sha256_json(raw)
                write_json(output / f"targets/{tk}.json", raw)
            report = run_stateful_execution(
                sessions,
                target_sets[tk],
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6 * p["scale"],
                    sell_tax_bps=10 * p["scale"],
                    slippage_bps=30 * p["scale"],
                    rebalance_mode="full_target" if p["policy"] == "original" else "target_changes",
                ),
                initial_nav=3_000_000,
            )
            row = {
                **account_summary(report),
                **p,
                "audit": audit_account(report),
                "account_sha256": save_account(output, key, report),
                "target_sha256": target_hashes[tk],
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
            if p["base"] == "lowvol" and p["policy"] == "original":
                expected = read(parent / "RESULT.json")["records"][
                    f"anchor-lowvol-{p['roundtrip_bps']}"
                ]["account_sha256"]
                if row["account_sha256"] != expected:
                    raise ValueError("original lowvol replay mismatch")
            records[key] = row
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            write_json(output / f"records/{key}.json", row)
            print(
                json.dumps({"completed": len(records), "key": key, "audit": row["audit"]["pass"]}),
                flush=True,
            )
        write_json(output / "allocation_diagnostics.json", diagnostics)
        checks = {}
        for p in planned:
            if p["policy"] == "model":
                checks.setdefault(p["identity"], {})[str(p["roundtrip_bps"])] = screen(
                    records[p["key"]], controls_for(p, records), states
                )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("protected evidence/runtime changed")
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "checks": checks,
            "screen_survived": {
                k: all(all(x.values()) for x in v.values()) for k, v in checks.items()
            },
            "targets_sha256": target_hashes,
            "models_sha256": {
                f"{a}-{y}": file_sha(p) for a, ps in paths.items() for y, p in ps.items()
            },
            "engineering_pass": all(r["audit"]["pass"] for r in records.values()),
            "completed_trials": len(records),
            "reserved_trials": 44,
            "raw_global_trial_lower_bound": 3600,
            "proxy_components": evidence.rows,
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
            json.dumps({"completed": 44, "survivors": result["screen_survived"], "debt": 3600}),
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
                "raw_trial_debt": 3600,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
