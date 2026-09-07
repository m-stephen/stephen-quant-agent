"""Native bilingual technical report, solely from independently audited results."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/calendar-challenge/epoch-001")
s = json.loads(Path("docs/V11_9_RESULT.summary.json").read_text(encoding="utf-8"))
audit = json.loads((ROOT / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
deep = json.loads(Path("docs/V11_9_DEEP.summary.json").read_text(encoding="utf-8"))
deep_audit = json.loads(
    Path("artifacts/calendar-lead-stress/epoch-001/INDEPENDENT_AUDIT.json").read_text(
        encoding="utf-8"
    )
)
names = {
    "blend_concentration_+1_h20": "筹码宽度 / Chip width",
    "blend_late_30_return_-1_h20": "尾盘反转 / Late reversal",
}
calendars = {
    **{f"phase_{i}": f"起点 / Phase {i}" for i in (0, 5, 10, 15)},
    "staggered_four": "四批 / Four cohorts",
    "annual_calendar": "年度日历 / Annual calendar",
}
rows = [
    {
        **r,
        "label": names[r["candidate"]] + " · " + calendars[r["calendar"]],
        "increment_pp": 100 * r["increment"],
    }
    for r in s["rows"]
    if r["cost_multiplier"] == 2
]
source = {
    "id": "calendar",
    "label": "V11.9 independently reconciled continuous accounts",
    "path": "docs/V11_9_RESULT.summary.json",
    "href": "https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.9-calendar-robustness/docs/V11_9_RESULT.zh.md",
    "query": {
        "sql": audit["query"],
        "engine": "DuckDB",
        "language": "sql",
        "tables_used": [
            "artifacts/calendar-challenge/epoch-001/accounts/*.jsonl",
            "docs/V11_9_RESULT.summary.json",
        ],
        "filters": [
            "2023-2024 exposed development",
            "one continuous CNY3m account",
            "chart82bps;all41/82bps results retained",
        ],
        "description": "Saved daily-account SQL metrics independently reconciled to Python annual returns, matched controls and gate checks by scripts/audit_calendar_epoch.py. Snapshot/result/runtime hashes are retained in the summary.",
        "metric_definitions": {
            "net_return": "final_NAV/3000000-1",
            "profit_cny": "final_NAV-3000000",
            "increment_pp": "100*(candidate total return-matched low-vol total return), percentage points",
            "max_drawdown": "min(NAV/running peak including initial capital-1)",
        },
    },
}
title = "Alpha Calendar Robustness | 调仓日历稳健性"
blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]


def md(key, heading, body, sourced=False):
    blocks.append(
        {
            "id": key,
            "type": "markdown",
            "body": "## " + heading + "\n\n" + body,
            **(
                {"sourceId": sourced if isinstance(sourced, str) else "calendar"} if sourced else {}
            ),
        }
    )


md(
    "summary",
    "连续账户已核验，尚非可用 Alpha / Technical summary",
    f"完成72个连续账户，固定四批策略通过本轮经济稳健性筛选的候选数为{len(s['survivors'])}。仍无已验证可用Alpha；不能挑本轮最佳调仓起点替代事前方案。\n\nAll72 continuous accounts were independently checked;{len(s['survivors'])} fixed staggered policies survive the prespecified economic screen. Historical profitability is not investment certification.",
    True,
)
md(
    "scope",
    "比较的是同资金、同覆盖的增量 / Scope and definitions",
    "2023–2024已暴露历史开发，单次投入300万元；两条冻结20日候选与各自同覆盖、同Top40/10档缓冲的低波动和hash对照。图中为双倍82bps往返成本。增量是候选总收益率减低波动总收益率，单位百分点，不是对沪深300的超额。\n\nCNY3m once; all returns deduct modeled costs. Annual cuts come from the same continuous account. Chip width means a broader cost distribution, not greater concentration.",
)
explanations = []
for candidate, candidate_label in names.items():
    r = next(r for r in rows if r["candidate"] == candidate and r["calendar"] == "staggered_four")
    a = s["assessments"][candidate]
    explanations.append(
        f"**{candidate_label}**：四批净收益 / net {r['net_return']:.2%}，盈利 / profit CNY{r['profit_cny']:,.0f}；低波动 / low-vol {r['lowvol_return']:.2%}，增量 / increment {r['increment_pp']:+.2f}pp。四个单起点增量范围 / phase increment range {100 * min(a['phase_increments'].values()):+.2f}至 / to {100 * max(a['phase_increments'].values()):+.2f}pp。"
    )
md(
    "calendar-evidence",
    "完整起点比较，不挑最优日历 / Complete phase comparison",
    "\n\n".join(explanations)
    + "\n\n图中保留全部六种日历。零线右侧才是超过匹配低波动的收益；单个起点漂亮不构成稳健优势。\n\nThe chart includes every calendar: positive values mean incremental return over matched low-vol. A favorable single starting date is not robust evidence.",
    True,
)
blocks.append({"id": "phase-chart", "type": "chart", "chartId": "phases"})
decomp = []
for candidate, d in s["decomposition"].items():
    decomp.append(
        f"**{names[candidate]}**：年度重置链接 / annual-reset linked {d['annual_reset_linked_return']:.2%} → 连续资金、年度日历 / continuous annual calendar {d['continuous_annual_calendar_return']:.2%} → 全连续起点0 / continuous phase0 {d['continuous_phase0_return']:.2%}。账户重置差异 / account-reset difference {d['account_reset_difference_pp']:+.2f}pp，日历差异 / calendar difference {d['calendar_difference_pp']:+.2f}pp。"
    )
md(
    "decomposition",
    "账户重置和日历差异分开解释 / Reset decomposition",
    "\n\n".join(decomp)
    + "\n\n该分解按预定顺序可核对总和，但不是独立因果估计。不得把多个年度的重置回测链接，当成同一笔资金真实运行。\n\nThis is an order-dependent descriptive decomposition, not identified causal attribution.",
    True,
)
md(
    "design",
    "分批目标是在一个账户净额执行 / Experimental design",
    "四个固定起点0/5/10/15，各负责25%目标权重；某一批更新时，同一账户重平衡整体目标。未开始批次保留现金，其他批次的实际漂移也会被纠正。不是四个独立基金，也不是事后平均收益。\n\nFour phases are frozen in advance, not an exhaustive20-phase test. One shared account pays costs on netted aggregate orders, including drift correction; no hindsight-filled initial holdings. Standard41bps results are retained alongside doubled costs in the complete evidence.",
)
failed = [
    f"- {names[n]}：未通过 / failed: {', '.join(k for k, v in a['checks'].items() if not v) or 'none'}"
    for n, a in s["assessments"].items()
]
md(
    "gates",
    "经济筛选与统计证书分离 / Gates and uncertainty",
    "\n".join(failed)
    + f"\n\n全日历family PBO诊断 / diagnostic {s['statistics'].get('pbo')}；DSR敏感性 / sensitivity {s['statistics'].get('dsr')}；family placebo p={s['placebo'].get('p_value')}。这些不是全历史搜索校准后的置信度，也没有新增独立OOS。\n\nHistorical search debt and selection exposure remain. No Court threshold is lowered, and no formal PASS is inferred from these diagnostics.",
    True,
)
md(
    "verification",
    "独立账户与账本核验通过 / Verification",
    f"72个账户逐日现金、持仓、NAV、费用和年度收益重算一致；独立SQL与筛选判断一致，最大残差{s['max_balance_residual_cny']:.3g}元。新增72次预记试验，累计下界{s['raw_global_trial_lower_bound']}，旧预留不退款；冻结父结果保持不变，2025/2026读取行数0。\n\nAll72 accounts and their trial registrations reconcile. This verifies implementation, not reliable future returns.",
    True,
)
md(
    "limitations",
    "真实成交与独立证据仍是必要条件 / Limitations",
    "复权碎股、线性佣金和ADV容量仍为研究近似，未完成原始股数/交易手数/最低佣金/公司行为/真实开盘流动性验证。低波动对照也不是完整行业、规模和市场风格剥离。\n\nPassing a historical economic screen would only justify further investigation. Broker realism, full style attribution, complete multiplicity handling and genuinely independent evidence remain necessary.",
)
md(
    "next",
    "保留失败原因，按机制推进 / Next steps",
    "1. 固定四批政策如幸存，先冻结并开展真实成交及风格核验，不再调相位。\n2. 如未幸存，保留旧候选；根据完整日历与换手证据，设计新的有限机制，先登记再测试。\n3. 继续自动续研，禁止重复本轮操作或对封存窗口调参。\n\nFreeze survivors before deeper execution/style testing. If none survive, change the mechanism only through a newly registered bounded epoch; never recycle the most favorable historical phase.",
)
md(
    "questions",
    "下一条线索需要回答什么 / Open questions",
    "候选真正增加的是独立信息，还是低波动与调仓时点的偶然组合？分批目标纠正其他批次的权重漂移，会否产生额外换手？这些问题需要新的事前机制或执行验证，而不是继续挑选已知收益最高的配置。\n\nDoes the signal add independent information, and can it survive credible implementation without exploiting already-revealed outcomes?",
)
deep_source = {
    **source,
    "id": "deep",
    "label": "V11.9 frozen staggered lead additional stresses",
    "path": "docs/V11_9_DEEP.summary.json",
    "href": "https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.9-calendar-robustness/docs/V11_9_DEEP.zh.md",
    "query": {
        **source["query"],
        "sql": deep_audit["query"],
        "tables_used": [
            "artifacts/calendar-lead-stress/epoch-001/accounts/*.jsonl",
            "docs/V11_9_DEEP.summary.json",
        ],
        "filters": [
            "frozen staggered chip candidate and matched controls",
            "2023-2024 exposed development",
            "102/132bps or82bps delayed/capacity stresses",
        ],
    },
}
deep_rows = [{**r, "label": r["calendar"]} for r in deep["rows"]]
stress_text = "\n\n".join(
    f"**{r['calendar']}**：2023 / net {r['return2023']:.2%}，两年 / two-year {r['net_return']:.2%}，相对对照 / increment {100 * r['increment']:+.2f}pp。"
    for r in deep_rows
)
md(
    "deep-result",
    "进一步深挖：成本缓冲仍然薄 / Cost cushion remains thin",
    stress_text
    + "\n\n额外成本使2023绝对收益转负，但相对低波动的增量仍正，因此不能将这一压力失败解释为信号完全无效。图中是2023净收益，不是增量。结合仍失败的统计检验，只保留冻结观察候选。\n\nHigher costs remove the2023 absolute-profit cushion, while relative increments stay positive. Stress failure is not proof that the signal has no value; it does prevent stronger investability claims.",
    "deep",
)
blocks.append({"id": "deep-chart", "type": "chart", "chartId": "deep-stresses"})
a = deep["diagnostics"]["quarter_capacity"]["lowvol_attribution"]
t = deep["diagnostics"]["quarter_capacity"]["tail"]
md(
    "deep-style",
    "增量仍需独立证据 / Increment remains unconfirmed",
    f"低波动单变量回归R²={a['r_squared']:.3f}；年化截距 / annualized intercept {a['annualized_intercept']:.2%}，描述性HAC95区间 / interval [{a['hac95_annualized_intercept_interval'][0]:.2%}, {a['hac95_annualized_intercept_interval'][1]:.2%}]。用对照收益替换最高5个正超额日后，增量 / incremental return变为{100 * t['increment_if_top_active_days_equal_control']:+.2f}pp。\n\nThese are post-selection diagnostics, not a tradable deletion rule or causal attribution. All12 additional accounts pass independent accounting/SQL checks. Total search debt is now3268; the earlier statistical figures remain explicitly scoped to their3256-trial parent calendar study, not a new full-search certificate.",
    "deep",
)
added = blocks[-3:]
blocks = blocks[:-3]
insert = next(i for i, b in enumerate(blocks) if b["id"] == "next")
blocks[insert:insert] = added
blocks[1]["body"] = (
    "## 线索已深挖，仍未达到可用 Alpha / Technical summary\n\n首轮72账户发现一条固定分批筹码线索，随即冻结并完成12账户深挖。成本缓冲、统计不确定性与执行证据仍不足；已验证可用Alpha为0。保留该候选观察，自动研究继续，不选最优相位、不降低门槛。\n\nA staggered chip lead survived calendar screening and was immediately challenged. All84 accounts reconcile, but cost fragility and unconfirmed incremental information prevent an investable-Alpha claim. The frozen observational lead is retained."
)
blocks[1].pop("sourceId", None)
artifact = {
    "surface": "report",
    "manifest": {
        "version": 1,
        "surface": "report",
        "title": title,
        "sources": [source],
        "blocks": blocks,
        "charts": [
            {
                "id": "phases",
                "type": "bar",
                "title": "2023–2024连续账户增量 / Increment versus low-vol (pp)",
                "dataset": "phases",
                "sourceId": "calendar",
                "source": source,
                "encodings": {
                    "x": {"field": "label", "type": "nominal"},
                    "y": {"field": "increment_pp", "type": "quantitative"},
                },
                "options": {"orientation": "horizontal"},
                "palette": {"kind": "sequential", "name": "blue"},
                "height": 620,
                "valueFormat": "number",
            }
        ],
    },
    "snapshot": {"version": 1, "status": "ready", "datasets": {"phases": rows}},
    "sources": [source],
}
artifact["manifest"]["sources"].append(deep_source)
artifact["sources"] = artifact["manifest"]["sources"]
artifact["snapshot"]["datasets"]["deep"] = deep_rows
artifact["manifest"]["charts"].append(
    {
        "id": "deep-stresses",
        "type": "bar",
        "title": "2023净收益：冻结四批候选 / Staggered lead stresses",
        "dataset": "deep",
        "sourceId": "deep",
        "source": deep_source,
        "encodings": {
            "x": {"field": "label", "type": "nominal"},
            "y": {"field": "return2023", "type": "quantitative"},
        },
        "options": {"orientation": "horizontal"},
        "palette": {"kind": "sequential", "name": "blue"},
        "height": 320,
        "valueFormat": "percent",
    }
)
write_json(ROOT / "final-report-artifact.json", artifact)
write_json(
    ROOT / "final-report-qa.json",
    {
        "audience": "technical",
        "surface": "mcp-app",
        "confidence": "SHARE_WITH_CAVEATS",
        "required_structure": "title,summary,definitions before findings,phase evidence,reset comparison,methods,gates,verification,limitations,next,questions",
        "chart_contract": "one horizontal categorical bar;12 reviewed scenario rows richer than encodings;zero-included signed pp;single blue root,direct labels,620px",
        "omitted_visual": "two-candidate reset decomposition uses exact narrative values for audit, not a sparse trend",
        "validation": "independent72+12-account SQL and all economic/stress decisions",
        "second_chart": "four predeclared discrete cost/delay/capacity scenarios;2023absolute net return with zero baseline;bar repeats because neither chart is a trend",
        "rendering": "validator/render receipt required;native pixel-level QA may be unavailable",
    },
)
print(json.dumps({"blocks": len(blocks), "charts": 2, "rows": len(rows) + len(deep_rows)}))
