"""Audit additional lead stresses and preserve exact cost scenario definitions."""

import json
from pathlib import Path

from audit_calendar_epoch import audit

from stephen_quant.workflows.v114_reliable_epoch import write_json

root = Path("artifacts/calendar-lead-stress/epoch-001")
s = audit(root)
write_json(Path("docs/V11_9_DEEP.summary.json"), s)
for lang in ("zh", "en"):
    zh = lang == "zh"
    lines = [
        "# V11.9 筹码四批候选深挖" if zh else "# V11.9 Staggered Chip Lead: Deeper Challenge",
        "",
        "## 结论" if zh else "## Technical summary",
        "",
        f"Decision: {s['decision']}; stress survivors={len(s['survivors'])}; validated Alpha=0.",
        "",
        "先冻结候选后预记12新政策试验，再执行完整的102/132bps、容量1/4和延迟一日挑战。所有比较都是2023–2024连续300万元研究账户及其匹配对照；非独立OOS。"
        if zh
        else "Twelve policies registered after freezing the lead:102/132bps, quarter ADV capacity and one-session delay. Continuous CNY3m2023–2024 research and matched controls;not independent OOS.",
        "",
        "|Scenario|Roundtrip bps|2023|2024|Total net|Profit CNY|Low-vol|Increment pp|MDD|Sharpe|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["rows"]:
        lines.append(
            f"|{r['calendar']}|{r['roundtrip_bps']}|{r['return2023']:.2%}|{r['return2024']:.2%}|{r['net_return']:.2%}|{r['profit_cny']:,.2f}|{r['lowvol_return']:.2%}|{100 * r['increment']:+.2f}|{r['max_drawdown']:.2%}|{r['sharpe']:.3f}|"
        )
    lines += [
        "",
        "## 描述性风格与盈利日依赖" if zh else "## Descriptive style and tail dependence",
        "",
    ]
    for scenario, d in s["diagnostics"].items():
        a, t = d["lowvol_attribution"], d["tail"]
        lines += [
            f"- {scenario}: {json.dumps(a, ensure_ascii=False)}",
            f"  Tail counterfactual: {json.dumps(t, ensure_ascii=False)}",
        ]
    lines += [
        "",
        "## 判断边界与下一步" if zh else "## Decision boundary and next step",
        "",
        "HAC和替换最高5个正超额日只用于描述，不用于生成删日交易规则，也不是经过选择校正的置信度。上轮PBO0.65、DSR敏感性0.005495、family placebo0.655属于3256次债务时的12个日历family，未冒充加入本轮后的完整统计认证。"
        if zh
        else "HAC and replacing the top5 positive active days are descriptive diagnostics, not trading rules or selection-adjusted inference. Parent PBO0.65, DSR sensitivity0.005495 and placebo0.655 refer to the12-calendar family at3256 trials, not a recomputed full search certificate.",
        "",
        f"Independent daily account/SQL/gate checks passed for12 accounts;maximum residual={s['max_balance_residual_cny']:.3g} CNY. New trials12;full raw debt3268. No2025/2026 reads;frozen parent unchanged.",
        "",
        "## 真实执行就绪程度" if zh else "## Brokerage-readiness evidence",
        "",
        "现有冻结日K提供原始open/close、amount/volume、adjustment_factor和available_at，但冻结分钟表只有日内特征，没有真实开盘逐笔成交。adjustment_factor不等于可审计的现金分红/送转/配股事件；不能据此完成原始手数及最低佣金的全账户认证。未运行真实券商账户、未下单。"
        if zh
        else "The frozen daily source supplies raw open/close, amount/volume, adjustment_factor and available_at;the frozen minute source contains features,not opening prints. An adjustment factor is not a complete cash-dividend/split/rights event ledger. Raw lots/minimum fees and executable opening capacity are NOT certified. No broker account or orders were used.",
        "",
        "如额外压力失败，保留该候选作观察，不再优化相位；继续预注册与低波动重复暴露不同的机制。若所有压力通过，也只进入执行来源审计，不宣称可用Alpha。完整正式门槛与独立证据要求不改变。"
        if zh
        else "If stresses fail, retain the frozen observational lead and change mechanism through a new preregistered epoch, not another phase tweak. Even stress survival only advances execution-source audit,not Alpha certification. Formal gates and independent-evidence requirements remain unchanged.",
        "",
    ]
    with Path(f"docs/V11_9_DEEP.{lang}.md").open("x", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
print(
    json.dumps(
        {
            "decision": s["decision"],
            "accounts": s["account_windows"],
            "debt": s["raw_global_trial_lower_bound"],
        }
    )
)
