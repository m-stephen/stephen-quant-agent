"""Read-only independent numerical/ledger reconciliation; no new search trials."""

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.research_reset.contracts import digest
from stephen_quant.discovery.research_reset.runner import read_json, write_new


def compare(actual, expected):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError("independent summary schema mismatch")
        for key in expected:
            compare(actual[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError("independent summary length mismatch")
        for a, e in zip(actual, expected, strict=True):
            compare(a, e)
    elif isinstance(expected, float):
        if not math.isclose(actual, expected, abs_tol=1e-12, rel_tol=1e-12):
            raise ValueError("independent summary numerical mismatch")
    elif actual != expected:
        raise ValueError("independent summary value mismatch")


def reference_look(k, n, kind):
    # Direct probability polynomial and bisection, independently of production
    # lgamma/log-sum-exp implementation. The frozen finite-look budget is .05.
    tail = 0.05 / 24

    def upper(count):
        if count == n:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(60):
            p = (lo + hi) / 2
            cdf = math.fsum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(count + 1))
            if cdf > tail:
                lo = p
            else:
                hi = p
        return hi

    lo, hi = 1 - upper(n - k), upper(k)
    threshold = 0.8 if kind == "power" else 0.05
    passed = lo >= threshold if kind == "power" else hi <= threshold
    failed = hi < threshold if kind == "power" else lo > threshold
    status = "PASS" if passed else "FAIL" if failed else "INCONCLUSIVE" if n == 500 else "CONTINUE"
    return {
        "status": status,
        "n": n,
        "count": k,
        "estimate": k / n,
        "lower": lo,
        "upper": hi,
        "threshold": threshold,
        "kind": kind,
        "one_tail_error": tail,
        "delta_cal": 0.05,
        "method": "exact-binomial-bonferroni-scenarios-looks-two-tails",
    }


def verify_summaries(result, values, output):
    scenes = ("linear", "interaction", "correlated_null", "regime_null")
    counts = {key: sum(v["counts"][key] for v in values) for key in result["counts"]}
    compare(result["counts"], counts)
    if result["mode"] == "audit":
        receipts, expected_looks = {}, set()
        for scene in scenes:
            paths = [v for v in values if v["scenario"] == scene]
            if len(paths) not in (100, 200, 500) or len({p["seed"] for p in paths}) != len(paths):
                raise ValueError("complete independent finite-look scenario required")
            k = 0
            for i, path in enumerate(paths, 1):
                k += bool(
                    path["promoted"] and (scene.endswith("null") or path["recovery"]["semantic"])
                )
                if i in (100, 200, 500):
                    receipt = reference_look(k, i, "fwer" if scene.endswith("null") else "power")
                    filename = f"{scene}-{i}.json"
                    expected_looks.add(filename)
                    compare(read_json(output / "looks" / filename), receipt)
                    if i < len(paths) and receipt["status"] != "CONTINUE":
                        raise ValueError("continued after terminal finite look")
            if receipt["status"] == "CONTINUE":
                raise ValueError("incomplete scenario")
            receipts[scene] = receipt
        if {p.name for p in (output / "looks").glob("*.json")} != expected_looks:
            raise ValueError("unexpected or missing finite look")
        compare(result["scenarios"], receipts)
        states = [r["status"] for r in receipts.values()]
        status = (
            "PASS"
            if all(s == "PASS" for s in states)
            else "FAIL"
            if "FAIL" in states
            else "INCONCLUSIVE"
        )
        compare(result["calibration"], status)
        return {"status": status, "looks_checked": len(expected_looks), "scenarios": receipts}
    cells = []
    for length in (120, 360, 720):
        for strength in (1.0, 0.5):
            for scene in scenes if strength == 1 else scenes[:2]:
                paths = [
                    v
                    for v in values
                    if v["scenario"] == scene
                    and v["spec"]["sessions"] == length + 100
                    and v["spec"]["strength_multiplier"] == strength
                ]
                if len(paths) != 8 or len({p["seed"] for p in paths}) != 8:
                    raise ValueError("all eight development paths required")
                cells.append(
                    {
                        "length": length,
                        "strength_multiplier": strength,
                        "scenario": scene,
                        "n": 8,
                        "promoted": sum(p["promoted"] for p in paths),
                        "semantic_promoted": sum(
                            p["promoted"] and p["recovery"]["semantic"] for p in paths
                        ),
                        "oracle_promoted": sum(
                            p["oracle_reference"].get("passes_same_economic_gate", False)
                            for p in paths
                        ),
                        "net_promoted": sum(p["net_diagnostic"]["promoted"] for p in paths),
                        "mean_net_bps_164": math.fsum(
                            p["paired"]["164:risk_only"]["paired"]["mean"] * 10000 for p in paths
                        )
                        / 8,
                    }
                )
    eligible = [
        n
        for n in (120, 360, 720)
        if all(
            c["promoted"] == 0
            if c["scenario"].endswith("null")
            else c["semantic_promoted"] >= 7 and c["oracle_promoted"] >= 7
            for c in cells
            if c["length"] == n and c["strength_multiplier"] == 1
        )
    ]
    expected = {
        "cells": cells,
        "selected_length": min(eligible) if eligible else None,
        "criterion": "coarse 7/8 development screen; not 80% power evidence",
        "cross_cell_independence": False,
        "primary_policy": "unchanged_gross_search",
    }
    if len(values) != 144:
        raise ValueError("exactly144 development paths required")
    compare(result["design"], expected)
    return {
        "status": "PASS_DEVELOPMENT_SUMMARY",
        "cells_checked": 18,
        "selected_length": expected["selected_length"],
    }


def verify(output):
    output = Path(output).resolve()
    result = read_json(output / "RESULT.json")
    terminal = read_json(output / "TERMINAL.json")
    envelope = read_json(output / "PLAN.json")
    if terminal["status"] != "COMPLETE" or terminal["result_sha256"] != digest(result):
        raise ValueError("terminal/result identity mismatch")
    if (
        envelope["sha256"] != digest(envelope["plan"])
        or result["plan_sha256"] != envelope["sha256"]
    ):
        raise ValueError("plan binding mismatch")
    if result["code"] != envelope["plan"]["code"]:
        raise ValueError("recorded code mismatch")
    for path, expected in result["code"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError("current decision pipeline differs")
    reserved, nav_count, paired_count, values, names = set(), 0, 0, [], set()

    def account(value):
        nonlocal nav_count
        daily = value["daily"]
        days = [p[0] for p in daily]
        if days != sorted(set(days)):
            raise ValueError("account calendar invalid")
        final = 3_000_000 * math.prod(1 + p[1] for p in daily)
        if not math.isclose(final, value["metrics"]["final_nav"], rel_tol=1e-10, abs_tol=1e-5):
            raise ValueError("independent daily-return product differs from NAV")
        nav_count += 1

    def paired(a, b, result):
        nonlocal paired_count
        if [p[0] for p in a] != [p[0] for p in b]:
            raise ValueError("paired calendar mismatch")
        mean = math.fsum(x[1] - y[1] for x, y in zip(a, b, strict=True)) / len(a)
        cash = 3_000_000 * (math.prod(1 + x[1] for x in a) - math.prod(1 + x[1] for x in b))
        if not math.isclose(mean, result["paired"]["mean"], abs_tol=1e-14):
            raise ValueError("paired mean mismatch")
        if not math.isclose(cash, result["increment_cny"], rel_tol=1e-10, abs_tol=1e-5):
            raise ValueError("paired currency mismatch")
        paired_count += 1

    for binding in result["paths"]:
        if binding["path"] in names or Path(binding["path"]).name != binding["path"]:
            raise ValueError("unsafe or duplicated path")
        names.add(binding["path"])
        folder = output / "paths" / binding["path"]
        value = read_json(folder / "RESULT.json")
        values.append(value)
        if digest(value) != binding["sha256"]:
            raise ValueError("path result hash differs")
        source = read_json(folder / "SOURCE.json")
        if any(value[k] != source[k] for k in ("scenario", "seed", "spec", "snapshot_sha256")):
            raise ValueError("source binding mismatch")
        events = [
            json.loads(line)
            for line in (folder / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if digest(events) != value["ledger_sha256"]:
            raise ValueError("event ledger hash mismatch")
        ids = [event["trial_id"] for event in events if event["trial_id"] is not None]
        if (
            ids != value["native_trial_ids"]
            or len(set(ids)) != len(ids)
            or reserved.intersection(ids)
        ):
            raise ValueError("trial identities mismatch/duplicate")
        reserved.update(ids)
        for report in value["accounts"].values():
            account(report)
        for key, comparison in value["paired"].items():
            cost, role = key.split(":")
            paired(
                value["accounts"][f"{cost}:risk_signal"]["daily"],
                value["accounts"][f"{cost}:{role}"]["daily"],
                comparison,
            )
        if "net_diagnostic" in value:
            bundles = [item["evidence"]["accounts"] for item in value["net_diagnostic"]["train"]]
            bundles.append(value["net_diagnostic"]["evaluation"])
            for bundle in bundles:
                for comparison in bundle.values():
                    reports = comparison["accounts"]
                    for report in reports.values():
                        account(report)
                    paired(
                        reports["risk_signal"]["daily"],
                        reports["risk_only"]["daily"],
                        comparison["paired"],
                    )
    with sqlite3.connect((output / "registry.sqlite3").as_uri() + "?mode=ro", uri=True) as conn:
        actual = {row[0] for row in conn.execute("SELECT trial_id FROM trials")}
    if actual != reserved or len(actual) != result["counts"]["native_trials"]:
        raise ValueError("native SQLite registry mismatch")
    summary = verify_summaries(result, values, output)
    return {
        "status": "PASS_HASH_LEDGER_PAIRED_NAV",
        "paths": len(result["paths"]),
        "native_trials": len(actual),
        "recomputed_daily_nav_accounts": nav_count,
        "recomputed_paired_comparisons": paired_count,
        "independent_summary_verification": summary,
        "result_sha256": digest(result),
        "result_file_sha256": hashlib.sha256((output / "RESULT.json").read_bytes()).hexdigest(),
        "limitations": "oracle accounts retain scalar audits, not independent full order reconstruction; no market Alpha",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = verify(args.run)
    write_new(Path(args.output), result)
    print(json.dumps(result, indent=2))
