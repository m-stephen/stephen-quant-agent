"""Independent saved-account SQL/ledger verification and bilingual report evidence."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

import duckdb

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json


def audit(folder):
    result = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    extra_slippage = {
        c["name"]: c["extra_slippage_bps"] for c in result["spec"].get("scenarios", [])
    }
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace(
            "__ACCOUNT_GLOB__", (folder / "accounts" / "*.jsonl").as_posix().replace("'", "''")
        )
    )
    with duckdb.connect() as con:
        cursor = con.execute(query)
        cols = [c[0] for c in cursor.description]
        sql_rows = [dict(zip(cols, r, strict=True)) for r in cursor.fetchall()]
    sql = {r["account_key"]: r for r in sql_rows}
    expected, residual, rows = set(), 0.0, []
    for calendar, policies in result["records"].items():
        for name, costs in policies.items():
            for cost, record in costs.items():
                label = f"{calendar}-{name}-{cost}"
                expected.add(label)
                path = folder / "accounts" / (label + ".jsonl")
                if file_sha(path) != record["account_sha256"]:
                    raise ValueError("account evidence hash changed")
                daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                nav = 3_000_000.0
                for row in daily:
                    error = abs(
                        row["nav"] - row["cash"] - sum(p["market_value"] for p in row["positions"])
                    )
                    residual = max(residual, error)
                    if error > 1e-5 or row["cash"] < -1e-7:
                        raise ValueError("cash/positions/NAV mismatch")
                    if not math.isclose(row["return"], row["nav"] / nav - 1, abs_tol=1e-12):
                        raise ValueError("continuous return mismatch")
                    if not math.isclose(
                        sum(o["total_cost"] for o in row["orders"]), row["cost"], abs_tol=1e-6
                    ):
                        raise ValueError("order costs mismatch")
                    nav = row["nav"]
                if [r["return"] for r in daily] != record["daily_returns"] or [
                    r["date"] for r in daily
                ] != record["dates"]:
                    raise ValueError("date/return evidence mismatch")
                for y, value in record["years"].items():
                    annual = math.prod(1 + r["return"] for r in daily if r["date"][:4] == y) - 1
                    if not math.isclose(annual, value, abs_tol=1e-12):
                        raise ValueError("annual continuous return mismatch")
                if len(daily) != sql[label]["sessions"]:
                    raise ValueError("session count mismatch")
                for a, b in (
                    ("net_return", "net_total_return"),
                    ("final_nav", "final_nav"),
                    ("cost_cny", "total_cost"),
                    ("max_drawdown", "max_drawdown"),
                ):
                    if not math.isclose(
                        sql[label][a], record["metrics"][b], abs_tol=1e-6, rel_tol=1e-10
                    ):
                        raise ValueError("independent SQL metric mismatch")
                if name.startswith("blend_"):
                    field = name[len("blend_") :].rsplit("_", 2)[0]
                    base = policies[f"lowvol_{field}_h20"][cost]
                    hashed = policies[f"hash_{field}_h20"][cost]
                    rows.append(
                        {
                            "calendar": calendar,
                            "candidate": name,
                            "cost_multiplier": int(cost),
                            "roundtrip_bps": 41 * int(cost) + 2 * extra_slippage.get(calendar, 0),
                            "net_return": record["metrics"]["net_total_return"],
                            "profit_cny": record["profit_cny"],
                            "cost_cny": record["metrics"]["total_cost"],
                            "lowvol_return": base["metrics"]["net_total_return"],
                            "hash_return": hashed["metrics"]["net_total_return"],
                            "increment": record["metrics"]["net_total_return"]
                            - base["metrics"]["net_total_return"],
                            "max_drawdown": record["metrics"]["max_drawdown"],
                            "sharpe": record["pooled_sharpe"],
                            "return2023": record["years"]["2023"],
                            "return2024": record["years"]["2024"],
                            "lowvol2023": base["years"]["2023"],
                            "lowvol2024": base["years"]["2024"],
                            "observations": len(daily),
                            "start": daily[0]["date"],
                            "end": daily[-1]["date"],
                        }
                    )
    if expected != set(sql) or len(sql) != result["completed_new_trials"]:
        raise ValueError("missing or extra account")
    for candidate, assessment in result["assessments"].items():
        cohort = [r for r in rows if r["candidate"] == candidate and r["cost_multiplier"] == 2]
        s = next(r for r in cohort if r["calendar"] == "staggered_four")
        phases = [r["increment"] for r in cohort if r["calendar"].startswith("phase_")]
        independently_passes = all(
            (
                s["return2023"] > 0,
                s["return2024"] > 0,
                s["sharpe"] >= 0.7,
                s["max_drawdown"] >= -0.25,
                s["increment"] >= 0.03,
                s["return2023"] - s["lowvol2023"] >= -0.05,
                s["return2024"] - s["lowvol2024"] >= -0.05,
                s["net_return"] > s["hash_return"],
                sum(v > 0 for v in phases) >= 3,
                min(phases) >= -0.05,
            )
        )
        if independently_passes != assessment["historical_robust_lead"]:
            raise ValueError("independent gate mismatch")
    for d in result["decomposition"].values():
        if not math.isclose(
            d["account_reset_difference_pp"] + d["calendar_difference_pp"],
            d["total_difference_pp"],
            abs_tol=1e-10,
        ):
            raise ValueError("decomposition does not reconcile")
    for scenario, checks in result.get("stress_checks", {}).items():
        r = next(r for r in rows if r["calendar"] == scenario)
        independent = {
            "positive_both_years": r["return2023"] > 0 and r["return2024"] > 0,
            "continuous_drawdown": r["max_drawdown"] >= -0.25,
            "sharpe": r["sharpe"] >= 0.7,
            "lowvol_increment": r["increment"] >= 0.03,
            "annual_increment": r["return2023"] - r["lowvol2023"] >= -0.05
            and r["return2024"] - r["lowvol2024"] >= -0.05,
            "hash_increment": r["net_return"] > r["hash_return"],
        }
        if independent != checks:
            raise ValueError("independent stress gate mismatch")
    with sqlite3.connect(
        f"file:{(folder / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as con:
        trials = con.execute("select count(*) from trials").fetchone()[0]
    if trials != result["reserved_new_trials"] or trials != len(sql):
        raise ValueError("trial ledger mismatch")
    summary = {
        "version": result["version"],
        "issue": 184,
        "decision": result["decision"],
        "survivors": result["survivors"],
        "validated_alpha": False,
        "rows": rows,
        "decomposition": result["decomposition"],
        "assessments": result["assessments"],
        "statistics": {
            k: v for k, v in result["statistics"].items() if k not in ("split_manifest", "folds")
        },
        "placebo": result["placebo"],
        "new_trials": trials,
        "raw_global_trial_lower_bound": result["raw_global_trial_lower_bound"],
        "account_windows": len(sql),
        "max_balance_residual_cny": residual,
        "independent_sql_and_gate_pass": True,
        "protected_unchanged": result["protected_unchanged"],
        "restricted_rows_read": result["restricted_rows_read"],
        "source_result_sha256": file_sha(folder / "RESULT.json"),
        "snapshot_sha256": result["spec"]["snapshot_sha256"],
        "runtime_code_sha256": result["spec"]["runtime_code_sha256"],
        "stress_checks": result.get("stress_checks", {}),
        "diagnostics": result.get("diagnostics", {}),
        "statistical_scope": result.get(
            "statistical_scope", "current calendar family; sensitivity only"
        ),
    }
    write_json(
        folder / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "query": query,
            "rows": sql_rows,
            "maximum_residual": residual,
            "summary": summary,
        },
    )
    return summary


def reports(s, docs):
    write_json(docs / "V11_9_RESULT.summary.json", s)
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# V11.9 调仓日历稳健性测试" if zh else "# V11.9 Calendar Robustness Results",
            "",
            "## 结论" if zh else "## Technical summary",
            "",
            (
                f"完成{s['account_windows']}个连续账户；固定四批策略稳健性幸存数{len(s['survivors'])}，已验证可用Alpha仍为0。"
                if zh
                else f"Completed{s['account_windows']} continuous accounts;{len(s['survivors'])} robust staggered leads;zero validated Alpha."
            ),
            "",
            "2023–2024 已暴露历史研究；单次300万元、覆盖匹配低波动/hash对照。增量为两个总收益率相减（百分点），不是信息比率或对沪深300的超额。"
            if zh
            else "Exposed2023–2024 research, CNY3m once, coverage-matched low-vol/hash controls. Increment is a difference in total returns (pp), not information ratio or CSI300 excess.",
            "",
            "## 双倍成本：所有预定日历" if zh else "## Doubled costs: all predeclared calendars",
            "",
            "|Candidate / 候选|Calendar / 日历|2023|2024|Total / 总收益|Profit / 盈利元|Low-vol / 对照|Increment / 增量pp|MDD|Sharpe|",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in s["rows"]:
            if r["cost_multiplier"] == 2:
                lines.append(
                    f"|{r['candidate']}|{r['calendar']}|{r['return2023']:.2%}|{r['return2024']:.2%}|{r['net_return']:.2%}|{r['profit_cny']:,.2f}|{r['lowvol_return']:.2%}|{100 * r['increment']:+.2f}|{r['max_drawdown']:.2%}|{r['sharpe']:.3f}|"
                )
        lines += [
            "",
            "## 年度重置差异分解" if zh else "## Descriptive reset decomposition",
            "",
            "|Candidate|Annual reset linked|Continuous annual calendar|Continuous phase0|Account reset pp|Calendar pp|",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for name, d in s["decomposition"].items():
            lines.append(
                f"|{name}|{d['annual_reset_linked_return']:.2%}|{d['continuous_annual_calendar_return']:.2%}|{d['continuous_phase0_return']:.2%}|{d['account_reset_difference_pp']:+.2f}|{d['calendar_difference_pp']:+.2f}|"
            )
        lines += [
            "",
            "差分按预定顺序可加总，但不是唯一因果归因。四批策略是目标权重合成的同一账户，不是事后收益平均。"
            if zh
            else "Differences reconcile in the prespecified order but are not identified causal effects. The staggered policy combines desired weights in ONE account, not ex-post returns.",
            "",
            "## 门禁与局限" if zh else "## Gates and limitations",
            "",
        ]
        for name, a in s["assessments"].items():
            lines.append(
                f"- {name}: failed checks={', '.join(k for k, v in a['checks'].items() if not v) or 'none'}"
            )
        lines += [
            "",
            f"PBO diagnostic={s['statistics'].get('pbo')}; DSR and all details in the adjacent machine-readable summary. Family placebo={s['placebo']}. These are current-family diagnostics, NOT full-history calibrated confidence.",
            "",
            "复权碎股、线性费用和ADV容量仍是近似；尚缺真实手数/最低佣金/公司行为/实际开盘容量和完整风格独立验证。没有门槛降低，也没有解封2025/2026。"
            if zh
            else "Adjusted fractional shares, linear fees and ADV capacity remain approximations. Raw-share/lots/minimum-fee/actions/opening-liquidity and full-style independent validation remain necessary. No thresholds reduced or2025/2026 unsealed.",
            "",
            "## 核验与下一步" if zh else "## Verification and next step",
            "",
            f"Independent SQL, daily cash/positions/NAV, annual compounding, gate decisions and{s['new_trials']} SQLite trials passed. Maximum residual{s['max_balance_residual_cny']:.3g} CNY. Raw trial lower bound{s['raw_global_trial_lower_bound']}; restricted rows read=0.",
            "",
            "若固定四批策略幸存，冻结后进入真实成交及风格审计；否则记录时点/换手/信号不足，预声明下一种机制，禁止挑选本轮最佳相位。待解问题是机制增量而非回测收益本身；已见历史不重新命名为独立验证。"
            if zh
            else "A surviving fixed staggered policy is frozen for execution/style audit. Otherwise record timing/turnover/signal failures and preregister a genuinely distinct mechanism; never select this epoch's best phase. The open question is incremental information, not merely positive returns. Reused history never becomes independent validation.",
            "",
        ]
        with (docs / f"V11_9_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    args = parser.parse_args()
    s = audit(Path(args.operation))
    reports(s, Path("docs"))
    print(
        json.dumps(
            {
                k: s[k]
                for k in (
                    "decision",
                    "survivors",
                    "account_windows",
                    "raw_global_trial_lower_bound",
                )
            }
        )
    )
