"""Bilingual bounded report, generated only from independently audited evidence."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/sparse-events/epoch-001")


def build():
    s = json.loads(Path("docs/V11_16_RESULT.summary.json").read_text(encoding="utf-8"))
    if not s["independent_audit_pass"] or s["validated_alpha"]:
        raise ValueError("audited exploratory evidence required")
    verification = json.loads((ROOT / "TEST_VERIFICATION.json").read_text(encoding="utf-8"))
    labels = {name: f"E{i + 1}" for i, name in enumerate(s["screen_survived"])}
    labels["anchor"] = "L"
    survivors = [labels[k] for k, v in s["screen_survived"].items() if v]
    by_key = {r["account_key"]: r for r in s["rows"]}
    chart_rows = []
    for r in s["rows"]:
        r["label"] = labels[r["identity"]]
        if r["policy"] == "event":
            controls = [
                by_key[f"{r['identity']}-{p}-{r['roundtrip_bps']}"]
                for p in ("risk_hash", "confirm_only")
            ]
            controls.append(by_key[f"anchor-lowvol-{r['roundtrip_bps']}"])
            r["minimum_control_increment"] = min(
                r["net_return"] - c["net_return"] for c in controls
            )
            chart_rows.append({**r, "cost_label": str(r["roundtrip_bps"]) + "bps"})
    best = max(
        (r for r in chart_rows if r["roundtrip_bps"] == 82),
        key=lambda r: r["minimum_control_increment"],
    )
    primary = [r for r in chart_rows if r["roundtrip_bps"] == 82]
    cash_low = min(r["mean_cash_fraction"] for r in primary)
    cash_high = max(r["mean_cash_fraction"] for r in primary)
    sections = [
        (
            "decision",
            "结论 / Decision",
            f"8种预登记事件中，{len(survivors)}种通过两成本完整探索筛选。已认证可用Alpha仍为0。"
            + (
                f"冻结继续验证：{','.join(survivors)}。"
                if survivors
                else "本轮全族留档，不转成实盘信号。"
            ),
            f"{len(survivors)}of8 preregistered event identities pass the complete two-cost exploratory screen. Certified usable Alpha remains zero."
            + (
                f"Freeze for further challenge:{','.join(survivors)}."
                if survivors
                else "Archive the entire family;do not promote it to live signals."
            ),
        ),
        (
            "scope",
            "范围与机制 / Scope and mechanism",
            "50个连续300万元账户，2023–2024共484交易日，2022仅预热。8身份×event/hash/confirm-only×82/164bps，再加两项冻结lowvol锚点。日K与资金流可见性共同准入，不要求分钟/竞价/筹码。每个身份由冲击→1或3日后确认生成，首次命中、40日冷却、次日开盘计划入场、20日计划持有。不是50份独立统计证据，也不是重新开放2025/2026。",
            "Fifty continuous CNY3m accounts over484 reused2023–2024 sessions,with2022 warmup. Eight identities×event/hash/confirm-only×82/164bps plus two frozen lowvol anchors. Daily/flow as-of eligibility does not require minute/auction/chip coverage. Shock then1/3-session confirmation,first-hit,40-session cooldown,next-open planned entry and20-session planned holding. These are not50 independent evidence sets;2025/26 remain sealed.",
        ),
        (
            "comparison",
            "完整候选对照 / Complete candidate comparison",
            f"按82bps相对最强预声明对照的总收益差描述性排序，最高为{best['label']}：总收益{best['net_return']:.4%}、2023年{best['return2023']:.4%}、2024年{best['return2024']:.4%}，Sharpe {best['sharpe']:.4f}、最大回撤{best['max_drawdown']:.4%}；净损益{best['profit_cny']:,.2f}元。其最小对照增量为{100 * best['minimum_control_increment']:.4f}个百分点。下图包含全部8身份及两成本，零线表示未胜过最强对照；排序不替代完整门槛。增量对照是策略，不是沪深300。",
            f"Descriptively,the largest82bps total-return gap to the strongest declared control is{best['label']}:total{best['net_return']:.4%},2023{best['return2023']:.4%},2024{best['return2024']:.4%},Sharpe{best['sharpe']:.4f},MDD{best['max_drawdown']:.4%},profit CNY{best['profit_cny']:,.2f}. Its minimum control increment is{100 * best['minimum_control_increment']:.4f}percentage points. The chart includes all eight identities at both costs;zero denotes no advantage versus the strongest comparator. Descriptive ranking does not replace the screen. Comparators are strategies,not CSI300.",
        ),
        (
            "matching",
            "匹配和交易解释 / Matching and execution",
            "控制股票匹配主事件计划入场日、风险格和退出时钟；confirm-only拿掉历史冲击。匹配覆盖=实际分配的控制目标名额/主目标新增名额，按计划入场年计；不是成交率。每个身份至多40个目标、每名2.5%，空额现金。满仓被拒事件同样进入冷却。到期未卖出由原执行器重试，实际持仓可超过40；期末未满20日持仓不强平。target_changes仍会按既有权重上限裁剪，不能称完全没有微小交易。",
            "Control targets match admission dates,risk cells and expiry clocks;confirm-only removes the earlier shock. Coverage is assigned control slots divided by new primary slots,by planned entry year—not fill rate. Up to40 desired2.5% slots;empty slots remain cash. Full-portfolio rejections consume cooldown. Blocked exits are retried and can exceed40 actual names;immature end holdings are marked,not forcibly liquidated. Existing cap trimming still applies under target_changes.",
        ),
        (
            "diagnosis",
            "本轮回答了什么 / What this epoch establishes",
            f"所有16个事件/成本账户的完整净收益均为负。匹配与事件数量门槛均通过，失败不是对照缺失或样本过少：是年度收益、回撤、风险调整表现及对照增量同时不足。82bps账户平均现金仅{cash_low:.2%}–{cash_high:.2%}；个股事件稀疏并没有变成组合低暴露。全市场事件汇集后目标多数时间仍接近满额，不能把本轮称为已经实现择时低换手。需要改变信息结构或可交易效应，而非继续给相同事件加别名。",
            f"All16 event/cost accounts have negative full-period net returns. Admission and matching gates pass;failure is not missing controls or too few events,but annual returns,drawdown,risk-adjusted performance and incremental value. Mean cash at82bps is only{cash_low:.2%}–{cash_high:.2%}:sparse instrument events did not produce low portfolio exposure. Pooling events across the market kept targets near capacity;this is not successful low-turnover timing. A different information structure or tradable effect is needed,not renamed events.",
        ),
        (
            "integrity",
            "验证与统计限制 / Verification and inference",
            f"完整测试{verification['passed']} passed、{verification['skipped']} skipped；Ruff通过。独立SQL从冻结源重新检查基础准入、过去20日标准化及风险分组；独立事件时钟、控制匹配、目标和全部50账户现金/净值/费用/容量/年度/SR/回撤及原生NOFIT账本重算通过。历史Trial下界3506。复用历史与多重搜索不能当成独立验证；本轮DSR/PBO/placebo均不作为正式认证输出。原两成本lowvol账户字节重放一致。",
            f"Full suite:{verification['passed']}passed,{verification['skipped']}skipped;Ruff passes. Independent raw-source SQL checks eligibility,previous20 normalizers and risk cells. Separate event/control/target reconstruction and all50 cash/NAV/fee/capacity/year/SR/drawdown/native-NOFIT audits pass. Raw Trial lower bound3506. Reused history and multiple search attempts are not independent validation;DSR/PBO/placebo are not certified here. Both original lowvol accounts replay byte-identically.",
        ),
        (
            "limitations",
            "数据和执行边界 / Source and execution limits",
            "82bps=双边各6佣金+卖方10税+双边各30滑点；164逐项翻倍，容量仍为原滞后ADV代理。复权碎股不是实际整手、最低佣金和公司行为现金流认证。供应商净流比不是订单簿OFI：Cont等论文研究的是报价簿事件及短时价格冲击，不能据此断言此日频代理有可交易预测力。该研究仅提供机制启发，不证明本轮因子。",
            "82bps=6commission each side+10sell tax+30slippage each side;164doubles components. Capacity remains the prior lagged-ADV proxy. Adjusted fractional units are not physical lots,minimum commissions or corporate-action cash certification. Vendor net-flow ratio is not order-book OFI:Cont et al.study book events and short-horizon impact,not evidence that this daily proxy predicts tradable returns. The paper motivates a question,not this factor's validity.",
        ),
        (
            "next",
            "后续处理 / Next action",
            "有完整探索幸存者时原样冻结，登记容量、延迟、市场状态和伪造挑战后继续深挖；否则保留负结果，另开真正不同的有限机制。禁止对同批结果不断改符号、阈值和年份来追逐合格曲线。不降低DSR/PBO/placebo等正式门槛，不保证一定找到Alpha。原候选和封存窗口不变。",
            "Freeze any complete exploratory survivor unchanged before capacity,delay,regime and placebo challenges. Otherwise preserve negative evidence and preregister a genuinely different bounded mechanism. Do not chase a passing curve by changing signs,thresholds or years on the same results. Formal DSR/PBO/placebo gates remain unchanged;Alpha is not guaranteed. Existing candidates and sealed windows remain untouched.",
        ),
    ]
    table = [
        "|ID|Policy|bps|2023|2024|Total|SR|MDD|Profit CNY|Cash mean|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["rows"]:
        table.append(
            f"|{r['label']}|{r['policy']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|{r['mean_cash_fraction']:.2%}|"
        )
    matching = ["|ID|Year|Admissions|Hash matched|Confirm matched|", "|---|---|---:|---:|---:|"]
    for identity, years in s["admissions"].items():
        for y, v in years.items():
            matching.append(
                f"|{labels[identity]}|{y}|{v['admissions']}|{v['risk_hash']}|{v['confirm_only']}|"
            )
    identities = [f"- {labels[k]}: `{k}`" for k in labels]
    for lang, title in (
        ("zh", "V11.16 稀疏事件测试报告"),
        ("en", "V11.16 Sparse Event Test Report"),
    ):
        lines = ["# " + title, ""]
        for key, heading, zh, en in sections:
            lines += ["## " + heading, "", zh if lang == "zh" else en, ""]
            if key == "scope":
                lines += identities + [""]
            if key == "comparison":
                lines += table + [""]
            if key == "matching":
                lines += matching + [""]
            if key == "limitations":
                lines += [
                    "[Cont,Kukanov and Stoikov: The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)",
                    "",
                ]
        lines += [
            "Evidence: V11_16_RESULT.summary.json; independent audit; Issue184 preregistration5561319318.",
            "",
            "Native artifact validation recorded separately. Visible/pixel QA deferred under quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_16_RESULT.{lang}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write("\n".join(lines))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text(encoding="utf-8")
        .replace("__ACCOUNT_GLOB__", "artifacts/sparse-events/epoch-001/accounts/*.jsonl")
    )
    source = {
        "id": "accounts",
        "label": "Independent saved-account reconstruction",
        "path": "docs/V11_16_RESULT.summary.json",
        "query": {
            "sql": query,
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["artifacts/sparse-events/epoch-001/accounts/*.jsonl"],
            "description": "Executed original account aggregation;annual metrics,matched counts and minimum-control gaps independently enriched by audit_sparse_events.py/build_sparse_events_report.py.",
            "filters": ["reused2023-2024", "all50 preregistered accounts"],
            "metric_definitions": {
                "net_return": "finalNAV/3000000-1",
                "minimum_control_increment": "event return minus max(risk_hash,confirm_only,originallowvol),samecost,fractional return",
            },
        },
    }
    title = "Sparse Sequence Events | 稀疏次序事件"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
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
                        "description": "All eight identities,2023–2024;fractional return;zero=no advantage over strongest declared control",
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
            "chart_contract": "16rows,8identities x2costs;comparison grouped bars;zero baseline;8compactlabels;rich50account source and identity mapping",
            "palette": "two-cost categorical roots;legend plus explicit cost labels",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(json.dumps({"reports": 2, "survivors": survivors, "validated_alpha": False}))


if __name__ == "__main__":
    build()
