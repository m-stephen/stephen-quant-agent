"""Bounded, automatically sequenced incremental research using immutable V11.6 inputs."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from stephen_quant.discovery.incremental_alpha import (
    CRITERIA,
    VERSION,
    IncrementalHypothesis,
    audit_account,
    batches,
    execute,
    holding_overlap,
    incremental_targets,
    policy,
    suspected_lead,
)
from stephen_quant.discovery.reliability_calibration import family_placebo
from stephen_quant.discovery.reliable_research import metric_bundle, temporal_selection
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import daily_evidence, file_sha, load_frozen_days
from stephen_quant.workflows.v114_reliable_epoch import (
    historical_debt,
    protected_digest,
    runtime_code_hash,
    write_json,
)


def inventory(pack):
    items = {}
    for h in pack:
        items[h.identity] = {
            "identity": h.identity,
            "name": h.name,
            "hypothesis": asdict(h),
            "kind": "candidate",
        }
        for kind in ("lowvol", "hash"):
            identity = sha256_json(
                {"kind": kind, "field": h.field, "horizon": h.horizon, "policy": policy()}
            )
            items.setdefault(
                identity,
                {
                    "identity": identity,
                    "name": f"{kind}_{h.field}_h{h.horizon}",
                    "hypothesis": asdict(h),
                    "kind": kind,
                },
            )
    return list(items.values())


def save_account(output, name, report):
    path = output / "accounts" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for row in daily_evidence(report):
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    return file_sha(path)


def evaluate_batch(days, pack, output, *, raw_trials, registry=None, trial_ids=None):
    records = {
        h.identity: {
            "name": h.name,
            "identity": h.identity,
            "hypothesis": asdict(h),
            "mechanism": h.mechanism,
            "years": {},
        }
        for h in pack
    }
    control_results = {}
    items = inventory(pack)
    controls = {(i["hypothesis"]["field"], i["kind"]): i for i in items if i["kind"] != "candidate"}
    account_count = 0
    for year in ("2023", "2024"):
        window = tuple(d for d in days if d.date.startswith(year))
        if len(window) < 200:
            raise ValueError("incomplete research year")
        cache, ranks = {}, {}
        for h in pack:
            records[h.identity]["years"][year] = {}
            targets, coverage = incremental_targets(window, h, rank_cache=ranks)
            if not coverage or not any(c["selected"] for c in coverage):
                raise ValueError("empty mechanism coverage, not an evaluated zero-return factor")
            for cost in (0, 1, 2):
                for kind in ("lowvol", "hash"):
                    key = (h.field, kind, cost)
                    if key not in cache:
                        item = controls[h.field, kind]
                        ct, _ = incremental_targets(window, h, kind, ranks)
                        control = execute(window, ct, cost)
                        audit = audit_account(control)
                        digest = save_account(output, f"{year}-{item['name']}-{cost}", control)
                        cache[key] = control
                        control_results.setdefault(item["identity"], {}).setdefault(year, {})[
                            str(cost)
                        ] = {
                            "metrics": asdict(control.metrics),
                            "audit": audit,
                            "targets_sha256": sha256_json([asdict(t) for t in ct]),
                            "account_sha256": digest,
                        }
                        account_count += 1
                result = execute(window, targets, cost)
                audit = audit_account(result)
                base, hashed = cache[h.field, "lowvol", cost], cache[h.field, "hash", cost]
                metrics = metric_bundle(result, base)
                metrics.update(
                    hash_control_return=hashed.metrics.net_total_return,
                    holdings_jaccard_vs_lowvol=holding_overlap(result, base),
                    audit=audit,
                    targets_sha256=sha256_json([asdict(t) for t in targets]),
                    account_sha256=save_account(output, f"{year}-{h.name}-{cost}", result),
                    quarterly_returns={
                        str(q): math.prod(
                            1 + p.net_return
                            for p in result.periods
                            if (int(p.trade_date[5:7]) - 1) // 3 + 1 == q
                        )
                        - 1
                        for q in (1, 2, 3, 4)
                    },
                )
                records[h.identity]["years"][year][str(cost)] = metrics
                account_count += 1
            write_json(output / "coverage" / f"{year}-{h.name}.json", coverage)
            print(
                json.dumps({"year": year, "candidate": h.name, "accounts": account_count}),
                flush=True,
            )
        write_json(output / f"{year}_checkpoint.json", list(records.values()))
    for record in records.values():
        record["assessment"] = suspected_lead(record["years"])
    matrix = {
        key: [v for year in ("2023", "2024") for v in r["years"][year]["2"]["daily_active"]]
        for key, r in records.items()
    }
    dates = [d.date for d in days if d.date[:4] in ("2023", "2024")]
    # Actual max holding horizon, never under-purge a 60-session strategy with20.
    try:
        statistics = temporal_selection(
            dates, matrix, raw_trials, holding_period_sessions=max(h.horizon for h in pack)
        )
    except ValueError as exc:
        statistics = {"status": "NOT_IDENTIFIABLE", "reason": str(exc)}
    placebo = family_placebo(matrix, seed=182, block=max(h.horizon for h in pack))
    leads = [r for r in records.values() if r["assessment"]["suspected_lead"]]
    # Explicit historical post-selection, not the2023 selector or fresh holdout evidence.
    winner = (
        max(leads, key=lambda r: (r["assessment"]["compound_increment_vs_lowvol"], r["identity"]))
        if leads
        else None
    )
    report = {
        "candidates": list(records.values()),
        "controls": control_results,
        "statistics": statistics,
        "placebo": placebo,
        "account_windows": account_count,
        "winner": winner["identity"] if winner else None,
        "suspected_count": len(leads),
        "validated_alpha": False,
        "selection": "post-selected on contaminated2023+2024, no OOS certification",
    }
    if registry is not None:
        for item in items:
            for cost in (0, 1, 2):
                payload = (
                    records[item["identity"]]["years"]
                    if item["kind"] == "candidate"
                    else control_results[item["identity"]]
                )
                registry.record_trial_result(
                    trial_ids[item["identity"], cost],
                    json.dumps(
                        {year: payload[year][str(cost)] for year in ("2023", "2024")},
                        sort_keys=True,
                    ),
                )
    write_json(output / "RESULT.json", report)
    return report


def run_incremental_epoch(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    output = Path(config["output_dir"]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    debt, legacy = historical_debt(config["legacy_operation_dirs"])
    if debt < 2866:
        raise ValueError("both V11.6 operation ledgers are required; debt cannot disappear")
    prior_evidence = []
    for folder in sorted({Path(p).resolve() for p in config.get("prior_incremental_dirs", [])}):
        reserved = json.loads((folder / "first_read_reservations.json").read_text())
        debt += len(reserved["trials"])
        prior_evidence.append(
            {
                "sha256": file_sha(folder / "first_read_reservations.json"),
                "charged": len(reserved["trials"]),
            }
        )
    plans = batches()
    all_items = [item for pack in plans for item in inventory(pack)]
    identities = [i["identity"] for i in all_items]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate identity across batches must be explicitly accounted")
    before, count = protected_digest(config["protected_paths"])
    if not count:
        raise ValueError("protected frozen candidate files are required")
    spec = {
        "version": VERSION,
        "issue": 182,
        "criteria": CRITERIA,
        "policy": policy(),
        "batches": [[asdict(h) for h in p] for p in plans],
        "raw_debt_before": debt,
        "legacy": legacy,
        "prior_incremental": prior_evidence,
        "runtime_code_sha256": runtime_code_hash(),
        "exposure": "2023/2024 reused historical development;2025/2026 forbidden this run",
        "stop": "first completed batch with suspected lead; preserve reserved unused budget",
        "protected_before": before,
    }
    write_json(output / "frozen_spec.json", spec)
    reservations = [
        {"identity": i["identity"], "cost": c, "name": i["name"]}
        for i in all_items
        for c in (0, 1, 2)
    ]
    write_json(
        output / "first_read_reservations.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
            "trials": reservations,
        },
    )
    try:
        inputs = Path(config["frozen_inputs_dir"]).resolve()
        snapshot = json.loads((inputs / "manifest.json").read_text())
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"bounded_inputs": snapshot["snapshot_sha256"]}),
            vendor_version=VERSION,
        )
        eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "incremental_alpha",
                "matched-control bounded historical exploration",
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        trial_ids = {}
        for item in all_items:
            for cost in (0, 1, 2):
                trial_ids[item["identity"], cost] = registry.create_trial_deterministic(
                    TrialSpec(
                        eid,
                        item["name"],
                        item["identity"],
                        json.dumps({"item": item, "cost": cost}),
                        182,
                        "2022-01-01",
                        "2022-12-31",
                        "2023-01-01",
                        "2023-12-31",
                        "2024-01-01",
                        "2024-12-31",
                    ),
                    f"{item['identity']}:{cost}",
                )[0]
        # Manifest metadata only above. Every attempt is registered before price bytes.
        write_json(
            output / "local_input_reference.json", {"path": str(inputs), "snapshot": snapshot}
        )
        days, quality = load_frozen_days(inputs)
        required = {h.field for p in plans for h in p} | {"volatility_20"}
        if any(not quality.get(f"available_rows:{f}") for f in required):
            raise ValueError("required campaign field unavailable")
        write_json(output / "DATA_PREFLIGHT.json", quality)
        reports = []
        for index, pack in enumerate(plans, 1):
            report = evaluate_batch(
                days,
                pack,
                output / f"batch-{index:02d}",
                raw_trials=debt + len(reservations),
                registry=registry,
                trial_ids=trial_ids,
            )
            reports.append(report)
            if report["winner"]:
                winner = next(r for r in report["candidates"] if r["identity"] == report["winner"])
                write_json(
                    output / "FROZEN_LEAD.json",
                    {
                        "candidate": winner,
                        "snapshot_sha256": snapshot["snapshot_sha256"],
                        "spec_sha256": sha256_json(spec),
                        "criteria": CRITERIA,
                        "status": CRITERIA["status"],
                        "validated_alpha": False,
                    },
                )
                break
        after, after_count = protected_digest(config["protected_paths"])
        if (
            after != before
            or after_count != count
            or runtime_code_hash() != spec["runtime_code_sha256"]
        ):
            raise ValueError("runtime or protected frozen state changed")
        result = {
            "version": VERSION,
            "issue": 182,
            "batches": reports,
            "engineering_pass": True,
            "validated_alpha": False,
            "decision": "FROZEN_HISTORICAL_LEAD" if reports[-1]["winner"] else "NO_LEAD",
            "raw_global_trial_lower_bound": debt + len(reservations),
            "reserved_new_trials": len(reservations),
            "completed_new_trials": sum(len(inventory(p)) * 3 for p in plans[: len(reports)]),
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "spec": spec,
            "protected_unchanged": True,
            "restricted_rows_read": 0,
            "external_llm_calls": 0,
        }
        write_json(output / "RESULT.json", result)
        print(json.dumps({"decision": result["decision"], "output": str(output)}), flush=True)
        return result
    except Exception as exc:
        write_json(output / "ABORTED.json", {"error": str(exc), "reservations_preserved": True})
        raise


def replay_lead(folder):
    folder = Path(folder).resolve()
    original = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    spec = original["spec"]
    if spec["runtime_code_sha256"] != runtime_code_hash():
        raise ValueError("exact replay requires unchanged runtime")
    frozen = json.loads((folder / "FROZEN_LEAD.json").read_text(encoding="utf-8"))
    h = IncrementalHypothesis(**frozen["candidate"]["hypothesis"])
    registry_before = file_sha(folder / "registry.sqlite3")
    inputs = json.loads((folder / "local_input_reference.json").read_text())["path"]
    days, _ = load_frozen_days(Path(inputs))
    output = folder / "replays" / str(uuid4())
    replay = evaluate_batch(days, (h,), output, raw_trials=original["raw_global_trial_lower_bound"])
    actual = replay["candidates"][0]
    if actual != frozen["candidate"]:
        raise ValueError("replayed candidate differs")
    if file_sha(folder / "registry.sqlite3") != registry_before:
        raise ValueError("replay modified trial ledger")
    receipt = {
        "pass": True,
        "candidate": h.identity,
        "account_windows": replay["account_windows"],
        "trial_delta": 0,
        "registry_unchanged": True,
        "original_result_sha256": file_sha(folder / "RESULT.json"),
    }
    write_json(output / "REPLAY_VERIFIED.json", receipt)
    print(json.dumps(receipt), flush=True)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config")
    group.add_argument("--replay")
    args = parser.parse_args()
    if args.replay:
        replay_lead(args.replay)
    else:
        run_incremental_epoch(args.config)


if __name__ == "__main__":
    main()
