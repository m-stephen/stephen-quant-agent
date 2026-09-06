"""Single-use V11.14 experiment: frozen sources, all plans before numerical reads."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.risk_stratified import (
    GROUPS,
    MECHANISMS,
    contract,
    mechanism_days,
    plans,
    screen,
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

VERSION, DEBT = "11.14.0", 3334
PARENT_SHA = "5f66f5d5c1b77dff2763df7d69f14c45e3273474a809329b49c9193d8daf3093"
SNAPSHOT_SHA = "b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51"
CARD_SHA = "c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134"
CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts/risk-stratified/claims"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(config_path):
    cfg = read(config_path)
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("preregistration required")
    parent, original, inputs, output = [
        Path(cfg[k]).resolve() for k in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    if output.exists():
        raise FileExistsError("operation exists; resume evidence only,never rerun")
    if any(
        output == p or p in output.parents or output in p.parents
        for p in (parent, original, inputs)
    ):
        raise ValueError("independent output required")
    if file_sha(parent / "RESULT.json") != PARENT_SHA:
        raise ValueError("frozen parent changed")
    prior = read(parent / "RESULT.json")
    if (
        prior["raw_global_trial_lower_bound"] != DEBT
        or not read(parent / "INDEPENDENT_AUDIT.json")["pass"]
    ):
        raise ValueError("prior debt/audit mismatch")
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    if file_sha(card_path) != CARD_SHA:
        raise ValueError("original card changed")
    card = read(card_path)
    anchor_path = original / "artifacts/temporal-increments/epoch-001/targets/lowvol.json"
    if file_sha(anchor_path) != card["targets_file_sha256"]["lowvol"]:
        raise ValueError("original target changed")
    manifest = read(inputs / "manifest.json")
    if (
        manifest["snapshot_sha256"] != SNAPSHOT_SHA
        or sha256_json(manifest["sources"]) != SNAPSHOT_SHA
    ):
        raise ValueError("frozen snapshot changed")
    source_paths = []
    for entry in manifest["sources"]:
        path = (inputs / entry["file"]).resolve()
        if (
            path.parent != inputs
            or entry["max_date"] >= "2025-01-01"
            or file_sha(path) != entry["sha256"]
        ):
            raise ValueError("source bounds/hash mismatch")
        source_paths.append(path)
    protected = [
        parent / "RESULT.json",
        parent / "registry.sqlite3",
        card_path,
        anchor_path,
        inputs / "manifest.json",
        *source_paths,
    ]
    before, _ = protected_digest(protected)
    planned = plans()
    spec = {
        "version": VERSION,
        "contract": contract(),
        "plans": planned,
        "preregistration_comment": cfg["preregistration_comment"],
        "parent_sha256": PARENT_SHA,
        "snapshot_sha256": SNAPSHOT_SHA,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "raw_debt_before": DEBT,
        "reserved_trials": len(planned),
        "protected_before": before,
    }
    write_json(
        CLAIM_ROOT / f"{PARENT_SHA}.json",
        {"output": str(output), "spec_sha256": sha256_json(spec), "reserved": len(planned)},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "trials": planned,
            "spec_sha256": sha256_json(spec),
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "risk_stratified",
                "joint mechanism ranks across full risk support",
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
            for p in planned
        }
        for tid in tids.values():
            if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
                raise ValueError("explicit native no-fit contract required")
        print(json.dumps({"reserved": len(tids), "stage": "before_numerical_read"}), flush=True)
        raw_targets = read(anchor_path)
        if sha256_json(raw_targets) != card["targets_canonical_sha256"]["lowvol"]:
            raise ValueError("anchor semantics mismatch")
        anchor = tuple(
            TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in raw_targets
        )
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        panel, coverage = mechanism_days(days)
        window = tuple(d for d in panel if d.date[:4] in ("2023", "2024"))
        if [d.date for d in window] != [t.trade_date for t in anchor]:
            raise ValueError("continuous calendar mismatch")
        write_json(output / "coverage.json", coverage)
        targets, diagnostics, cell_cache = {"anchor-lowvol": anchor}, {}, {}
        sessions = tuple(d.bars for d in window)
        records, hashes = {}, {}
        for p in planned:
            key, target_key = p["key"], f"{p['group']}-{p['policy']}"
            if target_key not in targets:
                targets[target_key], diagnostics[target_key] = targets_for(
                    registry, tids[key], window, p["group"], p["policy"], cell_cache
                )
            if target_key not in hashes:
                rows = [asdict(t) for t in targets[target_key]]
                hashes[target_key] = sha256_json(rows)
                write_json(output / "targets" / f"{target_key}.json", rows)
            report = run_stateful_execution(
                sessions,
                targets[target_key],
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6 * p["scale"],
                    sell_tax_bps=10 * p["scale"],
                    slippage_bps=30 * p["scale"],
                ),
                initial_nav=3_000_000,
            )
            row = account_summary(report)
            row.update(
                **p,
                audit=audit_account(report),
                account_sha256=save_account(output, key, report),
                target_sha256=hashes[target_key],
                fit_lineage_sha256=registry.fit_lineage(tids[key])["sha256"],
            )
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
            }
            if (
                p["group"] == "anchor"
                and row["account_sha256"]
                != prior["records"][f"lowvol-full_target-{p['roundtrip_bps']}"]["account_sha256"]
            ):
                raise ValueError("original lowvol account replay mismatch")
            records[key] = row
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            write_json(output / "records" / f"{key}.json", row)
            print(
                json.dumps({"completed": len(records), "key": key, "audit": row["audit"]["pass"]}),
                flush=True,
            )
        write_json(output / "selection_diagnostics.json", diagnostics)
        checks = {
            f"{g}-{m}": {
                str(c): screen(
                    records[f"{g}-{m}-{c}"],
                    [
                        records[f"{g}-hash-{c}"],
                        records[f"{g}-price_reversal-{c}"],
                        records[f"anchor-lowvol-{c}"],
                    ],
                )
                for c in (82, 164)
            }
            for g in GROUPS
            for m in MECHANISMS
        }
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("frozen evidence or runtime changed during operation")
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "checks": checks,
            "screen_survived": {
                k: all(all(x.values()) for x in v.values()) for k, v in checks.items()
            },
            "targets_sha256": hashes,
            "engineering_pass": all(r["audit"]["pass"] for r in records.values()),
            "completed_trials": len(records),
            "reserved_trials": len(planned),
            "raw_global_trial_lower_bound": DEBT + len(planned),
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
            json.dumps(
                {
                    "engineering": result["engineering_pass"],
                    "survivors": result["screen_survived"],
                    "debt": DEBT + len(planned),
                }
            ),
            flush=True,
        )
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {"error_type": type(exc).__name__, "reservations_preserved": True},
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    run(parser.parse_args().config)
