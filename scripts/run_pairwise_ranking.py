"""Single exclusive 24-account date-balanced pairwise epoch, preregister then reserve."""

import argparse
import gzip
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from run_sparse_events import CARD_SHA, SNAPSHOT_SHA, read

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.pairwise_ranking import (
    BASES,
    KINDS,
    VERSION,
    contract,
    fit_model,
    plans,
    prepare,
    screen,
    stages,
    targets_for,
    training_pairs,
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

PARENT_SHA = "c0451e1b077ee67c8ef99e4dc982fab7c546b433b254d270baa53b3082c9e83f"
ABORTED_SHA = "3c254b86990b1bc801e58ace3bd8da30a079c162d9ee7bb718e67cf9409bb034"
CLAIMS = Path(__file__).resolve().parents[1] / "artifacts/pairwise-ranking/claims"


def controls_for(p, records):
    cost = p["roundtrip_bps"]
    return [records[f"{p['basis']}-{k}-{cost}"] for k in ("risk", "shuffle", "regression")] + [
        records[f"control-{k}-{cost}"]
        for k in ("hash", "lowvol", "original_lowvol", "original_stable")
    ]


def write_gzip(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("xb") as stream,
        gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as z,
    ):
        z.write(json.dumps(value, sort_keys=True, allow_nan=False).encode())


def reserve(output, spec):
    registry = ExperimentRegistry(output / "registry.sqlite3")
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
    )
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            "pairwise_ranking",
            "same-cell date-balanced relative ranking",
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
                fit_stages=stages() if p["policy"] in KINDS else (),
            ),
            sha256_json(p),
        )[0]
        for p in spec["plans"]
    }
    if registry.global_trial_count() != 24:
        raise ValueError("all24 native trials must precede numerical read")
    return registry, tids


def run(config):
    cfg = read(config)
    parent, original, inputs, output = [
        Path(cfg[k]).resolve() for k in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    aborted = Path(cfg["aborted_dir"]).resolve()
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("preregistration required")
    if output.exists() or any(
        output == p or output in p.parents or p in output.parents
        for p in (parent, original, inputs, aborted)
    ):
        raise ValueError("new independent output required; never retry")
    if (
        file_sha(aborted / "ABORTED.json") != ABORTED_SHA
        or read(aborted / "ABORTED.json")["raw_trial_debt"] != 3624
    ):
        raise ValueError("aborted operation and its debt must be preserved")
    with sqlite3.connect(
        f"file:{(aborted / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as db:
        if db.execute("SELECT count(*) FROM trials").fetchone()[0] != 24:
            raise ValueError("aborted native reservations incomplete")
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    targets_paths = {
        b: original / f"artifacts/temporal-increments/epoch-001/targets/{b}.json"
        for b in ("lowvol", "stable_lowrisk")
    }
    if (
        file_sha(parent / "RESULT.json") != PARENT_SHA
        or not read(parent / "INDEPENDENT_AUDIT.json")["pass"]
        or read(parent / "RESULT.json")["raw_global_trial_lower_bound"] != 3600
        or file_sha(card_path) != CARD_SHA
    ):
        raise ValueError("parent debt/evidence/card mismatch")
    card = read(card_path)
    for b, p in targets_paths.items():
        if file_sha(p) != card["targets_file_sha256"][b]:
            raise ValueError("original bytes changed")
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
        *sorted(p for p in aborted.rglob("*") if p.is_file()),
    ]
    before, _ = protected_digest(protected)
    spec = {
        "contract": contract(),
        "plans": plans(),
        "parent_sha256": PARENT_SHA,
        "aborted_sha256": ABORTED_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "auditor_sha256": file_sha(Path(__file__).with_name("audit_pairwise_ranking.py")),
        "audit_query_sha256": file_sha(Path(__file__).with_name("pairwise_source_audit.sql")),
        "preregistration_comment": cfg["preregistration_comment"],
        "protected_before": before,
        "protected_files": {str(p): file_sha(p) for p in protected},
        "original_target_files": {b: str(p) for b, p in targets_paths.items()},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(CLAIMS / f"{ABORTED_SHA}.json", {"reserved": 24, "spec_sha256": sha256_json(spec)})
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {"trials": plans(), "spec_sha256": sha256_json(spec)},
    )
    records = {}
    try:
        registry, tids = reserve(output, spec)
        print(json.dumps({"reserved": 24, "stage": "before_numerical_read"}), flush=True)
        anchors = {}
        for b, p in targets_paths.items():
            raw = read(p)
            if sha256_json(raw) != card["targets_canonical_sha256"][b]:
                raise ValueError("original target semantics changed")
            anchors[b] = tuple(
                TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in raw
            )
        raw_days, quality = load_frozen_days(inputs)
        days, coverage = prepare(raw_days)
        del raw_days
        calendar = [d.date for d in days]
        write_json(output / "DATA_PREFLIGHT.json", quality)
        write_json(output / "calendar.json", calendar)
        write_json(output / "coverage.json", coverage)
        cache = {}
        pairs = training_pairs(days, cache)
        write_gzip(output / "training_pairs.json.gz", pairs)
        print(json.dumps({"stage": "labels_built", "pairs": len(pairs)}), flush=True)
        models, paths = {}, {}
        for basis in BASES:
            for kind in KINDS:
                mk = f"{basis}-{kind}"
                models[mk], paths[mk] = {}, {}
                for year in (2023, 2024):
                    model = fit_model(pairs, calendar, year, basis, kind)
                    models[mk][year] = model
                    paths[mk][year] = output / f"models/{mk}-{year}.json"
                    write_json(paths[mk][year], model)
                    print(
                        json.dumps(
                            {
                                "fit": mk,
                                "year": year,
                                "dates": model["training_signal_dates"],
                                "pairs": model["training_pairs"],
                            }
                        ),
                        flush=True,
                    )
        window = tuple(d for d in days if d.date >= "2023-01-01")
        if any([t.trade_date for t in a] != [d.date for d in window] for a in anchors.values()):
            raise ValueError("anchor calendar mismatch")
        sessions = tuple(d.bars for d in window)
        lineages, target_sets, target_hashes, diagnostics = {}, {}, {}, {}
        for p in plans():
            key = p["key"]
            tk = key.rsplit("-", 1)[0]
            if p["policy"] in KINDS:
                for y in (2023, 2024):
                    registry.record_model_fit(
                        tids[key], str(y), model=models[tk][y], artifact_path=paths[tk][y]
                    )
            lineages[key] = registry.fit_lineage(tids[key])
            if tk not in target_sets:
                if p["policy"].startswith("original_"):
                    target_sets[tk] = anchors[
                        "lowvol" if p["policy"] == "original_lowvol" else "stable_lowrisk"
                    ]
                else:
                    target_sets[tk], diagnostics[tk] = targets_for(
                        registry,
                        tids[key],
                        window,
                        p["policy"],
                        cache,
                        models.get(tk),
                        paths.get(tk),
                    )
                raw = [asdict(t) for t in target_sets[tk]]
                target_hashes[tk] = sha256_json(raw)
                write_json(output / f"targets/{tk}.json", raw)
            elif p["policy"] in KINDS and lineages[key] != lineages[tk + "-82"]:
                raise ValueError("shared model lineage mismatch")
            report = run_stateful_execution(
                sessions,
                target_sets[tk],
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6 * p["scale"],
                    sell_tax_bps=10 * p["scale"],
                    slippage_bps=30 * p["scale"],
                    rebalance_mode="full_target"
                    if p["policy"].startswith("original_")
                    else "target_changes",
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
            if p["policy"].startswith("original_"):
                b = "lowvol" if p["policy"] == "original_lowvol" else "stable_lowrisk"
                expected = read(parent / "RESULT.json")["records"][
                    f"{b}-original-{p['roundtrip_bps']}"
                ]["account_sha256"]
                if row["account_sha256"] != expected:
                    raise ValueError("original account replay mismatch")
            records[key] = row
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            write_json(output / f"records/{key}.json", row)
            print(
                json.dumps({"completed": len(records), "key": key, "audit": row["audit"]["pass"]}),
                flush=True,
            )
        write_gzip(output / "rank_cache.json.gz", cache)
        write_gzip(
            output / "feature_cache.json.gz", {d.date: d.features for d in days if d.date in cache}
        )
        write_json(output / "selection_diagnostics.json", diagnostics)
        checks = {}
        for p in plans():
            if p["policy"] == "full":
                checks.setdefault(p["identity"], {})[str(p["roundtrip_bps"])] = screen(
                    records[p["key"]],
                    controls_for(p, records),
                    diagnostics[p["key"].rsplit("-", 1)[0]],
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
            "reserved_trials": 24,
            "raw_global_trial_lower_bound": 3648,
            "training_pairs": len(pairs),
            "rank_dates": len(cache),
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
            json.dumps({"completed": 24, "survivors": result["screen_survived"], "debt": 3648}),
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
                "raw_trial_debt": 3648,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
