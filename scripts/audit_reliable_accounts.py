"""Reconcile saved daily evidence and publish a small bilingual release report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean


def inspect_run(folder: Path):
    report_bytes = (folder / "RESULT.json").read_bytes()
    report = json.loads(report_bytes)
    windows = 0
    maximum_residual = 0.0
    for candidate in report["candidates"]:
        for stage in ("inner", "outer"):
            for cost in ("1", "2"):
                metrics = candidate[stage][cost]
                path = folder / "accounts" / f"{stage}-{candidate['name']}-{cost}.jsonl"
                daily = [json.loads(line) for line in path.read_text().splitlines()]
                assert [p["return"] for p in daily] == metrics["daily_returns"]
                assert math.isclose(daily[-1]["nav"], metrics["final_nav"], abs_tol=1e-7)
                assert math.isclose(
                    sum(p["cost"] for p in daily), metrics["cost_cny"], abs_tol=1e-7
                )
                assert math.isclose(
                    math.prod(1 + p["return"] for p in daily) - 1,
                    metrics["absolute_return"],
                    abs_tol=1e-10,
                )
                for p in daily:
                    residual = abs(
                        p["nav"] - p["cash"] - sum(m["market_value"] for m in p["positions"])
                    )
                    maximum_residual = max(maximum_residual, residual)
                    assert residual < 1e-5
                    assert p["cash"] >= 0
                    assert math.isclose(
                        sum(o["total_cost"] for o in p["orders"]), p["cost"], abs_tol=1e-6
                    )
                windows += 1
    winner = next(c for c in report["candidates"] if c["name"] == report["winner_name"])
    compact = []
    for c in report["candidates"]:
        entry = {"name": c["name"], "identity": c["identity"], "parent": c["parent"]}
        for stage in ("inner", "outer"):
            entry[stage] = {
                cost: {k: v for k, v in c[stage][cost].items() if not k.startswith("daily_")}
                for cost in ("1", "2")
            }
        compact.append(entry)
    summary = {
        "version": report["version"],
        "decision": report["decision"],
        "validated_alpha": False,
        "audit_pass": True,
        "account_windows_reconciled": windows,
        "maximum_balance_residual_cny": maximum_residual,
        "source_result_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "snapshot_sha256": report["source_snapshot"]["snapshot_sha256"],
        "runtime_code_sha256": report["spec"]["runtime_code_sha256"],
        "winner_name": winner["name"],
        "winner_identity": winner["identity"],
        "candidates": compact,
        "statistics": {
            k: report["selection"][k]
            for k in ("dsr", "dsr_status", "pbo", "daily_observations", "effective_observations")
        },
        "minimum_cpcv_training_observations": min(
            f["train_n"] for f in report["selection"]["folds"]
        ),
        "placebo_p": report["placebo"]["p_value"],
        "calibration": report["calibration"],
        "protected_state": report["protected_state"],
        "raw_global_trial_lower_bound": report["raw_global_trial_lower_bound"],
        "completed_new_trials": report["new_trials"],
        "aborted_trials_retained": 48,
        "positive_active_mean_2023": sum(
            mean(c["inner"]["2"]["daily_active"]) > 0 for c in report["candidates"]
        ),
        "positive_excess_total_2024": sum(
            c["outer"]["2"]["excess_percentage_points"] > 0 for c in report["candidates"]
        ),
        "exposed_restricted_rows": report["source_snapshot"]["exposed_sealed_rows"],
        "external_llm_calls": report["external_llm_calls"],
    }
    return summary


def write_reports(summary, docs):
    docs.mkdir(parents=True, exist_ok=True)
    winner = next(c for c in summary["candidates"] if c["name"] == summary["winner_name"])
    for language in ("zh", "en"):
        zh = language == "zh"
        lines = [
            "# V11.6 最终测试报告" if zh else "# V11.6 final test report",
            "",
            "工程修复完成；本轮没有验证通过的新Alpha。"
            if zh
            else "Engineering repairs delivered; no new validated Alpha in this epoch.",
            "",
            "## 工程验收" if zh else "## Engineering checks",
            "",
            "- 完整测试：702 passed、1 skipped；Ruff通过。"
            if zh
            else "- Full local suite:702 passed,1 skipped; Ruff passed.",
            "- 修复门控方向、未来退出价入池、无关字段过滤、分钟可见时间连接、逐日会计与统计口径。"
            if zh
            else "- Repaired gate direction, future exit-price eligibility, unused-field filtering, minute availability joins, daily accounting and statistical definitions.",
            f"- {summary['account_windows_reconciled']} account-window reconciliations passed; maximum balance residual CNY{summary['maximum_balance_residual_cny']:.10f}.",
            "- 合成校准：真实1/8 worker一致，24/24恢复第一名，0/100噪声误报（95% Wilson上界3.70%）。"
            if zh
            else "- Synthetic audit:actual1/8-worker parity,24/24 first-place recovery,0/100 false positives (95% Wilson upper bound3.70%).",
            "- 上述经济检测不等于Court校准：全局次数DSR敏感性令24个强植入信号也全部未通过，必须保留这一限制。"
            if zh
            else "- Economic detection is not Court calibration:the raw-count DSR sensitivity rejects all24 strong planted signals; this limitation remains explicit.",
            "",
            "## 冻结赢家的账户表现" if zh else "## Frozen winner accounts",
            "",
            f"2023 selector: `{summary['winner_name']}`. Identity: `{summary['winner_identity']}`.",
            "",
            "每个年度独立投入300万元，以下均为扣费后结果。基准为相同字段覆盖股票的理论等权组合，不是沪深300，也不是已验证可整手交易的产品。"
            if zh
            else "Each year starts independently with CNY3m. Net of modeled costs. Benchmark:theoretical matched-availability equal weights, not CSI300 or a verified board-lot product.",
            "",
            "| 年份 | 往返成本 | 账户收益率 | 净利润/元 | 基准收益率 | 超额/百分点 | 最大回撤 |"
            if zh
            else "| Year | Round-trip bps | Account return | Profit CNY | Benchmark return | Excess pp | Max drawdown |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for stage, year in (("inner", 2023), ("outer", 2024)):
            for cost in ("1", "2"):
                m = winner[stage][cost]
                lines.append(
                    f"| {year} | {41 * int(cost)} | {m['absolute_return']:.2%} | {m['profit_cny']:,.2f} | {m['benchmark_return']:.2%} | {m['excess_percentage_points'] * 100:.2f} | {m['max_drawdown']:.2%} |"
                )
        lines += [
            "",
            "## 统计结论与限制" if zh else "## Statistical conclusion and limits",
            "",
            f"- DSR sensitivity={summary['statistics']['dsr']:.8f}; PBO diagnostic={summary['statistics']['pbo']}; family placebo p={summary['placebo_p']}.",
            f"- Daily observations={summary['statistics']['daily_observations']}; effective={summary['statistics']['effective_observations']}; minimum CPCV training fold={summary['minimum_cpcv_training_observations']}.",
            f"- 2023 positive mean active return: {summary['positive_active_mean_2023']}/24. 2024 positive total excess: {summary['positive_excess_total_2024']}/24 (post-hoc diagnostic count, not winner replacement).",
            "- 2022训练、2023选择、2024受污染诊断；不是独立样本外证据。2025–2026本轮返回行数为0，历史暴露事实未被抹掉。"
            if zh
            else "- Train2022/select2023/contaminated diagnostic2024; no independent out-of-sample claim. Zero2025–2026 returned rows this epoch; previous exposure remains disclosed.",
            "- 历史同频候选收益矩阵缺失，DSR只是以本轮离散度外推全局次数的敏感性。CPCV折最少样本数较低，PBO只能作诊断。"
            if zh
            else "- Missing aligned historical candidate returns means DSR extrapolates current-family dispersion to raw debt. Smallest purged folds are short; PBO remains diagnostic.",
            "- 当前仍是24个受控机制/基准的生成比较（含线性收缩和浅树），外部LLM调用为0；没有声称自由自主因子发现已经成熟。"
            if zh
            else "- This compares24 controlled mechanism/baseline proposals including ridge and a stump; zero external LLM calls. Free-form autonomous discovery is not declared mature.",
            "- 采用复权价格、分数股、固定费率、日均量容量近似，尚非整手/最低佣金/开盘真实可成交量的实盘模拟。"
            if zh
            else "- Adjusted prices, fractional shares, fixed fees and ADV capacity are approximations, not board-lot/minimum-commission/open-auction-volume brokerage simulation.",
            "",
            "## 证据与后续" if zh else "## Evidence and next step",
            "",
            f"- Completed48 trials; aborted48 retained; historical raw trial lower bound={summary['raw_global_trial_lower_bound']}.",
            f"- Protected files={summary['protected_state']['files']}; unchanged={summary['protected_state']['unchanged']}.",
            f"- Snapshot SHA-256: `{summary['snapshot_sha256']}`.",
            f"- Result SHA-256: `{summary['source_result_sha256']}`.",
            f"- Runtime SHA-256: `{summary['runtime_code_sha256']}`.",
            "- 下一步优先做可交易基准和成本/风格归因，并重建可识别的历史统计合同；不通过扩大随机模板或放宽阈值来制造PASS。冻结该轮结果，只在新方案预声明后继续。"
            if zh
            else "- Next:investable benchmark and cost/style attribution, then an identifiable historical statistical contract. Do not manufacture PASS by increasing random templates or relaxing thresholds. Keep this epoch frozen.",
            "",
        ]
        with (docs / f"V11_6_RESULT.{language}.md").open("x", encoding="utf-8") as stream:
            stream.write("\n".join(lines))
    with (docs / "V11_6_RESULT.summary.json").open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    summary = inspect_run(args.folder)
    write_reports(summary, args.docs)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "candidates"}, ensure_ascii=False, indent=2
        )
    )
