"""Issue184: immutable, bounded lead challenge with complete reservation accounting."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from stephen_quant.discovery.incremental_alpha import IncrementalHypothesis, audit_account
from stephen_quant.discovery.lead_challenge import (
    CHALLENGES,
    VERSION,
    challenge_assessment,
    challenge_execute,
    lowvol_attribution,
    next_action,
    summarize_account,
    tail_sensitivity,
)
from stephen_quant.discovery.reliable_research import metric_bundle
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


def verify_parent(config):
    folder = Path(config["parent_operation_dir"]).resolve()
    frozen_path = Path(config["frozen_leads_file"]).resolve()
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if file_sha(folder / "RESULT.json") != frozen["source_result_sha256"]:
        raise ValueError("parent result does not match frozen leads")
    parent = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    if parent["raw_global_trial_lower_bound"] < 3058:
        raise ValueError("historical trial debt cannot decrease")
    pack = tuple(IncrementalHypothesis(**lead["hypothesis"]) for lead in frozen["leads"])
    if len(pack) != 2 or [h.identity for h in pack] != [x["identity"] for x in frozen["leads"]]:
        raise ValueError("frozen candidate identities changed")
    reference = json.loads((folder / "local_input_reference.json").read_text(encoding="utf-8"))
    inputs = Path(reference["path"]).resolve()
    manifest = json.loads((inputs / "manifest.json").read_text(encoding="utf-8"))
    if manifest["snapshot_sha256"] != frozen["snapshot_sha256"]:
        raise ValueError("parent snapshot changed")
    return folder, frozen_path, frozen, parent, pack, inputs


def planned_trials(pack):
    # Baseline82 is verified byte-for-byte replay, not another trial. All other
    # execution scenarios, including continuous capital, are new policy attempts.
    return [
        {
            "item": item,
            "challenge": asdict(c),
            "identity": sha256_json(
                {"item": item["identity"], "challenge": asdict(c), "v": VERSION}
            ),
        }
        for c in CHALLENGES
        if c.name != "baseline_82"
        for item in inventory(pack)
    ]


def run_challenge(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    folder, frozen_path, frozen, parent, pack, inputs = verify_parent(config)
    output = Path(config["output_dir"]).resolve()
    if any(output == p or p in output.parents for p in (folder, inputs)):
        raise ValueError("output must be separate from immutable parent and source inputs")
    output.mkdir(parents=True, exist_ok=False)
    protected = [
        frozen_path,
        folder / "RESULT.json",
        folder / "registry.sqlite3",
        folder / "first_read_reservations.json",
        *config["protected_paths"],
    ]
    before, _ = protected_digest(protected)
    plans = planned_trials(pack)
    debt = parent["raw_global_trial_lower_bound"]
    # Resume by NEW operation only, retaining unsuccessful reservations too.
    seen = set()
    predecessors = []
    for value in config.get("prior_challenge_dirs", []):
        p = Path(value).resolve() / "first_read_reservations.json"
        digest = file_sha(p)
        if digest in seen:
            raise ValueError("duplicate predecessor evidence")
        seen.add(digest)
        previous = json.loads(p.read_text(encoding="utf-8"))
        debt += len(previous["trials"])
        predecessors.append({"sha256": digest, "charged_trials": len(previous["trials"])})
        protected.append(p)
    before, _ = protected_digest(protected)
    spec = {
        "version": VERSION,
        "issue": 184,
        "challenges": [asdict(c) for c in CHALLENGES],
        "leads_sha256": file_sha(frozen_path),
        "parent_result_sha256": file_sha(folder / "RESULT.json"),
        "snapshot_sha256": frozen["snapshot_sha256"],
        "runtime_code_sha256": runtime_code_hash(),
        "raw_debt_before": debt,
        "predecessors": predecessors,
        "protected_before": before,
        "diagnostics": {"ols_control": "matched lowvol", "hac_lag": 20, "top_active_days": 5},
        "windows": ["2023", "2024", "continuous2023-2024"],
        "exposure": "historical development only; no2025/2026; no independent holdout",
        "survival": "all five annual scenarios pass the unchanged V11.7 economic screen",
        "validated_alpha": False,
    }
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
                "frozen_lead_challenge",
                "falsify economic leads",
                sid,
                spec["runtime_code_sha256"],
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        trial_ids = {}
        for plan in plans:
            trial_ids[plan["identity"]] = registry.create_trial_deterministic(
                TrialSpec(
                    eid,
                    plan["item"]["name"],
                    plan["item"]["identity"],
                    json.dumps(plan),
                    184,
                    "2022-01-01",
                    "2022-12-31",
                    "2023-01-01",
                    "2023-12-31",
                    "2024-01-01",
                    "2024-12-31",
                ),
                plan["identity"],
            )[0]
        # All thirty new policies are reserved AND registered before market bytes.
        days, quality = load_frozen_days(inputs)
        write_json(output / "DATA_PREFLIGHT.json", quality)
        items = inventory(pack)
        records, results = {}, {}
        total_accounts = 0
        original = parent["batches"][0]
        old_candidates = {r["identity"]: r for r in original["candidates"]}
        for c in CHALLENGES:
            result = {"candidates": {}, "assessments": {}}
            windows = ("continuous2023-2024",) if c.continuous else ("2023", "2024")
            for year in windows:
                window = (
                    tuple(d for d in days if d.date[:4] in ("2023", "2024"))
                    if c.continuous
                    else tuple(d for d in days if d.date.startswith(year))
                )
                if len(window) < (400 if c.continuous else 200):
                    raise ValueError("incomplete frozen research window")
                cache, accounts = {}, {}
                for item in items:
                    h = IncrementalHypothesis(**item["hypothesis"])
                    report, targets, coverage = challenge_execute(window, h, item["kind"], c, cache)
                    if not coverage or not any(row["selected"] for row in coverage):
                        raise ValueError("empty candidate coverage")
                    audit = audit_account(report)
                    label = f"{c.name}-{year}-{item['name']}"
                    digest = save_account(output, label, report)
                    summary = summarize_account(report)
                    summary.update(
                        audit=audit,
                        account_sha256=digest,
                        targets_sha256=sha256_json([asdict(t) for t in targets]),
                    )
                    records[label] = {
                        "scenario": c.name,
                        "window": year,
                        "policy": item["name"],
                        "kind": item["kind"],
                        **summary,
                    }
                    accounts[item["identity"]] = report
                    if c.name == "baseline_82":
                        old = (
                            old_candidates[item["identity"]]["years"][year]["2"]
                            if item["kind"] == "candidate"
                            else original["controls"][item["identity"]][year]["2"]
                        )
                        if (
                            digest != old["account_sha256"]
                            or summary["targets_sha256"] != old["targets_sha256"]
                        ):
                            raise ValueError("baseline replay differs from immutable V11.7")
                    total_accounts += 1
                for h in pack:
                    control = next(
                        i
                        for i in items
                        if i["kind"] == "lowvol" and i["hypothesis"]["field"] == h.field
                    )
                    hashed = next(
                        i
                        for i in items
                        if i["kind"] == "hash" and i["hypothesis"]["field"] == h.field
                    )
                    report, baseline = accounts[h.identity], accounts[control["identity"]]
                    metrics = metric_bundle(report, baseline)
                    metrics.update(
                        hash_control_return=accounts[hashed["identity"]].metrics.net_total_return,
                        audit=audit_account(report),
                    )
                    result["candidates"].setdefault(h.name, {})[year] = metrics
                    if c.name == "baseline_82":
                        metrics["attribution"] = lowvol_attribution(
                            metrics["daily_returns"], metrics["daily_benchmark"]
                        )
                        metrics["tail_sensitivity"] = tail_sensitivity(
                            metrics["daily_returns"], metrics["daily_benchmark"]
                        )
                print(
                    json.dumps({"scenario": c.name, "window": year, "accounts": total_accounts}),
                    flush=True,
                )
            if not c.continuous:
                result["assessments"] = {
                    name: challenge_assessment(years)
                    for name, years in result["candidates"].items()
                }
            results[c.name] = result
            write_json(output / "scenarios" / f"{c.name}.json", result)
            for plan in plans:
                if plan["challenge"]["name"] == c.name:
                    payload = {
                        key: row
                        for key, row in records.items()
                        if row["scenario"] == c.name and row["policy"] == plan["item"]["name"]
                    }
                    registry.record_trial_result(
                        trial_ids[plan["identity"]], json.dumps(payload, sort_keys=True)
                    )
        survivors = [
            h.name
            for h in pack
            if all(
                results[c.name]["assessments"][h.name]["suspected_lead"]
                for c in CHALLENGES
                if not c.continuous
            )
        ]
        if (
            protected_digest(protected)[0] != before
            or runtime_code_hash() != spec["runtime_code_sha256"]
        ):
            raise ValueError("protected parent state or runtime changed")
        final = {
            "version": VERSION,
            "issue": 184,
            "engineering_pass": True,
            "validated_alpha": False,
            "decision": next_action(survivors),
            "stress_survivors": survivors,
            "raw_global_trial_lower_bound": debt + len(plans),
            "reserved_new_trials": len(plans),
            "completed_new_trials": len(plans),
            "baseline_replay_trial_delta": 0,
            "account_windows": total_accounts,
            "records": records,
            "scenarios": results,
            "spec": spec,
            "protected_unchanged": True,
            "restricted_rows_read": 0,
            "parent_court": {"statistics": original["statistics"], "placebo": original["placebo"]},
            "limitations": [
                "adjusted fractional shares, not brokerage ready",
                "ADV proxy is not opening liquidity",
                "postselected historical development",
                "full historical multiplicity not calibrated",
                "no market/industry/size attribution yet",
                "no independent evidence or formal Alpha PASS",
            ],
        }
        write_json(output / "RESULT.json", final)
        print(
            json.dumps(
                {"decision": final["decision"], "survivors": survivors, "output": str(output)}
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    run_challenge(args.config)


if __name__ == "__main__":
    main()
