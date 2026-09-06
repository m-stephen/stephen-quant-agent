"""Generate bilingual evidence, complete aggregate tables and one native artifact."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/peer-information/epoch-001")


def build():
    s = json.loads(Path("docs/V11_17_RESULT.summary.json").read_text(encoding="utf-8"))
    if not s["independent_audit_pass"] or s["validated_alpha"]:
        raise ValueError("independently audited exploratory evidence required")
    labels = {k: f"P{i + 1}" for i, k in enumerate(s["screen_survived"])}
    labels["anchor"] = "L"
    winners = [k for k, v in s["screen_survived"].items() if v]
    by_key = {r["account_key"]: r for r in s["rows"]}
    chart_rows = []
    for r in s["rows"]:
        r["label"] = labels[r["identity"]]
        if r["policy"] == "peer":
            controls = [
                by_key[f"{r['identity']}-{p}-{r['roundtrip_bps']}"]
                for p in ("own", "shuffle", "hash")
            ]
            controls.append(by_key[f"anchor-lowvol-{r['roundtrip_bps']}"])
            chart_rows.append(
                {
                    **r,
                    "minimum_control_increment": min(
                        r["net_return"] - c["net_return"] for c in controls
                    ),
                    "cost_label": f"{r['roundtrip_bps']}bps",
                }
            )
    best = max(
        (r for r in chart_rows if r["roundtrip_bps"] == 82),
        key=lambda r: r["minimum_control_increment"],
    )
    coverage = ", ".join(f"{y}: {d['mean_common_ratio']:.2%}" for y, d in s["coverage"].items())
    tests = json.loads((ROOT / "TEST_VERIFICATION.json").read_text())
    sections = [
        (
            "summary",
            "结果 / Result",
            f"六个跨股统计关联候选中，{len(winners)}个通过两种成本完整探索筛选。已认证可用Alpha仍为0。"
            + (
                f"需原样冻结并深入验证：{', '.join(winners)}。"
                if winners
                else "本轮全部留档，不将最好看的曲线称为可用Alpha。"
            ),
            f"{len(winners)}of6 statistical-peer identities survive the complete two-cost exploratory screen. Certified usable Alpha remains zero."
            + (
                f"Freeze unchanged for deeper validation:{', '.join(winners)}."
                if winners
                else "Archive this family;the best-looking curve is not a usable Alpha."
            ),
        ),
        (
            "scope",
            "实验范围 / Experiment scope",
            "50个连续300万元账户，2023–2024共484个交易日，2022用于训练及预热。两种信号×三风险组×四政策×两成本，加两项原lowvol锚点。全部数据为已复用开发史，并非新的独立样本；2025/2026未读取。",
            "Fifty continuous CNY3m accounts over484 sessions in2023–2024,with2022 training/warmup. Two signals×three risk groups×four policies×two costs plus two original lowvol anchors. All years are reused development evidence,not new independent samples;2025/26 were not accessed.",
        ),
        (
            "comparison",
            "净收益增量 / Net incremental evidence",
            f"按82bps相对最强预声明对照的总收益差描述性排序，最高为{best['label']}（{best['identity']}）：总收益{best['net_return']:.4%}，2023年{best['return2023']:.4%}，2024年{best['return2024']:.4%}；Sharpe {best['sharpe']:.4f}，最大回撤{best['max_drawdown']:.4%}，净损益{best['profit_cny']:,.2f}元。最小对照增量{best['minimum_control_increment'] * 100:.4f}个百分点。图中展示全部六身份、两成本；零线代表没有胜过最强对照，+3个百分点只是完整筛选的一项。比较基准是同组自身信号/打乱图/hash及旧lowvol，不是沪深300。",
            f"Descriptively,the highest82bps increment over the strongest declared control is{best['label']}({best['identity']}):total{best['net_return']:.4%},2023{best['return2023']:.4%},2024{best['return2024']:.4%},Sharpe{best['sharpe']:.4f},MDD{best['max_drawdown']:.4%},profit CNY{best['profit_cny']:,.2f}. Minimum control increment is{best['minimum_control_increment'] * 100:.4f}percentage points. All six identities and both costs are shown;zero means no advantage over the strongest comparator,and+3pp is only one screening condition. Controls are same-group own signal,shuffled graph,hash and original lowvol—not CSI300.",
        ),
        (
            "model",
            "图和信号定义 / Graph and signal definitions",
            "分别用2022及2022–2023构建下一年图，去掉训练末尾5个交易日。逐日收益先去当日市场均值，再计算至少120日共同观察的Pearson相关，选10个正相关≥0.15的统计邻居。价格信号是邻居五日收益加权均值减本股五日收益；资金流信号是邻居五日净流比均值减本股均值。两图均需至少8个当前可用邻居。无监督拟合只绑定真实观察日期，不虚构收益标签。",
            "Graphs for2023 and2024 use2022 and2022–2023 respectively,excluding the final five training sessions. Daily returns are cross-sectionally demeaned;Pearson edges require120 overlapping observations,with ten positive neighbors>=.15. Price gap is weighted peer five-day return minus own return;flow gap uses five-day mean net-flow/turnover ratios. Both graphs require eight currently available peers. Native unsupervised lineage records observation dates,not fabricated return labels.",
        ),
        (
            "controls",
            "对照与覆盖 / Controls and coverage",
            f"图端点在训练期12个风险格内按固定哈希置换，保留拓扑、权重和粗风险结构。真实图与打乱图使用相同当前接收股票池，每年平均覆盖：{coverage}。公共风险格均值减自身数值与自身负值在格内排序相同，因此共用一个对照账户，不能把两者称为独立证明。固定一次打乱不等于统计placebo检验。",
            f"A fixed training-risk-cell node permutation preserves topology,weights and broad risk structure. True and shuffled graphs share receiver support;mean annual coverage:{coverage}. Common cell value minus own value has exactly the own-negative within-cell ordering,so it intentionally shares that account rather than pretending to be independent evidence. A single structural shuffle is not a statistical placebo test.",
        ),
        (
            "execution",
            "交易和筛选定义 / Execution and screening",
            "每风险组四个小格各选10只，前13名保留旧目标；20日周期，四相位0/5/10/15组合为一个连续账户，每个子组合单名2.5%。82bps=双边各6佣金+卖出10税+双边各30滑点；164逐项翻倍。必须同时满足两成本、两年正收益、Sharpe≥0.7、回撤不低于−25%、每个对照总增量≥3个百分点且年度差不低于−5个百分点，并通过覆盖和完整审计。",
            "Each risk group selects ten stocks in each of four cells,retaining incumbents in top13;four fixed20-session phases0/5/10/15 form one continuous account,with2.5% per name per sleeve.82bps=6commission each side+10sell tax+30slippage each side;164doubles all components. Both costs must pass positive returns in both years,Sharpe>=.7,MDD>=-.25,total increment>=3pp and annual increment>=-5pp against every control,plus coverage and audits.",
        ),
        (
            "audit",
            "独立验证 / Independent verification",
            f"完整测试{tests['passed']} passed、{tests['skipped']} skipped，Ruff通过。独立源SQL复核{s['input_rows']:,}条记录、全部{s['graph_checks']['selected_edges']:,}条选中边的相关性、固定样本{s['graph_checks']['top10_receivers_sampled']}个接收节点的top10，以及置换与覆盖。全部24组新目标、50账户现金/NAV/成本/容量和96份原生拟合证据重算通过。历史Trial下界3556。所有失败结果同样保留。",
            f"Full suite:{tests['passed']}passed,{tests['skipped']}skipped;Ruff passes. Independent SQL checks{s['input_rows']:,}source rows,all{s['graph_checks']['selected_edges']:,}selected correlations,top10 selection for{s['graph_checks']['top10_receivers_sampled']}fixed receiver samples,permutations and coverage. All24new target sets,50cash/NAV/cost/capacity accounts and96native fit records reconcile. Raw Trial lower bound3556.All failures remain in evidence.",
        ),
        (
            "limits",
            "不能据此宣称的内容 / What this cannot establish",
            "收益相关图不是真实供应链或历史行业成员表。Cohen与Frazzini使用真实客户–供应商经济联系；这里只借鉴跨股信息可能缓慢反映的研究问题，不声称复现其因果或收益。现有复权碎股、滞后ADV容量代理仍不等于实盘整手、最低佣金、公司行为现金认证。图top10仅对固定样本独立复算全部候选边，选中边则全部校验。开发史反复使用、多重搜索和普通相关性都限制证据强度，DSR/PBO/placebo未作为正式认证输出。",
            "Return-correlation graphs are not actual supply chains or historical industry memberships. Cohen and Frazzini use customer–supplier economic links;this tests a related cross-stock information question,not their causal mechanism or returns. Adjusted fractional units and lagged-ADV capacity are not live lots,minimum-commission or corporate-action cash certification. Independent exhaustive top10 candidate ranking covers a fixed receiver sample;all selected edge statistics are checked. Reused development history,multiplicity and correlation limit inference. No certified DSR/PBO/placebo output is claimed.",
        ),
        (
            "next",
            "后续与未决问题 / Next steps and open questions",
            "完整幸存者先冻结，再预登记延迟、容量、跨状态及伪造挑战；否则不反复改本轮阈值/符号/持有期追曲线，而是更换有明确新增信息或交易机制的有限实验。任何更改均累计Trial，不把成本、资金规模或基准悄悄变更。需要确认的是跨股信息增量能否覆盖交易摩擦、是否稳定跨年，以及是否能获得独立前向支持，而不是单看某一条最高收益曲线。",
            "Freeze complete survivors before registered delay,capacity,regime and falsification challenges. Otherwise change to a genuinely distinct finite mechanism,not threshold/sign/horizon chasing within this batch. Every change adds Trial debt;costs,capital and comparators are not silently replaced. Remaining questions are whether incremental information pays for execution,stays stable across years,and earns independent forward support—not which single curve is highest.",
        ),
    ]
    table = [
        "|ID|Policy|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Mean cash|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["rows"]:
        table.append(
            f"|{r['label']}|{r['policy']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|{r['mean_cash_fraction']:.2%}|"
        )
    paper = "https://pages.stern.nyu.edu/~afrazzin/pdf/Economic%20Links%20and%20Predictable%20Returns%20-%20Cohen%20and%20Frazzini.pdf"
    for language, title in (
        ("zh", "V11.17 跨股统计关联测试报告"),
        ("en", "V11.17 Statistical Peer Test Report"),
    ):
        lines = ["# " + title, ""]
        for key, heading, zh, en in sections:
            lines += ["## " + heading, "", zh if language == "zh" else en, ""]
            if key == "scope":
                lines += [f"- {v}: `{k}`" for k, v in labels.items()] + [""]
            if key == "comparison":
                lines += table + [""]
            if key == "limits":
                lines += [
                    f"[Cohen and Frazzini: Economic Links and Predictable Returns]({paper})",
                    "",
                ]
        lines += [
            "Evidence: V11_17_RESULT.summary.json;independent audit;Issue184 preregistration5561787787.",
            "",
            "Native artifact schema validation recorded separately. Visible/pixel QA deferred under the quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_17_RESULT.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write("\n".join(lines))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text()
        .replace("__ACCOUNT_GLOB__", "artifacts/peer-information/epoch-001/accounts/*.jsonl")
    )
    source = {
        "id": "accounts",
        "label": "Independent peer account reconstruction",
        "path": "docs/V11_17_RESULT.summary.json",
        "query": {
            "sql": query,
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["artifacts/peer-information/epoch-001/accounts/*.jsonl"],
            "description": "Original executed account aggregation;annual metrics and peer-control increments independently enriched by audit_peer_information.py and this report builder.",
            "filters": ["reused2023-2024", "all50 predeclared accounts"],
            "metric_definitions": {
                "net_return": "finalNAV/3000000-1",
                "minimum_control_increment": "peer net return minus maximum own/shuffle/hash/originallowvol net return,samecost,fractional rate",
            },
        },
    }
    title = "Statistical Peer Information | 跨股统计关联"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        mapping = (
            "\n\n" + "; ".join(f"{v}: {k}" for k, v in labels.items()) if key == "scope" else ""
        )
        blocks.append(
            {"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}" + mapping}
        )
        if key == "comparison":
            blocks.append({"id": "plot", "type": "chart", "chartId": "increments"})
    write_json(
        ROOT / "report-artifact.json",
        {
            "surface": "report",
            "manifest": {
                "version": 1,
                "surface": "report",
                "title": title,
                "blocks": blocks,
                "sources": [source],
                "charts": [
                    {
                        "id": "increments",
                        "type": "bar",
                        "dataset": "increments",
                        "title": "Net Increment against Declared Controls by Cost",
                        "description": "All six identities,2023–2024;fractional return;zero means no advantage over strongest control",
                        "sourceId": "accounts",
                        "source": source,
                        "encodings": {
                            "x": {"field": "label", "type": "nominal"},
                            "y": {"field": "minimum_control_increment", "type": "quantitative"},
                            "color": {"field": "cost_label", "type": "nominal"},
                        },
                        "height": 420,
                        "palette": {"kind": "categorical", "name": "default"},
                    }
                ],
            },
            "snapshot": {
                "version": 1,
                "status": "ready",
                "datasets": {"increments": chart_rows, "accounts": s["rows"]},
            },
            "sources": [source],
        },
    )
    write_json(
        ROOT / "report-qa.json",
        {
            "surface": "codex_desktop:mcp-app",
            "mode": "unknown",
            "chart_contract": "12rows;all6identities x2costs;grouped category bars;zero baseline;compactlabels;rich account sources and explicit identity mapping",
            "palette": "two-cost roots;legend plus explicit cost labels",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(json.dumps({"reports": 2, "exploratory_survivors": winners, "validated_alpha": False}))


if __name__ == "__main__":
    build()
