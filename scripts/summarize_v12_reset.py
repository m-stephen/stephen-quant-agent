"""Read-only reconciliation of frozen V12 generated results; never run search.

Writes one new aggregate artifact. All inputs are explicit generated result paths;
the script has no warehouse/source connector and is not a calibration decision rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from stephen_quant.discovery.research_reset.contracts import digest
from stephen_quant.discovery.research_reset.runner import read_json, write_new


def summarize(directory):
    directory = Path(directory).resolve()
    result = read_json(directory / "RESULT.json")
    terminal = read_json(directory / "TERMINAL.json")
    if digest(result) != terminal["result_sha256"] or terminal["status"] != "COMPLETE":
        raise ValueError("result/terminal binding mismatch")
    plan = read_json(directory / "PLAN.json")
    if digest(plan["plan"]) != result["plan_sha256"]:
        raise ValueError("plan binding mismatch")
    buckets = defaultdict(list)
    reserved_ids, policy_ids, failures = set(), set(), []
    totals = defaultdict(int)
    for entry in result["completed_paths"]:
        path = directory / "paths" / entry["path"]
        if path.parent != directory / "paths":
            raise ValueError("unexpected path")
        value = read_json(path / "RESULT.json")
        if digest(value) != entry["result_sha256"]:
            raise ValueError("path evidence hash mismatch")
        source = read_json(path / "SOURCE.json")
        if source["snapshot_sha256"] != value["snapshot_sha256"]:
            raise ValueError("source binding mismatch")
        events = [json.loads(x) for x in (path / "ledger.jsonl").read_text().splitlines()]
        if digest(events) != value["ledger_sha256"]:
            raise ValueError("ledger event hash mismatch")
        for account in value["accounts"].values():
            if account["audit"]["status"] != "PASS":
                failures.append(entry["path"])
            # Independent arithmetic cross-check of the stored daily account.
            wealth = math.prod(1 + row[1] for row in account["daily"])
            if not math.isclose(wealth * 3_000_000, account["metrics"]["final_nav"], abs_tol=1e-5):
                raise ValueError("daily returns and final account NAV disagree")
        for key, count in value["counts"].items():
            totals[key] += count
        if reserved_ids.intersection(value["native_trial_ids"]):
            raise ValueError("trial identity reused across independent paths")
        reserved_ids.update(value["native_trial_ids"])
        buckets[value["scenario"]].append(value)
    if dict(totals) != result["counts"] or failures:
        raise ValueError("operation counts/account audits fail reconciliation")
    with sqlite3.connect((directory / "registry.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        stored_ids = {r[0] for r in db.execute("SELECT trial_id FROM trials")}
        for row in db.execute("SELECT hyperparams FROM trials"):
            payload = json.loads(row[0])
            if not payload["synthetic_only"] or payload["empirical_trial_delta"] != 0:
                raise ValueError("unexpected empirical trial")
            policy_ids.add(payload["policy_id"])
    if stored_ids != reserved_ids or len(stored_ids) != totals["native_trial_records"]:
        raise ValueError("SQLite identities and operation receipts disagree")
    scenarios = []
    for name, rows in buckets.items():
        promoted = sum(r["promoted"] for r in rows)
        planted = not name.endswith("null")
        event_count = sum(
            r["promoted"] and (not planted or r["recovery"]["semantic"]) for r in rows
        )
        receipt = result["scenarios"][name]
        if event_count != receipt["count"] or len(rows) != receipt["n"]:
            raise ValueError("declared calibration numerator/denominator mismatch")
        item = {"scenario": name, **receipt, "promoted_any": promoted}
        if planted:
            item.update(
                {
                    "semantic_recovery_count": sum(r["recovery"]["semantic"] for r in rows),
                    "exact_recovery_count": sum(
                        r["recovery"]["exact_expression_direction"] for r in rows
                    ),
                    "top3_expression_count": sum(r["recovery"]["top3_expression"] for r in rows),
                    "known_expression_net_positive_both": sum(
                        r["oracle_reference"]["positive_net_increment_both_costs"] for r in rows
                    ),
                    "known_expression_gate_pass": sum(
                        r["oracle_reference"]["passes_same_economic_gate"] for r in rows
                    ),
                    "missed_when_reference_passes": sum(
                        r["oracle_reference"]["passes_same_economic_gate"] and not r["promoted"]
                        for r in rows
                    ),
                }
            )
        for cost in (0, 82, 164):
            values = [r["paired"][f"{cost}:risk_only"] for r in rows]
            item[f"mean_paired_daily_bps_{cost}"] = (
                10_000 * math.fsum(v["paired"]["mean"] for v in values) / len(values)
            )
            item[f"positive_mean_count_{cost}"] = sum(v["paired"]["mean"] > 0 for v in values)
            item[f"mean_below_1bp_count_{cost}"] = sum(v["paired"]["mean"] < 0.0001 for v in values)
            item[f"t_below_2_5_count_{cost}"] = sum(
                v["paired"]["t"] is None or v["paired"]["t"] < 2.5 for v in values
            )
            item[f"nonpositive_half_count_{cost}"] = sum(
                min(v["segment_means"]) <= 0 for v in values
            )
            item[f"mean_cost_increment_cny_{cost}"] = math.fsum(
                v["fee_increment_cny"] for v in values
            ) / len(values)
            if planted and cost:
                item[f"known_expression_mean_bps_{cost}"] = (
                    10_000
                    * math.fsum(
                        r["oracle_reference"]["paired"][str(cost)]["paired"]["mean"] for r in rows
                    )
                    / len(rows)
                )
        scenarios.append(item)
    return {
        "version": "12.0.0",
        "scope": result["scope"],
        "calibration": result["calibration"],
        "validated_alpha": False,
        "source_sha256": terminal["result_sha256"],
        "source_file_sha256": hashlib.sha256((directory / "RESULT.json").read_bytes()).hexdigest(),
        "plan_sha256": result["plan_sha256"],
        "pipeline_sha256": result["pipeline_sha256"],
        "elapsed_seconds": terminal["elapsed_seconds"],
        "ended_at": terminal["ended_at"],
        "scenarios": scenarios,
        "counts": result["counts"],
        "native_counts": result["native_counts"],
        "unique_global_policy_identities": len(policy_ids),
        "policy_count_note": "global identities are not source-specific; operation sum is policy-by-source evaluations; neither is independent statistical trials",
        "reconciliation": "PASS_HASH_COUNTS_SQLITE_DAILY_NAV",
        "historical_raw_attempts": result["historical_raw_attempts"],
        "empirical_trial_delta": 0,
        "real_label_authorized": False,
        "court": result["court"],
        "runtime": plan["plan"]["runtime"],
        "diagnostic_limit": "descriptive failure reasons overlap; never remove paths or retune from reserved results",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = summarize(args.run)
    write_new(args.output, summary)
    print(json.dumps(summary, indent=2))
