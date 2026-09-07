"""Independently reconcile frozen allocation stresses; read saved evidence only."""

import json
import math
import sqlite3
from pathlib import Path
from statistics import mean, stdev

import duckdb

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/stability-challenge/epoch-001")
PARENT = Path("artifacts/temporal-increments/epoch-001")


def audit():
    r = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    with duckdb.connect() as con:
        cursor = con.execute(query)
        cols = [d[0] for d in cursor.description]
        sql = {row[0]: dict(zip(cols, row, strict=True)) for row in cursor.fetchall()}
    expected = {f"{c}-{p}" for c, policies in r["records"].items() for p in policies}
    if set(sql) != expected or len(sql) != 10:
        raise ValueError("all ten accounts required")
    rows, maximum = [], 0.0
    for c in r["spec"]["scenarios"]:
        name = c["name"]
        for policy, account in r["records"][name].items():
            key = f"{name}-{policy}"
            targets = json.loads((ROOT / "targets" / (key + ".json")).read_text(encoding="utf-8"))
            parent_targets = json.loads(
                (PARENT / "targets" / (policy + ".json")).read_text(encoding="utf-8")
            )
            if len(targets) != len(parent_targets):
                raise ValueError("target length changed")
            for i, t in enumerate(targets):
                lag = c["delay_sessions"]
                if i >= lag:
                    expected_t = {
                        **parent_targets[i - lag],
                        "trade_date": parent_targets[i]["trade_date"],
                    }
                    if t != expected_t:
                        raise ValueError("target is not exact frozen schedule plus declared delay")
                elif t["weights"] or t["rebalance"] or t["forced_exits"]:
                    raise ValueError("delayed initial target must be inactive cash")
                if t["rebalance"] and t["decided_at"][:10] >= t["trade_date"]:
                    raise ValueError("target temporal ordering failed")
                if sum(t["weights"].values()) > 1 + 1e-10 or any(
                    w < 0 or w > 0.025 + 1e-10 for w in t["weights"].values()
                ):
                    raise ValueError("target exposure limit failed")
            path = ROOT / "accounts" / (key + ".jsonl")
            if (
                file_sha(path) != account["account_sha256"]
                or sha256_json(targets) != account["targets_sha256"]
            ):
                raise ValueError("account/target hash failed")
            daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            nav = 3_000_000.0
            for d in daily:
                residual = abs(
                    d["nav"] - d["cash"] - sum(p["market_value"] for p in d["positions"])
                )
                maximum = max(maximum, residual)
                if residual > 1e-5 or d["cash"] < -1e-7:
                    raise ValueError("account balance failed")
                if not math.isclose(d["return"], d["nav"] / nav - 1, abs_tol=1e-12):
                    raise ValueError("NAV/return failed")
                if not math.isclose(
                    d["cost"], sum(o["total_cost"] for o in d["orders"]), abs_tol=1e-6
                ):
                    raise ValueError("daily/order costs failed")
                for o in d["orders"]:
                    n = o["executed_notional"]
                    fee = abs(n) * (6 + 30 + c["extra_slippage_bps"] + (10 if n < 0 else 0)) / 10000
                    if not math.isclose(fee, o["total_cost"], abs_tol=1e-7):
                        raise ValueError("declared fee rate failed")
                    if abs(n) > o["capacity_notional"] + 1e-6:
                        raise ValueError("recorded order capacity exceeded")
                nav = d["nav"]
            if [d["return"] for d in daily] != account["daily_returns"] or [
                d["date"] for d in daily
            ] != account["dates"]:
                raise ValueError("return/date vector failed")
            if [t["trade_date"] for t in targets] != account["dates"]:
                raise ValueError("target/account alignment failed")
            for y in ("2023", "2024"):
                annual = math.prod(1 + d["return"] for d in daily if d["date"].startswith(y)) - 1
                if not math.isclose(annual, account["years"][y], abs_tol=1e-12):
                    raise ValueError("annual compounding failed")
            values = account["daily_returns"]
            sr = mean(values) / stdev(values) * math.sqrt(252)
            if not math.isclose(sr, account["pooled_sharpe"], abs_tol=1e-10):
                raise ValueError("independent Sharpe failed")
            for field, metric in (
                ("final_nav", "final_nav"),
                ("net_return", "net_total_return"),
                ("cost_cny", "total_cost"),
                ("max_drawdown", "max_drawdown"),
            ):
                if not math.isclose(sql[key][field], account["metrics"][metric], abs_tol=1e-6):
                    raise ValueError("independent SQL failed")
            base = r["records"][name]["lowvol"]
            row = {
                **sql[key],
                "scenario": name,
                "policy": policy,
                "roundtrip_bps": 82 + 2 * c["extra_slippage_bps"],
                "capacity_fraction": c["capacity_fraction"],
                "delay_sessions": c["delay_sessions"],
                "return2023": account["years"]["2023"],
                "return2024": account["years"]["2024"],
                "sharpe": sr,
                "lowvol_return": base["metrics"]["net_total_return"],
                "increment_pp": 100
                * (sql[key]["net_return"] - base["metrics"]["net_total_return"]),
            }
            rows.append(row)
            if policy == "stable_lowrisk":
                check = {
                    "account": account["audit"]["pass"] and base["audit"]["pass"],
                    "both_years_positive": row["return2023"] > 0 and row["return2024"] > 0,
                    "sharpe": sr >= 0.7,
                    "drawdown": row["max_drawdown"] >= -0.25,
                    "increment": row["increment_pp"] >= 3,
                    "annual_increment": all(
                        account["years"][y] - base["years"][y] >= -0.05 for y in ("2023", "2024")
                    ),
                }
                if check != r["checks"][name]:
                    raise ValueError("independent gate failed")
    reservations = json.loads((ROOT / "first_read_reservations.json").read_text(encoding="utf-8"))[
        "trials"
    ]
    with sqlite3.connect(f"file:{(ROOT / 'registry.sqlite3').as_posix()}?mode=ro", uri=True) as con:
        trials = con.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(trials) != 10 or con.execute("SELECT COUNT(*) FROM trials").fetchone()[0] != 10:
            raise ValueError("ten native trial contracts required")
        if con.execute("SELECT COUNT(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("no fitting allowed")
        identities = set()
        for plan_text, result_text, stages, code in trials:
            p = json.loads(plan_text)
            if p not in reservations or stages != "[]" or code != r["spec"]["runtime_code_sha256"]:
                raise ValueError("native registration mismatch")
            if json.loads(result_text) != r["records"][p["scenario"]["name"]][p["policy"]]:
                raise ValueError("native result differs from account")
            identities.add(p["identity"])
        if len(identities) != 10:
            raise ValueError("duplicate trial")
    if (
        r["raw_global_trial_lower_bound"] != 3320
        or r["completed_new_trials"] != 10
        or len(reservations) != 10
    ):
        raise ValueError("historical debt failed")
    survived = all(all(c.values()) for c in r["checks"].values())
    if r["stress_survived"] != survived or r["validated_alpha"]:
        raise ValueError("incorrect final classification")
    summary = {
        "version": r["version"],
        "issue": 184,
        "decision": r["decision"],
        "rows": rows,
        "checks": r["checks"],
        "diagnostics": r["diagnostics"],
        "stress_survived": survived,
        "new_trials": 10,
        "raw_trial_lower_bound": 3320,
        "validated_alpha": False,
        "independent_sql_account_target_and_native_trial_pass": True,
        "maximum_balance_residual_cny": maximum,
        "restricted_rows_read": 0,
        "source_result_sha256": file_sha(ROOT / "RESULT.json"),
        "snapshot_sha256": r["spec"]["snapshot_sha256"],
        "statistics": r["statistics"],
    }
    write_json(ROOT / "INDEPENDENT_AUDIT.json", {"pass": True, "query": query, "summary": summary})
    write_json(Path("docs/V11_11_DEEP.summary.json"), summary)
    return summary


if __name__ == "__main__":
    s = audit()
    print(json.dumps({"decision": s["decision"], "accounts": len(s["rows"]), "debt": 3320}))
