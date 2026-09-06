"""Bounded bilingual technical report from independently reconciled evidence."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

challenge = json.loads(Path("docs/V11_8_RESULT.summary.json").read_text(encoding="utf-8"))
successor = json.loads(Path("docs/V11_8_SUCCESSOR.summary.json").read_text(encoding="utf-8"))
challenge_root = Path("artifacts/lead-challenge/epoch-001")
successor_root = Path("artifacts/lead-successor/epoch-001")
sources = []
for key, root, doc in (
    ("challenge", challenge_root, "V11_8_RESULT"),
    ("successor", successor_root, "V11_8_SUCCESSOR"),
):
    audit = json.loads((root / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
    sources.append(
        {
            "id": key,
            "label": f"V11.8 {key} independently audited accounts",
            "path": f"docs/{doc}.summary.json",
            "href": f"https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.8-lead-challenge/docs/{doc}.zh.md",
            "query": {
                "sql": audit["query"],
                "language": "sql",
                "engine": "DuckDB",
                "tables_used": [
                    str(root / "RESULT.json"),
                    str(root / "accounts/*.jsonl")
                    if key == "challenge"
                    else str(root / "batch-01/accounts/*.jsonl"),
                ],
                "filters": [
                    "2023-2024 exposed historical development",
                    "CNY3m per annual account; continuous explicitly labeled",
                    "no2025/2026",
                ],
                "description": "Independent SQL from saved daily accounts, cross-checked against Python ledger metrics. Derived compound increments, attribution and statistics are recorded with snapshot/result hashes in the named summary JSON.",
                "metric_definitions": {
                    "net": "final_NAV/3000000-1 after modeled costs",
                    "profit": "final_NAV-3000000 CNY",
                    "increment": "compound annual-reset candidate returns minus compound matched lowvol returns; not continuous capital",
                    "r_squared": "descriptive one-control OLS explained daily return variance, not causal alpha",
                },
            },
        }
    )

cost_labels = {
    "baseline_82": "82bps",
    "cost_102": "102bps",
    "cost_132": "132bps",
    "quarter_capacity": "1/4 ADV cap",
    "delay_one": "+1 day delay",
}


def name(value):
    return "筹码宽度 / Chip width" if "concentration" in value else "尾盘反转 / Late reversal"


stress = [
    {**r, "label": f"{name(r['candidate'])} · {cost_labels[r['scenario']]}"}
    for r in challenge["rows"]
    if r["window"] == "2023"
]
family = [
    {
        "label": c["name"].replace("conditional_", "").replace("_h60", " /60d"),
        "candidate": c["name"],
        "net2023": c["years"]["2023"]["2"]["absolute_return"],
        "net2024": c["years"]["2024"]["2"]["absolute_return"],
        "lowvol2023": c["years"]["2023"]["2"]["benchmark_return"],
        "lowvol2024": c["years"]["2024"]["2"]["benchmark_return"],
        "increment": c["assessment"]["compound_increment_vs_lowvol"],
        "sharpe": c["assessment"]["pooled_sharpe"],
        "lead": c["assessment"]["suspected_lead"],
    }
    for c in successor["candidates"]
]
family.sort(key=lambda row: row["increment"], reverse=True)
title = "Frozen Alpha Leads Under Stress | 冻结候选深挖"
blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]


def md(key, body, source=None):
    blocks.append(
        {"id": key, "type": "markdown", "body": body, **({"sourceId": source} if source else {})}
    )


md(
    "summary",
    "## 尚未找到可用 Alpha，研究继续 / Technical summary\n\n旧线索完成深挖，均未通过全部预声明执行压力检验；随后自动进入更低换手的60日机制。工程核验通过不等于Alpha成立。两轮共258个账户窗口、126个新试验，未降低通过门槛。\n\nNeither frozen lead survives every execution stress. The predeclared lower-turnover successor also finds no qualifying economic lead. Both rounds remain historical development, not investment certification.",
)
md(
    "scope",
    "## 收益口径先于比较 / Scope and definitions\n\n2023和2024分别初始化300万元；连续账户仅在起点初始化一次。基准是同字段覆盖/同期限/同Top40预算的低波动对照，不是沪深300。持仓带10档缓冲。旧线索持有20日，后继机制持有60日。筹码宽度代表成本分布宽度，不是更高集中度。\n\nAll returns deduct modeled costs. Annual-reset results and continuous capital are explicitly separate; exposed history is not fresh OOS.",
)
md(
    "fragility",
    "## 2023利润很容易被额外成本吃掉 / Thin cost cushion\n\n筹码线索2023从82bps往返成本的+0.90%，降到102bps的−0.65%；尾盘反转在132bps下变为−2.31%。图中保留所有年度压力情景，不只展示最有利的一档。容量收紧未改变结果，只能说明ADV代理在本规模未绑定，不能证明开盘能成交。\n\nExtra costs are rerun through cash and share accounting. Identical results under a smaller ADV cap do not establish opening-liquidity capacity.",
    "challenge",
)
blocks.append({"id": "stress-chart", "type": "chart", "chartId": "stress"})
md(
    "continuous",
    "## 连续运行推翻了尾盘线索的相对优势 / Continuous capital changes the story\n\n筹码线索两年连续净收益31.54%，约赚94.61万元；匹配对照26.21%，增量5.32个百分点。尾盘线索连续净收益13.73%，约赚41.19万元，对照29.54%，落后15.81个百分点。全部是研究账户，不是实盘执行保证。\n\nKeeping positions, cash and rebalance phase across New Year matters. Annual resets can conceal implementation and calendar sensitivity.",
    "challenge",
)
md(
    "attribution",
    "## 大部分波动与低波动风格共同变化 / Strong low-vol co-movement\n\n低波动单变量回归R²约0.78–0.88，所有年度截距的描述性HAC95区间包含零。将最强5个正超额日替换为对照收益后，四个候选—年份组合的增量都转负。这是事后依赖诊断，不能当作可交易删日规则，也未完成行业/规模/市场beta归因。\n\nNeither regression nor the tail counterfactual is selection-adjusted proof of Alpha.",
    "challenge",
)
md(
    "successor",
    "## 延长到60日，并未恢复增量收益 / Longer holding alone does not help\n\n第二轮完整测试8类信号×双方向，在最低波动30%的股票内排序。图中展示全部16个组合；其相对匹配低波动基线的年度链接增量均为负。最接近的组合仍落后约14.39个百分点。这里比较的是年度重置链接，不是连续资金。\n\nNone of the16 predeclared lower-turnover candidates qualifies. Lower turnover alone did not add information over the matched low-vol control.",
    "successor",
)
blocks.append({"id": "family-chart", "type": "chart", "chartId": "family"})
md(
    "methods",
    "## 账本与统计门槛没有改写 / Registration and statistical contract\n\n30个新压力方案先登记后读取行情；12个旧基线账户精确重放、Trial增量0。后继机制新增96个试验，累计原始试验下界3184，保留旧未执行预算。后继CPCV按60日期限purge；PBO0.55，family placebo p0.995，DSR敏感性0.0163。DSR不是全历史已校准置信度，不能报告Court通过。\n\nComplete family results, failed attempts and prior exposure remain recorded. Statistical thresholds are unchanged.",
)
md(
    "verification",
    "## 账户核验通过，投资有效性未通过 / Verification is not certification\n\n两轮66+192个账户的现金、持仓、成本及NAV均经独立重算，最大余额残差小于0.000001元；DuckDB与Python结果一致。本地完整751项测试通过，另1项Windows符号链接权限相关跳过。冻结父证据不变，没有读取2025/2026。\n\nSource hashes and account evidence support reproducibility. They do not establish that the strategy can earn reliable future excess returns.",
)
md(
    "next",
    "## 后续自动探索的边界 / Next research steps\n\n1. 保留两条旧线索和全部新失败，不覆盖或回收Trial。\n2. 下一批优先检验信号时点、连续持仓和真正不同的机制；先登记有限候选，再读结果。\n3. 有经济线索时先做原始股数、手数、最低佣金、公司行为及开盘流动性核验，再检验完整风格暴露和独立证据。\n4. 完整Alpha Court通过才报告可用；若需要新权限或独立数据则明确说明，不制造成功。\n\nThe recurring task resumes safely, avoids duplicate jobs, and keeps ordinary failures in bilingual evidence. No trading or paid data purchase is authorized.",
)
md(
    "questions",
    "## 仍需回答 / Open questions\n\n当前排名机制是否只是重复低波动风格？信息是否被错误的持有期限稀释？连续持仓的相位敏感性有多大？这些问题比继续堆叠同类公式更值得下一轮检验。\n\nCan timing-specific mechanisms add executable information beyond known low-risk exposure, without depending on annual account resets?",
)

charts = [
    {
        "id": "stress",
        "type": "bar",
        "title": "2023净收益：执行压力情景 / Execution stress",
        "dataset": "stress",
        "sourceId": "challenge",
        "source": sources[0],
        "encodings": {
            "x": {"field": "label", "type": "nominal"},
            "y": {"field": "net_return", "type": "quantitative"},
        },
        "options": {"orientation": "horizontal"},
        "palette": {"kind": "sequential", "name": "blue"},
        "height": 480,
        "valueFormat": "percent",
    },
    {
        "id": "family",
        "type": "bar",
        "title": "60日机制：相对低波动的链接增量 / Linked increment",
        "dataset": "family",
        "sourceId": "successor",
        "source": sources[1],
        "encodings": {
            "x": {"field": "label", "type": "nominal"},
            "y": {"field": "increment", "type": "quantitative"},
        },
        "options": {"orientation": "horizontal"},
        "palette": {"kind": "sequential", "name": "blue"},
        "height": 660,
        "valueFormat": "percent",
    },
]
artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": title,
        "sources": sources,
        "blocks": blocks,
        "charts": charts,
    },
    "snapshot": {"version": 1, "status": "ready", "datasets": {"stress": stress, "family": family}},
    "sources": sources,
}
write_json(challenge_root / "report-artifact.json", artifact)
write_json(
    challenge_root / "report-qa.json",
    {
        "audience": "technical",
        "surface": "mcp-app",
        "snapshot_status": "ready",
        "chart_contract": "two horizontal categorical comparisons, zero-included signed returns, single blue root and direct labels;10 stress and16 family rows with context retained",
        "repeat_bar_reason": "both questions compare discrete policy scenarios, not trends",
        "required_structure": "title; technical summary; definitions moved before evidence; findings; method; limitations; next steps; open questions",
        "limitations": "descriptive historical analysis, not validated Alpha; brokerage realism and independent evidence absent",
        "confidence": "SHARE_WITH_CAVEATS",
        "sql_checks": "66 challenge plus192 successor accounts reconciled",
    },
)
print(json.dumps({"blocks": len(blocks), "charts": len(charts), "rows": len(stress) + len(family)}))
