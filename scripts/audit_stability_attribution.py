"""Independent saved-account / SQL / native ledger audit; no market rerun."""

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

ROOT = Path("artifacts/stability-attribution/epoch-001")


def near(a, b, message, tol=1e-6):
    if not math.isclose(a, b, abs_tol=tol, rel_tol=1e-10):
        raise ValueError(message)


def audit():
    result = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    spec = result["spec"]
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    with duckdb.connect() as c:
        data = c.execute(query)
        cols = [x[0] for x in data.description]
        sql = {r[0]: dict(zip(cols, r, strict=True)) for r in data.fetchall()}
    if set(sql) != set(result["records"]) or len(sql) != 12:
        raise ValueError("twelve complete accounts required")
    rows, maximum = [], 0.0
    for key, record in result["records"].items():
        path = ROOT / "accounts" / f"{key}.jsonl"
        if file_sha(path) != record["account_sha256"]:
            raise ValueError("account byte hash mismatch")
        targets = json.loads(
            (ROOT / "targets" / f"{record['policy']}.json").read_text(encoding="utf-8")
        )
        if sha256_json(targets) != spec["targets_sha256"][record["policy"]]:
            raise ValueError("target canonical hash mismatch")
        daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if [t["trade_date"] for t in targets] != [d["date"] for d in daily] or len(daily) != 484:
            raise ValueError("continuous calendar mismatch")
        nav, cash, ticket_count, traded = 3_000_000.0, 3_000_000.0, 0, 0.0
        max_weight, over = 0.0, 0
        for d, target in zip(daily, targets, strict=True):
            if d["date"][:4] not in {"2023", "2024"} or datetime.fromisoformat(
                target["decided_at"]
            ) >= datetime.fromisoformat(d["date"] + "T09:30:00+08:00"):
                raise ValueError("temporal scope failed")
            if sum(target["weights"].values()) > 1 + 1e-10 or any(
                w < 0 or w > 0.025 for w in target["weights"].values()
            ):
                raise ValueError("declared target exposure failed")
            residual = abs(d["nav"] - d["cash"] - sum(m["market_value"] for m in d["positions"]))
            maximum = max(maximum, residual)
            if residual > 1e-5 or d["cash"] < -1e-7:
                raise ValueError("cash/marked NAV balance failed")
            near(d["nav"] / nav - 1, d["return"], "daily return", 1e-12)
            near(
                d["cash"],
                cash - sum(o["executed_notional"] + o["total_cost"] for o in d["orders"]),
                "cash flow",
            )
            near(d["cost"], sum(o["total_cost"] for o in d["orders"]), "order cost")
            for order in d["orders"]:
                n = order["executed_notional"]
                near(
                    order["total_cost"],
                    abs(n) * record["scale"] * (36 + (10 if n < 0 else 0)) / 10000,
                    "fee formula",
                )
                if abs(n) > order["capacity_notional"] + 1e-6:
                    raise ValueError("capacity exceeded")
                ticket_count += abs(n) > 1e-8
                traded += abs(n)
            for m in d["positions"]:
                near(m["market_value"], m["shares"] * m["mark_price"], "share mark")
                weight = m["market_value"] / d["nav"]
                max_weight = max(max_weight, weight)
                over += weight > 0.025 + 1e-10
            nav, cash = d["nav"], d["cash"]
        if [d["return"] for d in daily] != record["daily_returns"]:
            raise ValueError("return vector mismatch")
        years = {
            y: math.prod(1 + d["return"] for d in daily if d["date"].startswith(y)) - 1
            for y in ("2023", "2024")
        }
        for y, v in years.items():
            near(v, record["years"][y], "annual return", 1e-12)
        sr = mean(d["return"] for d in daily) / stdev(d["return"] for d in daily) * math.sqrt(252)
        near(sr, record["pooled_sharpe"], "Sharpe", 1e-10)
        for column, metric in (
            ("final_nav", "final_nav"),
            ("net_return", "net_total_return"),
            ("cost_cny", "total_cost"),
            ("max_drawdown", "max_drawdown"),
        ):
            near(sql[key][column], record["metrics"][metric], "SQL metric")
        execution = record["execution"]
        for a, b in (
            (ticket_count, execution["executed_tickets"]),
            (traded, execution["traded_cny"]),
            (max_weight, execution["max_close_weight"]),
            (over, execution["close_position_days_above_2_5pct"]),
        ):
            near(a, b, "execution summary")
        cash_fraction = mean(d["cash"] / d["nav"] for d in daily)
        near(cash_fraction, execution["mean_cash_fraction"], "cash exposure")
        rows.append(
            {
                **sql[key],
                "policy": record["policy"],
                "mode": record["mode"],
                "roundtrip_bps": record["roundtrip_bps"],
                "return2023": years["2023"],
                "return2024": years["2024"],
                "sharpe": sr,
                **execution,
            }
        )
    with sqlite3.connect(f"file:{(ROOT / 'registry.sqlite3').as_posix()}?mode=ro", uri=True) as c:
        native = c.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version FROM trials t JOIN trial_fit_contracts c USING(trial_id) JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(native) != 12 or c.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("native no-fit contracts failed")
        keys = set()
        for plan_text, output_text, stages, runtime in native:
            plan = json.loads(plan_text)
            if (
                plan not in spec["plans"]
                or stages != "[]"
                or runtime != spec["runtime_code_sha256"]
            ):
                raise ValueError("native lineage failed")
            if json.loads(output_text) != result["records"][plan["key"]]:
                raise ValueError("native saved result failed")
            keys.add(plan["key"])
        if keys != set(sql):
            raise ValueError("native keys incomplete")
    reservation = json.loads((ROOT / "first_read_reservations.json").read_text(encoding="utf-8"))
    if reservation["trials"] != spec["plans"] or reservation["spec_sha256"] != sha256_json(spec):
        raise ValueError("first-read budget mismatch")
    if (
        result["raw_global_trial_lower_bound"] != 3334
        or result["completed_trials"] != 12
        or result["validated_alpha"]
    ):
        raise ValueError("debt or certificate failed")
    # Recompute the factorial contrasts from independently queried account NAVs.
    for cost in (0, 82, 164):
        s_full = sql[f"stable_lowrisk-full_target-{cost}"]["net_return"]
        l_full = sql[f"lowvol-full_target-{cost}"]["net_return"]
        s_change = sql[f"stable_lowrisk-target_changes-{cost}"]["net_return"]
        l_change = sql[f"lowvol-target_changes-{cost}"]["net_return"]
        a = result["attribution"][str(cost)]
        near(a["membership_increment"]["full_target"], s_full - l_full, "membership contrast")
        near(
            a["membership_increment"]["target_changes"], s_change - l_change, "membership contrast"
        )
        near(
            a["maintenance_increment"]["stable_lowrisk"], s_change - s_full, "maintenance contrast"
        )
        near(a["maintenance_increment"]["lowvol"], l_change - l_full, "maintenance contrast")
        near(a["interaction"], s_change - l_change - s_full + l_full, "factorial interaction")
    for key, drag in result["attribution"]["cost_path_drag"].items():
        zero_key = key.rsplit("-", 1)[0] + "-0"
        near(drag, sql[zero_key]["net_return"] - sql[key]["net_return"], "full path cost drag")
    # Independently rederive the matched screens; zero-cost is never a deployment gate.
    for mode in ("full_target", "target_changes"):
        for cost in (82, 164):
            a, b = (
                next(
                    x
                    for x in rows
                    if x["mode"] == mode and x["roundtrip_bps"] == cost and x["policy"] == p
                )
                for p in ("stable_lowrisk", "lowvol")
            )
            check = {
                "accounts": True,
                "both_years_positive": a["return2023"] > 0 and a["return2024"] > 0,
                "sharpe": a["sharpe"] >= 0.7,
                "drawdown": a["max_drawdown"] >= -0.25,
                "total_increment": a["net_return"] - b["net_return"] >= 0.03,
                "annual_increment": all(
                    a["return" + y] - b["return" + y] >= -0.05 for y in ("2023", "2024")
                ),
            }
            if check != result["checks"][mode][str(cost)]:
                raise ValueError("screen mismatch")
        if result["screen_survived"][mode] != all(
            all(c.values()) for c in result["checks"][mode].values()
        ):
            raise ValueError("screen aggregation mismatch")
    summary = {
        "version": result["version"],
        "rows": rows,
        "checks": result["checks"],
        "screen_survived": result["screen_survived"],
        "attribution": result["attribution"],
        "raw_trial_lower_bound": 3334,
        "new_trials": 12,
        "validated_alpha": False,
        "independent_account_sql_ledger_pass": True,
        "maximum_balance_residual_cny": maximum,
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
    write_json(Path("docs/V11_13_RESULT.summary.json"), summary)
    return summary


if __name__ == "__main__":
    s = audit()
    print(json.dumps({"pass": True, "accounts": len(s["rows"]), "screen": s["screen_survived"]}))
