"""Independent arithmetic, saved-target and trial audit. Does not read market inputs."""

import argparse
import json
import math
import sqlite3
from pathlib import Path
from statistics import mean, stdev

import duckdb

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.fit_lineage import digest
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json


def audit(folder):
    r = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace(
            "__ACCOUNT_GLOB__", (folder / "accounts" / "*.jsonl").as_posix().replace("'", "''")
        )
    )
    with duckdb.connect() as con:
        cur = con.execute(query)
        cols = [c[0] for c in cur.description]
        sql_rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    sql = {row["account_key"]: row for row in sql_rows}
    expected, rows, maximum = set(), [], 0.0
    for policy, costs in r["records"].items():
        targets = json.loads((folder / "targets" / (policy + ".json")).read_text(encoding="utf-8"))
        for t in targets:
            if t["rebalance"] and t["decided_at"][:10] >= t["trade_date"]:
                raise ValueError("target chronology failed")
            if sum(t["weights"].values()) > 1 + 1e-10 or any(
                w < 0 or w > 0.025 + 1e-10 for w in t["weights"].values()
            ):
                raise ValueError("target leverage/position limit failed")
        for cost, row in costs.items():
            key = f"{policy}-{cost}"
            expected.add(key)
            path = folder / "accounts" / (key + ".jsonl")
            if (
                file_sha(path) != row["account_sha256"]
                or sha256_json(targets) != row["targets_sha256"]
            ):
                raise ValueError("account or target hash changed")
            daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            nav = 3_000_000.0
            for d in daily:
                error = abs(d["nav"] - d["cash"] - sum(p["market_value"] for p in d["positions"]))
                maximum = max(maximum, error)
                if error > 1e-5 or d["cash"] < -1e-7:
                    raise ValueError("cash/positions reconciliation failed")
                if not math.isclose(d["return"], d["nav"] / nav - 1, abs_tol=1e-12):
                    raise ValueError("continuous NAV return failed")
                if not math.isclose(
                    sum(o["total_cost"] for o in d["orders"]), d["cost"], abs_tol=1e-6
                ):
                    raise ValueError("cost reconciliation failed")
                commission, tax, slippage = (
                    (3, 5, 15) if cost == "41" else (6, 10, 30 if cost == "82" else 40)
                )
                for o in d["orders"]:
                    n = o["executed_notional"]
                    expected_fee = abs(n) * (commission + slippage + (tax if n < 0 else 0)) / 10000
                    if not math.isclose(expected_fee, o["total_cost"], abs_tol=1e-7):
                        raise ValueError("registered fee rate mismatch")
                nav = d["nav"]
            if [d["return"] for d in daily] != row["daily_returns"] or [
                d["date"] for d in daily
            ] != row["dates"]:
                raise ValueError("dates/returns mismatch")
            if [t["trade_date"] for t in targets] != row["dates"] or len(daily) != sql[key][
                "sessions"
            ]:
                raise ValueError("target/session alignment failed")
            for y in ("2023", "2024"):
                annual = math.prod(1 + d["return"] for d in daily if d["date"].startswith(y)) - 1
                if not math.isclose(annual, row["years"][y], abs_tol=1e-12):
                    raise ValueError("annual return mismatch")
            values = [d["return"] for d in daily]
            sr = mean(values) / stdev(values) * math.sqrt(252) if stdev(values) > 0 else 0
            if not math.isclose(sr, row["pooled_sharpe"], abs_tol=1e-10):
                raise ValueError("independent Sharpe mismatch")
            for s, p in (
                ("final_nav", "final_nav"),
                ("net_return", "net_total_return"),
                ("cost_cny", "total_cost"),
                ("max_drawdown", "max_drawdown"),
            ):
                if not math.isclose(sql[key][s], row["metrics"][p], abs_tol=1e-6):
                    raise ValueError("independent SQL mismatch")
            base, hashed = r["records"]["lowvol"][cost], r["records"]["stable_lowrisk"][cost]
            summary = {
                **sql[key],
                "policy": policy,
                "roundtrip_bps": int(cost),
                "sharpe": sr,
                "return2023": row["years"]["2023"],
                "return2024": row["years"]["2024"],
                "lowvol_return": base["metrics"]["net_total_return"],
                "stable_lowrisk_return": hashed["metrics"]["net_total_return"],
                "increment_lowvol_pp": 100
                * (sql[key]["net_return"] - base["metrics"]["net_total_return"]),
                "increment_hash_pp": 100
                * (sql[key]["net_return"] - hashed["metrics"]["net_total_return"]),
                "start": row["dates"][0],
                "end": row["dates"][-1],
                "hurdle_replacements": sum(
                    v["hurdle_replacements"] for v in r["target_diagnostics"][policy]
                ),
                "mean_selected_per_cohort": mean(
                    v["selected"] for v in r["target_diagnostics"][policy]
                ),
                "mean_coverage": mean(v["matched"] for v in r["target_diagnostics"][policy]),
            }
            rows.append(summary)
            if policy in r["checks"] and cost in r["checks"][policy]:
                checks = {
                    "both_years_positive": summary["return2023"] > 0 and summary["return2024"] > 0,
                    "sharpe": sr >= 0.7,
                    "drawdown": summary["max_drawdown"] >= -0.25,
                    "lowvol_increment": summary["increment_lowvol_pp"] >= 3,
                    "stable_lowrisk_increment": summary["increment_hash_pp"] >= 3,
                    "annual_increment": all(
                        row["years"][y] - base["years"][y] >= -0.05 for y in ("2023", "2024")
                    ),
                    "account": True,
                }
                if checks != r["checks"][policy][cost]:
                    raise ValueError("independent economic gate mismatch")
    if set(sql) != expected or len(sql) != 15:
        raise ValueError("missing or extra accounts")
    for year, model in r["models"].items():
        if not model["maximum_label_end"] <= model["fit_cutoff"] < f"{year}-01-01":
            raise ValueError("model maturity failed")
        if model != json.loads((folder / "models" / f"{year}.json").read_text(encoding="utf-8")):
            raise ValueError("saved model mismatch")
    with sqlite3.connect(
        f"file:{(folder / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as con:
        n = con.execute("select count(*) from trials").fetchone()[0]
        trials = con.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,c.stages_json,e.code_version,s.snapshot_sha256 "
            "FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id) "
            "JOIN data_snapshots s ON s.snapshot_id=e.dataset_snapshot_id"
        ).fetchall()
        if len(trials) != n:
            raise ValueError("every new Trial requires native contract")
        native = json.loads((folder / "NATIVE_FIT_LINEAGE.json").read_text(encoding="utf-8"))
        if file_sha(folder / "NATIVE_FIT_LINEAGE.json") != r["native_fit_lineage_sha256"]:
            raise ValueError("native lineage artifact changed")
        native_count = 0
        for tid, plan_text, result_text, stage_text, code, snapshot in trials:
            plan, stages = json.loads(plan_text), json.loads(stage_text)
            fit_rows = con.execute(
                "SELECT evidence_json,evidence_sha256 FROM trial_model_fits WHERE trial_id=? ORDER BY stage_id",
                (tid,),
            ).fetchall()
            fits = [json.loads(f[0]) for f in fit_rows]
            if {f["stage"]["stage_id"] for f in fits} != {s["stage_id"] for s in stages}:
                raise ValueError("native stage completeness failed")
            for fit, (_, hashed) in zip(fits, fit_rows, strict=True):
                stage = fit["stage"]
                year = stage["stage_id"]
                model = r["models"][year]
                if (
                    digest(fit) != hashed
                    or fit["artifact_sha256"] != file_sha(folder / "models" / f"{year}.json")
                    or fit["model_content_sha256"] != digest(model)
                    or fit["training_signal_sessions"] != model["training_signal_sessions"]
                    or fit["training_end"] != model["fit_cutoff"]
                    or fit["maximum_label_end"] != model["maximum_label_end"]
                    or fit["code_version"] != code
                    or code != r["spec"]["runtime_code_sha256"]
                    or fit["snapshot_sha256"] != snapshot
                    or not stage["training_not_before"]
                    <= fit["training_start"]
                    <= fit["training_end"]
                    <= stage["training_not_after"]
                    < stage["prediction_start"]
                ):
                    raise ValueError("native fit contents/hash/scope failed")
            bound = {"stages": stages, "fits": fits, "sha256": digest(fits)}
            if native[plan["identity"]] != bound:
                raise ValueError("SQL and native artifact mismatch")
            if plan["kind"] == "fit":
                expected_result = r["models"][str(plan["year"])]["models"][plan["policy"]]
            else:
                expected_result = r["records"][plan["policy"]][str(plan["cost_bps"])]
                if expected_result["fit_lineage_sha256"] != bound["sha256"]:
                    raise ValueError("account did not bind native fit")
            if json.loads(result_text) != expected_result:
                raise ValueError("registered Trial result differs from financial/model result")
            native_count += len(fits)
        if native_count != 24:
            raise ValueError("expected24 native model bindings")
    reservations = json.loads(
        (folder / "first_read_reservations.json").read_text(encoding="utf-8")
    )["trials"]
    if (
        n != 21
        or n != len(reservations)
        or n != r["completed_new_trials"]
        or r["raw_global_trial_lower_bound"] != 3289 + n
    ):
        raise ValueError("model/account reservation mismatch")
    summary = {
        "version": r["version"],
        "issue": 184,
        "decision": r["decision"],
        "rows": rows,
        "survivors": r["survivors"],
        "models": r["models"],
        "checks": r["checks"],
        "statistics": {
            k: v for k, v in r["statistics"].items() if k not in ("folds", "split_manifest")
        },
        "placebo": r["placebo"],
        "statistical_scope": r["statistical_scope"],
        "account_windows": 15,
        "new_trials": n,
        "raw_global_trial_lower_bound": 3310,
        "independent_sql_and_gate_pass": True,
        "native_model_bindings": native_count,
        "native_fit_lineage_sha256": r["native_fit_lineage_sha256"],
        "distinct_nonzero_active_paths": r["distinct_nonzero_active_paths"],
        "maximum_balance_residual_cny": maximum,
        "source_result_sha256": file_sha(folder / "RESULT.json"),
        "snapshot_sha256": r["spec"]["snapshot_sha256"],
        "runtime_code_sha256": r["spec"]["runtime_code_sha256"],
        "restricted_rows_read": r["restricted_rows_read"],
        "protected_unchanged": r["protected_unchanged"],
        "validated_alpha": False,
    }
    write_json(
        folder / "INDEPENDENT_AUDIT.json", {"pass": True, "query": query, "summary": summary}
    )
    write_json(Path("docs/V11_11_RESULT.summary.json"), summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    summary = audit(Path(parser.parse_args().operation))
    print(
        json.dumps(
            {k: summary[k] for k in ("decision", "account_windows", "new_trials", "survivors")}
        )
    )
