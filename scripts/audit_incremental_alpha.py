"""Independently reconcile all saved accounts and produce public-safe bilingual evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json


def audit(folder):
    result = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    accounts = 0
    residual = 0.0
    rows = []
    for batch_index, batch in enumerate(result["batches"], 1):
        root = folder / f"batch-{batch_index:02d}"
        evidence = {}
        for path in sorted((root / "accounts").glob("*.jsonl")):
            daily = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for p in daily:
                error = abs(p["nav"] - p["cash"] - sum(m["market_value"] for m in p["positions"]))
                residual = max(residual, error)
                if error > 1e-5 or p["cash"] < -1e-7:
                    raise ValueError("independent account reconciliation failed")
                if not math.isclose(
                    sum(o["total_cost"] for o in p["orders"]), p["cost"], abs_tol=1e-6
                ):
                    raise ValueError("independent order-cost reconciliation failed")
            nav = daily[-1]["nav"]
            total = math.prod(1 + p["return"] for p in daily) - 1
            if not math.isclose(nav / 3e6 - 1, total, abs_tol=1e-10):
                raise ValueError("independent wealth reconciliation failed")
            evidence[path.stem] = {
                "nav": nav,
                "total": total,
                "cost": sum(p["cost"] for p in daily),
                "daily": [p["return"] for p in daily],
                "hash": file_sha(path),
            }
            accounts += 1
        for c in batch["candidates"]:
            compact = {k: v for k, v in c.items() if k != "years"}
            compact["batch"] = batch_index
            compact["years"] = {}
            for year in ("2023", "2024"):
                compact["years"][year] = {}
                for cost in ("0", "1", "2"):
                    m = c["years"][year][cost]
                    e = evidence[f"{year}-{c['name']}-{cost}"]
                    if (
                        e["hash"] != m["account_sha256"]
                        or e["daily"] != m["daily_returns"]
                        or not math.isclose(e["nav"], m["final_nav"], abs_tol=1e-7)
                        or not math.isclose(e["cost"], m["cost_cny"], abs_tol=1e-6)
                    ):
                        raise ValueError("reported candidate metrics differ from evidence")
                    compact["years"][year][cost] = {
                        k: v for k, v in m.items() if not k.startswith("daily_")
                    }
            rows.append(compact)
        # Controls are equally auditable; match every recorded hash and money metric.
        by_hash = {e["hash"]: e for e in evidence.values()}
        for control in batch["controls"].values():
            for year in control.values():
                for m in year.values():
                    e = by_hash[m["account_sha256"]]
                    if not math.isclose(e["nav"], m["metrics"]["final_nav"], abs_tol=1e-7):
                        raise ValueError("control NAV mismatch")
    receipt = {
        "pass": True,
        "account_windows": accounts,
        "max_residual_cny": residual,
        "decision": result["decision"],
        "validated_alpha": False,
        "raw_global_trial_lower_bound": result["raw_global_trial_lower_bound"],
        "reserved_new_trials": result["reserved_new_trials"],
        "completed_new_trials": result["completed_new_trials"],
        "snapshot_sha256": result["snapshot_sha256"],
        "runtime_code_sha256": result["spec"]["runtime_code_sha256"],
        "source_result_sha256": file_sha(folder / "RESULT.json"),
        "criteria": result["spec"]["criteria"],
        "candidates": rows,
        "batches": [
            {
                k: v
                for k, v in b.items()
                if k in ("winner", "suspected_count", "placebo", "statistics", "selection")
            }
            for b in result["batches"]
        ],
        "protected_unchanged": result["protected_unchanged"],
    }
    receipt["content_sha256"] = sha256_json(receipt)
    return receipt


def reports(summary, docs):
    docs.mkdir(parents=True, exist_ok=True)
    write_json(docs / "V11_7_RESULT.summary.json", summary)
    leads = [c for c in summary["candidates"] if c["assessment"]["suspected_lead"]]
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# V11.7 增量因子测试报告" if zh else "# V11.7 Incremental Alpha Test Report",
            "",
            f"Decision: **{summary['decision']}**. Validated Alpha: **false**.",
            "",
            f"{'疑似历史线索' if zh else 'Historical leads'}: {len(leads)}/{len(summary['candidates'])}.",
            "",
            "2023/2024均为已污染历史开发窗口。本报告不批准实盘，也不声称独立样本外有效。"
            if zh
            else "Both2023/2024 are contaminated historical development. No trading approval or independent OOS claim.",
            "",
            "## 判定与比较口径" if zh else "## Definitions and comparisons",
            "",
            "每年独立投入300万元；日均ADV至少1000万元、历史至少20会话、非ST。Top40/10档缓冲；前收盘信号、次开盘交易。"
            if zh
            else "Independent CNY3m each year; lagged ADV>=CNY10m,>=20-session history, non-ST. Top40/buffer10, previous-close signal/next-open execution.",
            "控制组是同字段覆盖、同期限的低波动Top40和哈希Top40，不是沪深300。复合两年度账户只是归一化链接，不是连续交易账户。"
            if zh
            else "Controls are coverage/horizon-matched low-vol Top40 and hashed Top40, not CSI300. Compounded annual-reset accounts are a normalized link, not continuous trading.",
            "",
            "## 全部候选（双倍成本）" if zh else "## All candidates (double costs)",
            "",
            "| Candidate | 2023 net | 2024 net | Compound increment vs low-vol | Pooled Sharpe | Lead |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for c in summary["candidates"]:
            a = c["assessment"]
            lines.append(
                f"| {c['name']} | {c['years']['2023']['2']['absolute_return']:.2%} | "
                f"{c['years']['2024']['2']['absolute_return']:.2%} | "
                f"{100 * a['compound_increment_vs_lowvol']:+.2f}pp | {a['pooled_sharpe']:.3f} | {a['suspected_lead']} |"
            )
        for c in leads:
            lines += [
                "",
                f"## {c['name']}",
                "",
                f"Identity: `{c['identity']}`.",
                f"Formula: `{c['mechanism']['formula']}`.",
                "",
                "| Year | Cost bps | Net return | Profit CNY | Low-vol | Hash control | Drawdown | Cost CNY |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for year, models in c["years"].items():
                for cost, m in models.items():
                    lines.append(
                        f"| {year} | {int(cost) * 41} | {m['absolute_return']:.2%} | {m['profit_cny']:,.2f} | "
                        f"{m['benchmark_return']:.2%} | {m['hash_control_return']:.2%} | "
                        f"{m['max_drawdown']:.2%} | {m['cost_cny']:,.2f} |"
                    )
            lines += ["", "Quarterly double-cost returns (quarters compound; not summed):", ""]
            for year in ("2023", "2024"):
                m = c["years"][year]["2"]
                lines.append(
                    f"- {year}: "
                    + ", ".join(f"Q{q} {v:+.2%}" for q, v in m["quarterly_returns"].items())
                    + f"; writeoffs={m['writeoffs']}, stale-position-days={m['stale_position_days']}, "
                    f"traded=CNY{m['gross_traded_notional']:,.0f}, holdings Jaccard vs low-vol={m['holdings_jaccard_vs_lowvol']:.3f}."
                )
        lines += [
            "",
            "## 统计与工程核验" if zh else "## Statistical and engineering checks",
            "",
            f"- Independently reconciled {summary['account_windows']} accounts; max residual CNY{summary['max_residual_cny']:.10f}.",
            f"- Trials: reserved {summary['reserved_new_trials']}, completed {summary['completed_new_trials']}, raw lower bound {summary['raw_global_trial_lower_bound']}.",
            "- All accounts retain costs/cash/orders/positions. Protected candidate files unchanged; no2025/2026 data reads.",
        ]
        for b in summary["batches"]:
            s = b["statistics"]
            lines.append(
                f"- Family best-mean candidate: {s.get('winner')}; DSR sensitivity={s.get('dsr')}; "
                f"PBO diagnostic={s.get('pbo')}; family placebo p={b['placebo']['p_value']}."
            )
        lines += [
            "",
            "统计表的赢家由最大日均主动收益选择，与历史财富增量赢家可能不同；不得移用它的DSR给其他候选背书。"
            if zh
            else "The statistical selector maximizes mean daily active return and may differ from the historical-wealth winner; its DSR must not certify another candidate.",
            "",
            "## 局限与下一步" if zh else "## Limits and next steps",
            "",
            "复权分数股、固定费率、前ADV容量、20会话缺数减记均是近似。尚未证明整手/最低佣金/开盘真实容量可执行性。低波动控制只排除了部分风格解释，未完整回归行业/规模/贝塔暴露。"
            if zh
            else "Adjusted fractional shares, fixed fees, lagged ADV capacity and20-session stale write-downs are approximations. Board lots/minimum fees/actual opening volume are not established. Low-vol control excludes only part of style explanations; industry/size/beta exposures are not fully regressed.",
            "缺少全历史同频Sharpe矩阵，DSR仅为敏感性；CPCV及placebo仅为历史诊断。自动生成是有界机制语法，不是外部LLM调用。"
            if zh
            else "Missing aligned historical Sharpe matrix makes DSR sensitivity-only; CPCV/placebo are historical diagnostics. Generation uses bounded mechanism grammar, not external LLM calls.",
            "有线索则冻结停止扩搜，先独立重放，再整手成交和容量压力测试、前向影子观察；无结果保留全失败清单，提出下一轮机制，不下调标准。"
            if zh
            else "Freeze any lead and stop expanding; independently replay, then test brokerage/capacity realism and forward shadow performance. Without leads, preserve all failures and propose a new mechanism without relaxing criteria.",
            "",
            f"Snapshot: `{summary['snapshot_sha256']}`.",
            f"Result: `{summary['source_result_sha256']}`.",
            "",
        ]
        with (docs / f"V11_7_RESULT.{lang}.md").open("x", encoding="utf-8") as stream:
            stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--docs", type=Path, required=True)
    args = parser.parse_args()
    summary = audit(args.folder)
    reports(summary, args.docs)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("candidates", "batches")}))
