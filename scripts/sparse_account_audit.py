"""Independent saved-account SQL/cash/ledger audit. Does not rerun market data."""

import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

import duckdb

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def near(a, b, why, tol=1e-6):
    if not math.isclose(a, b, abs_tol=tol, rel_tol=1e-10):
        raise ValueError(why)


def audit_accounts(ROOT, result, *, expected_accounts=50):
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    with duckdb.connect() as conn:
        data = conn.execute(query)
        columns = [x[0] for x in data.description]
        sql = {r[0]: dict(zip(columns, r, strict=True)) for r in data.fetchall()}
    if len(sql) != expected_accounts or set(sql) != set(result["records"]):
        raise ValueError("all predeclared accounts required")
    rows, max_balance = [], 0.0
    for key, record in result["records"].items():
        path = ROOT / "accounts" / f"{key}.jsonl"
        if file_sha(path) != record["account_sha256"]:
            raise ValueError("account hash changed")
        target_key = key.rsplit("-", 1)[0]
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
            "max_actual_positions": max(len(d["positions"]) for d in daily),
            "end_positions": len(daily[-1]["positions"]),
        }
        for k, v in execution.items():
            near(v, record["execution"][k], "execution metric")
        rows.append(
            {
                **sql[key],
                "identity": record["identity"],
                "policy": record["policy"],
                "roundtrip_bps": record["roundtrip_bps"],
                "return2023": years["2023"],
                "return2024": years["2024"],
                "sharpe": sr,
                **execution,
            }
        )
    return rows, max_balance
