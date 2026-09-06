"""Independent saved-account SQL/cash/ledger audit. Does not rerun market data."""

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

import duckdb

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/risk-stratified/epoch-001")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def near(a, b, why, tol=1e-6):
    if not math.isclose(a, b, abs_tol=tol, rel_tol=1e-10):
        raise ValueError(why)


def audit():
    result = read(ROOT / "RESULT.json")
    spec = result["spec"]
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    with duckdb.connect() as conn:
        data = conn.execute(query)
        columns = [x[0] for x in data.description]
        sql = {r[0]: dict(zip(columns, r, strict=True)) for r in data.fetchall()}
    if len(sql) != 32 or set(sql) != set(result["records"]):
        raise ValueError("all32 accounts required")
    rows, max_balance = [], 0.0
    for key, record in result["records"].items():
        path = ROOT / "accounts" / f"{key}.jsonl"
        if file_sha(path) != record["account_sha256"]:
            raise ValueError("account hash changed")
        target_key = record["group"] + "-" + record["policy"]
        targets = read(ROOT / "targets" / f"{target_key}.json")
        if (
            sha256_json(targets) != record["target_sha256"]
            or sha256_json(targets) != result["targets_sha256"][target_key]
        ):
            raise ValueError("target hash changed")
        daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(daily) != 484 or [d["date"] for d in daily] != [t["trade_date"] for t in targets]:
            raise ValueError("continuous calendar failed")
        nav, cash, traded, tickets, max_weight = 3e6, 3e6, 0.0, 0, 0.0
        for d, t in zip(daily, targets, strict=True):
            if d["date"][:4] not in ("2023", "2024") or datetime.fromisoformat(
                t["decided_at"]
            ) >= datetime.fromisoformat(d["date"] + "T09:30:00+08:00"):
                raise ValueError("timing/scope failed")
            if sum(t["weights"].values()) > 1 + 1e-10 or any(
                w < 0 or w > 0.025 for w in t["weights"].values()
            ):
                raise ValueError("target weights failed")
            residual = abs(d["nav"] - d["cash"] - sum(m["market_value"] for m in d["positions"]))
            max_balance = max(max_balance, residual)
            if residual > 1e-5 or d["cash"] < -1e-7:
                raise ValueError("balance failed")
            near(d["return"], d["nav"] / nav - 1, "daily return", 1e-12)
            near(
                d["cash"],
                cash - sum(o["executed_notional"] + o["total_cost"] for o in d["orders"]),
                "cashflow",
            )
            near(d["cost"], sum(o["total_cost"] for o in d["orders"]), "cost sum")
            for o in d["orders"]:
                n = o["executed_notional"]
                near(
                    o["total_cost"],
                    abs(n) * record["scale"] * (36 + (10 if n < 0 else 0)) / 10000,
                    "fee formula",
                )
                if abs(n) > o["capacity_notional"] + 1e-6:
                    raise ValueError("capacity exceeded")
                traded += abs(n)
                tickets += abs(n) > 1e-8
            for m in d["positions"]:
                near(m["market_value"], m["shares"] * m["mark_price"], "marked shares")
                max_weight = max(max_weight, m["market_value"] / d["nav"])
            nav, cash = d["nav"], d["cash"]
        years = {
            y: math.prod(1 + d["return"] for d in daily if d["date"].startswith(y)) - 1
            for y in ("2023", "2024")
        }
        for y, v in years.items():
            near(v, record["years"][y], "annual return", 1e-12)
        sd = stdev(d["return"] for d in daily)
        sr = mean(d["return"] for d in daily) / sd * math.sqrt(252) if sd else 0
        near(sr, record["pooled_sharpe"], "Sharpe", 1e-10)
        if [d["return"] for d in daily] != record["daily_returns"]:
            raise ValueError("return vector changed")
        for col, metric in (
            ("final_nav", "final_nav"),
            ("net_return", "net_total_return"),
            ("cost_cny", "total_cost"),
            ("max_drawdown", "max_drawdown"),
        ):
            near(sql[key][col], record["metrics"][metric], "SQL metric")
        execution = {
            "traded_cny": traded,
            "executed_tickets": tickets,
            "max_close_weight": max_weight,
            "mean_cash_fraction": mean(d["cash"] / d["nav"] for d in daily),
        }
        for k, v in execution.items():
            near(v, record["execution"][k], "execution metric")
        rows.append(
            {
                **sql[key],
                "group": record["group"],
                "policy": record["policy"],
                "roundtrip_bps": record["roundtrip_bps"],
                "return2023": years["2023"],
                "return2024": years["2024"],
                "sharpe": sr,
                **execution,
            }
        )
    by_key = {r["account_key"]: r for r in rows}
    for row in rows:
        if row["group"] != "anchor":
            for comparator in ("hash", "price_reversal"):
                control = by_key[f"{row['group']}-{comparator}-{row['roundtrip_bps']}"]
                row["increment_vs_" + comparator] = row["net_return"] - control["net_return"]
            row["increment_vs_lowvol"] = (
                row["net_return"] - by_key[f"anchor-lowvol-{row['roundtrip_bps']}"]["net_return"]
            )
    for identity, cost_checks in result["checks"].items():
        group, _policy = identity.split("-", 1)
        for cost, expected in cost_checks.items():
            a = by_key[f"{identity}-{cost}"]
            controls = [by_key[f"{group}-{p}-{cost}"] for p in ("hash", "price_reversal")] + [
                by_key[f"anchor-lowvol-{cost}"]
            ]
            computed = {
                "accounts": True,
                "both_years_positive": a["return2023"] > 0 and a["return2024"] > 0,
                "sharpe": a["sharpe"] >= 0.7,
                "drawdown": a["max_drawdown"] >= -0.25,
                "total_increment": all(a["net_return"] - c["net_return"] >= 0.03 for c in controls),
                "annual_increment": all(
                    a["return" + y] - c["return" + y] >= -0.05
                    for c in controls
                    for y in ("2023", "2024")
                ),
            }
            if expected != computed:
                raise ValueError("independent screen mismatch")
        if result["screen_survived"][identity] != all(
            all(v.values()) for v in cost_checks.values()
        ):
            raise ValueError("screen aggregation mismatch")
    with sqlite3.connect(
        f"file:{(ROOT / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as conn:
        native = conn.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(native) != 32 or conn.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("native no-fit contract failed")
        seen = set()
        for plan_text, row_text, stages, runtime in native:
            plan = json.loads(plan_text)
            if (
                plan not in spec["plans"]
                or stages != "[]"
                or runtime != spec["runtime_code_sha256"]
                or json.loads(row_text) != result["records"][plan["key"]]
            ):
                raise ValueError("native lineage/result mismatch")
            seen.add(plan["key"])
        if seen != set(sql):
            raise ValueError("incomplete native trial set")
    reservations = read(ROOT / "first_read_reservations.json")
    if reservations["trials"] != spec["plans"] or reservations["spec_sha256"] != sha256_json(spec):
        raise ValueError("reservation mismatch")
    if (
        result["raw_global_trial_lower_bound"] != 3366
        or result["completed_trials"] != 32
        or result["validated_alpha"]
    ):
        raise ValueError("debt or certificate mismatch")
    diagnostics = read(ROOT / "selection_diagnostics.json")
    detail_summary = {}
    for key, decisions in diagnostics.items():
        if len(decisions) != sum(t["rebalance"] for t in read(ROOT / "targets" / f"{key}.json")):
            raise ValueError("selection diagnostics incomplete")
        if any(
            d["selected"] != sum(c["selected"] for c in d["cells"])
            or any(c["selected"] != min(10, c["eligible"]) for c in d["cells"])
            for d in decisions
        ):
            raise ValueError("selection quotas failed")
        detail_summary[key] = {
            "decisions": len(decisions),
            "new_members": sum(d["new_members"] for d in decisions),
            "mean_volatility20": mean(d["mean_volatility20"] for d in decisions),
            "mean_ADV_cny": mean(d["mean_ADV_cny"] for d in decisions),
            "min_eligible": min(sum(c["eligible"] for c in d["cells"]) for d in decisions),
            "max_eligible": max(sum(c["eligible"] for c in d["cells"]) for d in decisions),
        }
    summary = {
        "version": result["version"],
        "rows": rows,
        "selection": detail_summary,
        "checks": result["checks"],
        "screen_survived": result["screen_survived"],
        "raw_trial_lower_bound": 3366,
        "new_trials": 32,
        "validated_alpha": False,
        "independent_account_sql_ledger_pass": True,
        "maximum_balance_residual_cny": max_balance,
        "source_result_sha256": file_sha(ROOT / "RESULT.json"),
        "snapshot_sha256": spec["snapshot_sha256"],
        "statistics": result["statistics"],
        "restricted_rows_read": 0,
    }
    write_json(
        ROOT / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "query": query,
            "summary": summary,
            "evidence_hashes": {
                p.relative_to(ROOT).as_posix(): file_sha(p) for p in ROOT.rglob("*") if p.is_file()
            },
        },
    )
    write_json(Path("docs/V11_14_RESULT.summary.json"), summary)
    print(json.dumps({"audit": True, "screen_survived": summary["screen_survived"]}))
    return summary


if __name__ == "__main__":
    audit()
