"""Single-use 2 x 2 x 3 frozen-target experiment. No fit or Alpha certificate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.calendar_robustness import account_summary
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

VERSION = "11.13.0"
DEBT = 3322
PARENT_SHA = "b42aed511e775c8588cf7b60f50fe8469a47f48f6ed28d2dd6ce0c781246bde4"
DEEP_SHA = "2b8385034514cab167470982d780fceac6eacf97478c74d220a664c4c7cca407"
CARD_SHA = "c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134"
SNAPSHOT_SHA = "b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51"
POLICIES = ("stable_lowrisk", "lowvol")
MODES = ("full_target", "target_changes")
CLAIM_ROOT = Path(__file__).resolve().parents[1] / "artifacts/stability-attribution/claims"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def plans():
    return [
        {"policy": p, "mode": m, "scale": s, "roundtrip_bps": 82 * s, "key": f"{p}-{m}-{82 * s}"}
        for p in POLICIES
        for m in MODES
        for s in (0, 1, 2)
    ]


def screen(a, b):
    return {
        "accounts": a["audit"]["pass"] and b["audit"]["pass"],
        "both_years_positive": all(a["years"][y] > 0 for y in ("2023", "2024")),
        "sharpe": a["pooled_sharpe"] >= 0.7,
        "drawdown": a["metrics"]["max_drawdown"] >= -0.25,
        "total_increment": a["metrics"]["net_total_return"] - b["metrics"]["net_total_return"]
        >= 0.03,
        "annual_increment": all(a["years"][y] - b["years"][y] >= -0.05 for y in ("2023", "2024")),
    }


def attribution(records):
    returns = {k: v["metrics"]["net_total_return"] for k, v in records.items()}
    out = {}
    for cost in (0, 82, 164):
        membership = {
            m: returns[f"stable_lowrisk-{m}-{cost}"] - returns[f"lowvol-{m}-{cost}"] for m in MODES
        }
        maintenance = {
            p: returns[f"{p}-target_changes-{cost}"] - returns[f"{p}-full_target-{cost}"]
            for p in POLICIES
        }
        out[str(cost)] = {
            "membership_increment": membership,
            "maintenance_increment": maintenance,
            "interaction": membership["target_changes"] - membership["full_target"],
        }
    out["cost_path_drag"] = {
        f"{p}-{m}-{cost}": returns[f"{p}-{m}-0"] - returns[f"{p}-{m}-{cost}"]
        for p in POLICIES
        for m in MODES
        for cost in (82, 164)
    }
    return out


def run(config_path):
    cfg = read(Path(config_path))
    if type(cfg.get("preregistration_comment")) is not int or cfg["preregistration_comment"] <= 0:
        raise ValueError("positive preregistration comment required")
    parent, original, inputs, output = [
        Path(cfg[n]).resolve() for n in ("parent_dir", "original_tree", "input_dir", "output_dir")
    ]
    if output.exists():
        raise FileExistsError("operation already exists; do not retry")
    if any(
        output == p or p in output.parents or output in p.parents
        for p in (parent, original, inputs)
    ):
        raise ValueError("independent output required")
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    target_dir = original / "artifacts/temporal-increments/epoch-001/targets"
    deep = original / "artifacts/stability-challenge/epoch-001"
    for file, digest in (
        (parent / "RESULT.json", PARENT_SHA),
        (card_path, CARD_SHA),
        (deep / "RESULT.json", DEEP_SHA),
    ):
        if file_sha(file) != digest:
            raise ValueError("frozen parent/card changed")
    previous, card, reference = (
        read(parent / "RESULT.json"),
        read(card_path),
        read(deep / "RESULT.json"),
    )
    if previous["raw_global_trial_lower_bound"] != DEBT or not previous["engineering_pass"]:
        raise ValueError("debt or prior engineering audit mismatch")
    for folder in (parent, deep):
        if not read(folder / "INDEPENDENT_AUDIT.json")["pass"]:
            raise ValueError("parent independent audit required")
    original_src = original / "src/stephen_quant"
    old_runtime = sha256_json(
        {
            p.relative_to(original_src).as_posix(): hashlib.sha256(
                p.read_text(encoding="utf-8").encode()
            ).hexdigest()
            for p in sorted(original_src.rglob("*.py"))
        }
    )
    if old_runtime != card["runtime_code_sha256"]:
        raise ValueError("original runtime changed")
    manifest = read(inputs / "manifest.json")
    if (
        manifest["snapshot_sha256"] != SNAPSHOT_SHA
        or sha256_json(manifest["sources"]) != SNAPSHOT_SHA
    ):
        raise ValueError("source snapshot changed")
    sources = []
    for entry in manifest["sources"]:
        path = (inputs / entry["file"]).resolve()
        if path.parent != inputs or entry["max_date"] >= "2025-01-01":
            raise ValueError("source outside scope")
        if file_sha(path) != entry["sha256"]:
            raise ValueError("source bytes changed")
        sources.append(path)
    target_paths = {p: target_dir / f"{p}.json" for p in POLICIES}
    for p, path in target_paths.items():
        if file_sha(path) != card["targets_file_sha256"][p]:
            raise ValueError("frozen target changed")
    protected = [
        card_path,
        parent / "RESULT.json",
        deep / "RESULT.json",
        inputs / "manifest.json",
        parent / "registry.sqlite3",
        deep / "registry.sqlite3",
        *sources,
        *target_paths.values(),
    ]
    before, _ = protected_digest(protected)
    planned = plans()
    spec = {
        "version": VERSION,
        "preregistration_comment": cfg["preregistration_comment"],
        "parent_sha256": PARENT_SHA,
        "original_runtime_sha256": old_runtime,
        "snapshot_sha256": SNAPSHOT_SHA,
        "card_sha256": CARD_SHA,
        "runtime_code_sha256": runtime_code_hash(),
        "driver_sha256": file_sha(Path(__file__)),
        "raw_debt_before": DEBT,
        "reserved_trials": 12,
        "plans": planned,
        "protected_before": before,
        "targets_sha256": card["targets_canonical_sha256"],
        "costs": "scale*(commission6_each_side+sell_tax10+slippage30_each_side)",
        "rule": "changed or pending target at refresh; unchanged shares drift; refresh cap2.5%; forced exits first",
        "pending": "retry next refresh until requested-notional minus execution <=1e-8 CNY",
        "exposure": "reused2023-2024; no sealed2025/2026; no independent certificate",
        "validated_alpha": False,
    }
    write_json(
        CLAIM_ROOT / (PARENT_SHA + ".json"),
        {"output": str(output), "spec": sha256_json(spec), "reserved": 12},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "frozen_spec.json", spec)
    write_json(
        output / "first_read_reservations.json",
        {
            "trials": planned,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
        },
    )
    try:
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"inputs": SNAPSHOT_SHA}), vendor_version=VERSION
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "stability_attribution",
                "membership vs maintenance",
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
        # All native no-fit contracts precede source numerical reads / target decoding.
        for tid in tids.values():
            if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
                raise ValueError("explicit unfitted contract required")
        targets = {}
        for p, path in target_paths.items():
            rows = read(path)
            if sha256_json(rows) != card["targets_canonical_sha256"][p]:
                raise ValueError("target semantics changed")
            targets[p] = tuple(
                TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in rows
            )
            write_json(output / "targets" / f"{p}.json", rows)
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        window = tuple(d for d in days if d.date[:4] in ("2023", "2024"))
        if any([d.date for d in window] != [t.trade_date for t in targets[p]] for p in POLICIES):
            raise ValueError("target calendar changed")
        sessions = tuple(d.bars for d in window)
        records = {}
        for p in planned:
            scale, key = p["scale"], p["key"]
            report = run_stateful_execution(
                sessions,
                targets[p["policy"]],
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6 * scale,
                    sell_tax_bps=10 * scale,
                    slippage_bps=30 * scale,
                    rebalance_mode=p["mode"],
                ),
                initial_nav=3_000_000,
            )
            row = account_summary(report)
            row.update(
                audit=audit_account(report),
                account_sha256=save_account(output, key, report),
                fit_lineage_sha256=registry.fit_lineage(tids[key])["sha256"],
                **p,
            )
            row["execution"] = {
                "traded_cny": sum(d.traded_notional_cny for d in report.periods),
                "executed_tickets": sum(
                    abs(o.executed_notional) > 1e-8 for d in report.periods for o in d.orders
                ),
                "mean_cash_fraction": sum(d.cash / d.end_nav for d in report.periods)
                / len(report.periods),
                "max_close_weight": max(
                    (m.market_value / d.end_nav for d in report.periods for m in d.marks), default=0
                ),
                "close_position_days_above_2_5pct": sum(
                    m.market_value / d.end_nav > 0.025 + 1e-10
                    for d in report.periods
                    for m in d.marks
                ),
            }
            if (
                p["mode"] == "full_target"
                and scale == 1
                and row["account_sha256"]
                != reference["records"]["baseline_82"][p["policy"]]["account_sha256"]
            ):
                raise ValueError("legacy account byte replay failed")
            registry.record_trial_result(tids[key], json.dumps(row, sort_keys=True))
            records[key] = row
            write_json(output / "records" / f"{key}.json", row)
            print(
                json.dumps(
                    {"completed": len(records), "account": key, "engineering": row["audit"]["pass"]}
                ),
                flush=True,
            )
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
            or file_sha(Path(__file__)) != spec["driver_sha256"]
        ):
            raise ValueError("frozen source/runtime changed during operation")
        checks = {
            m: {
                str(c): screen(records[f"stable_lowrisk-{m}-{c}"], records[f"lowvol-{m}-{c}"])
                for c in (82, 164)
            }
            for m in MODES
        }
        result = {
            "version": VERSION,
            "spec": spec,
            "records": records,
            "checks": checks,
            "attribution": attribution(records),
            "completed_trials": len(records),
            "reserved_trials": 12,
            "raw_global_trial_lower_bound": DEBT + 12,
            "engineering_pass": all(r["audit"]["pass"] for r in records.values()),
            "restricted_rows_read": 0,
            "validated_alpha": False,
            "protected_unchanged": True,
            "screen_survived": {m: all(all(v.values()) for v in checks[m].values()) for m in MODES},
            "statistics": {
                "status": "NOT_INDEPENDENT",
                "DSR": None,
                "PBO": None,
                "placebo": None,
                "reason": "post-selected allocation on reused history; no full-family independent Court",
            },
        }
        write_json(output / "RESULT.json", result)
        print(
            json.dumps(
                {
                    "engineering": result["engineering_pass"],
                    "screen": result["screen_survived"],
                    "debt": DEBT + 12,
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
