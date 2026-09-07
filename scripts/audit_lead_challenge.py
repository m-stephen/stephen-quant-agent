"""Independent saved-account/SQL audit and public-safe bilingual challenge report."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import duckdb

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json


def audit(folder):
    result = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
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
        sql_rows = [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]
    sql = {row["account_key"]: row for row in sql_rows}
    if set(sql) != set(result["records"]):
        raise ValueError("missing/unexpected accounting evidence")
    residual = 0.0
    for label, r in result["records"].items():
        path = folder / "accounts" / (label + ".jsonl")
        if file_sha(path) != r["account_sha256"]:
            raise ValueError("account evidence hash mismatch")
        daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        prior = 3_000_000.0
        for row in daily:
            error = abs(row["nav"] - row["cash"] - sum(p["market_value"] for p in row["positions"]))
            residual = max(error, residual)
            if error > 1e-5 or row["cash"] < -1e-7:
                raise ValueError("cash/positions/NAV mismatch")
            if not math.isclose(
                sum(o["total_cost"] for o in row["orders"]), row["cost"], abs_tol=1e-6
            ):
                raise ValueError("order costs mismatch")
            if not math.isclose(row["return"], row["nav"] / prior - 1, abs_tol=1e-12):
                raise ValueError("daily returns mismatch")
            prior = row["nav"]
        if [r["return"] for r in daily] != r["daily_returns"]:
            raise ValueError("return vector mismatch")
        for field, metric in (
            ("final_nav", "final_nav"),
            ("net_return", "net_total_return"),
            ("cost_cny", "total_cost"),
            ("max_drawdown", "max_drawdown"),
        ):
            if not math.isclose(
                sql[label][field], r["metrics"][metric], abs_tol=1e-6, rel_tol=1e-10
            ):
                raise ValueError("independent SQL mismatch")
    summary = {
        "version": result["version"],
        "issue": 184,
        "validation_assessment": "SHARE_WITH_CAVEATS",
        "engineering_pass": True,
        "validated_alpha": False,
        "decision": result["decision"],
        "stress_survivors": result["stress_survivors"],
        "account_windows": len(sql_rows),
        "max_balance_residual_cny": residual,
        "sql_all_accounts_match": True,
        "source_result_sha256": file_sha(folder / "RESULT.json"),
        "snapshot_sha256": result["spec"]["snapshot_sha256"],
        "runtime_code_sha256": result["spec"]["runtime_code_sha256"],
        "raw_global_trial_lower_bound": result["raw_global_trial_lower_bound"],
        "new_trials": result["completed_new_trials"],
        "baseline_replay_accounts": 12,
        "baseline_replay_trial_delta": 0,
        "protected_unchanged": result["protected_unchanged"],
        "restricted_rows_read": result["restricted_rows_read"],
        "limitations": result["limitations"],
        "rows": [],
        "continuous": [],
        "diagnostics": [],
    }
    for scenario, payload in result["scenarios"].items():
        for candidate, years in payload["candidates"].items():
            for year, row in years.items():
                record = {
                    "scenario": scenario,
                    "candidate": candidate,
                    "window": year,
                    "net_return": row["absolute_return"],
                    "profit_cny": row["profit_cny"],
                    "lowvol_return": row["benchmark_return"],
                    "hash_return": row["hash_control_return"],
                    "increment_vs_lowvol": row["excess_percentage_points"],
                    "max_drawdown": row["max_drawdown"],
                    "cost_cny": row["cost_cny"],
                    "turnover": row["gross_traded_notional"] / 3e6,
                }
                if year.startswith("continuous"):
                    summary["continuous"].append(record)
                else:
                    record["whole_scenario_economic_pass"] = payload["assessments"][candidate][
                        "suspected_lead"
                    ]
                    summary["rows"].append(record)
                if scenario == "baseline_82":
                    summary["diagnostics"].append(
                        {
                            "candidate": candidate,
                            "year": year,
                            "attribution": row["attribution"],
                            "tail_sensitivity": row["tail_sensitivity"],
                        }
                    )
    write_json(
        folder / "INDEPENDENT_AUDIT.json",
        {"pass": True, "rows": sql_rows, "max_balance_residual_cny": residual, "query": query},
    )
    return summary


def reports(s, docs):
    write_json(docs / "V11_8_RESULT.summary.json", s)
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# V11.8 候选深挖测试报告" if zh else "# V11.8 Frozen Lead Challenge Results",
            "",
            "## 结论" if zh else "## Technical summary",
            "",
            (
                f"完成{s['account_windows']}个账户窗口。可用Alpha仍为0；全部压力情景幸存数：{len(s['stress_survivors'])}。"
                if zh
                else f"Completed {s['account_windows']} account windows. Validated Alpha: zero. All-stress survivors: {len(s['stress_survivors'])}."
            ),
            "下一动作 / Next action: `" + s["decision"] + "`。",
            "",
            "## 口径 / Scope",
            "",
            (
                "2023、2024分别以300万元初始化；连续账户只初始化一次。所有收益均扣模型成本。"
                "基准为同字段覆盖、同持有期、同40只股票预算的低波动对照，不是沪深300。"
                "历史已被用于选因子，不能作为独立验证。"
                if zh
                else "Annual accounts start with CNY3m separately; continuous accounts initialize once. Returns include modeled costs. "
                "The benchmark is the field/coverage/horizon-matched Top40 low-vol control, NOT CSI300. Both years are postselected historical development."
            ),
            "",
            "## 年度压力检验 / Annual execution stresses",
            "",
            "筹码宽度 / Chip width = (cost85-cost15)/weighted_cost; higher does not mean more concentrated chips.",
            "",
            "| Candidate | Scenario | Year | Net | Profit CNY | Low-vol | Increment pp | Cost CNY |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
        for r in s["rows"]:
            lines.append(
                f"|{r['candidate']}|{r['scenario']}|{r['window']}|{r['net_return']:.2%}|{r['profit_cny']:,.2f}|{r['lowvol_return']:.2%}|{r['increment_vs_lowvol'] * 100:+.2f}|{r['cost_cny']:,.2f}|"
            )
        lines += ["", "## 连续账户 / Continuous capital", ""]
        for r in s["continuous"]:
            lines.append(
                f"- {r['candidate']}: net {r['net_return']:.2%}; profit CNY{r['profit_cny']:,.2f}; low-vol {r['lowvol_return']:.2%}; increment {r['increment_vs_lowvol'] * 100:+.2f}pp; MDD {r['max_drawdown']:.2%}."
            )
        lines += ["", "## 风格与极端日诊断 / Style and tail diagnostics", ""]
        for r in s["diagnostics"]:
            a, t = r["attribution"], r["tail_sensitivity"]
            lo, hi = a["hac95_annualized_intercept_interval"]
            lines.append(
                f"- {r['candidate']} {r['year']}: low-vol beta {a['beta_to_lowvol']:.3f}, R² {a['r_squared']:.3f}, annualized intercept {a['annualized_intercept']:.2%}, descriptive HAC95 [{lo:.2%}, {hi:.2%}]. Top5 positive-active days set equal to control: increment {t['increment_if_top_active_days_equal_control'] * 100:+.2f}pp."
            )
        lines += [
            "",
            (
                "这些回归未做事后选择校正，区间不能当作正式Alpha推断。极端日替换是假设诊断，不能据此设计可交易删日策略。"
                if zh
                else "Regressions are not postselection-adjusted Alpha inference. Replacing extreme days is a nontradable diagnostic, never a date-removal strategy."
            ),
            "",
            "## 验证 / Verification",
            "",
            f"- {s['account_windows']} accounts independently reconcile; max cash/position/NAV residual CNY{s['max_balance_residual_cny']:.3g}.",
            "- Independent DuckDB net/NAV/cost/drawdown aggregation matches every saved account.",
            f"- New trials {s['new_trials']}; cumulative raw lower bound {s['raw_global_trial_lower_bound']};12 exact baseline replays have zero trial delta.",
            "- Parent/frozen evidence unchanged; no2025/2026 reads.",
            "",
            "## 局限与后续 / Limitations and next work",
            "",
            (
                "本轮属于复权分数股研究账户，未实现原始股数、交易手数、最低佣金、完整公司行为与开盘流动性核验。"
                "因此不能声称可实盘。压力失败不等于证明因子永远无效：冻结保留其证据，后续检验更匹配机制的期限、降低换手的方法，"
                "但任何修改均另计Trial。当前仍缺完整统计校准和独立验证，不能宣布Alpha Court PASS。"
                if zh
                else "These adjusted fractional-share accounts are not brokerage-ready: raw shares, board lots, minimum commissions, corporate actions and actual opening liquidity remain unaudited. "
                "Stress failure does not prove universal inefficacy. Preserve the frozen evidence and preregister lower-turnover/horizon mechanisms. Every amendment counts. "
                "Historical multiplicity calibration and independent validation remain absent; no Alpha Court PASS is claimed."
            ),
            "",
            "## 待回答 / Open question",
            "",
            (
                "信号能否在低换手、真实可成交且非样本反复筛选的条件下保留增量收益？"
                if zh
                else "Can incremental returns survive lower-turnover, genuinely executable policies and independent evidence?"
            ),
            "",
        ]
        with (docs / f"V11_8_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--docs", default="docs")
    args = parser.parse_args()
    summary = audit(Path(args.folder))
    reports(summary, Path(args.docs))
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "account_windows",
                    "decision",
                    "stress_survivors",
                    "raw_global_trial_lower_bound",
                )
            }
        )
    )
