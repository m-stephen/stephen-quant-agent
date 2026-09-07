"""Bilingual, answer-first report from independently reconciled saved evidence."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/risk-stratified/epoch-001")


def build():
    s = json.loads(Path("docs/V11_14_RESULT.summary.json").read_text(encoding="utf-8"))
    if not s["independent_account_sql_ledger_pass"] or s["validated_alpha"]:
        raise ValueError("independently audited noncertified evidence required")
    survivors = [k for k, v in s["screen_survived"].items() if v]
    mechanisms = {"flow_price_absorption", "quiet_accumulation", "auction_exhaustion"}
    candidates = [r for r in s["rows"] if r["policy"] in mechanisms]
    for row in candidates:
        row["minimum_control_increment"] = min(
            row["increment_vs_" + c] for c in ("hash", "price_reversal", "lowvol")
        )
    base = sorted(
        (r for r in candidates if r["roundtrip_bps"] == 82),
        key=lambda r: (-r["minimum_control_increment"], r["account_key"]),
    )
    best = base[0]
    decision_zh = f"九个机制-风险组中，{len(survivors)}个通过两种成本下的完整预登记经济筛选，已认证可用Alpha仍为0。"
    decision_en = f"Of nine mechanism-stratum identities,{len(survivors)} pass the complete preregistered screen at both costs. Certified usable Alpha remains zero."
    sections = [
        ("decision", "测试结论 / Test conclusion", decision_zh, decision_en),
        (
            "scope",
            "现有数据上的新搜索范围 / New search support on existing data",
            "同一冻结源，2022预热、2023–2024重复暴露开发期484个交易日。按当时合格共同覆盖股票的vol20划分低/中/高三组；每组四个vol/ADV格子。三条固定联合rank机制，配同组hash、同组价格反转及旧严格低波锚点。32个连续300万元账户；不是32份独立证据。每个袖40股、四个相位平均净额，合计可包含至多160个目标股，而非始终只持40股。稀疏格子留现金；实际仓位受成交与停牌影响。",
            "Same frozen source,2022 warmup and484 reused2023–2024 development sessions. Three as-of vol20 strata,each with four vol/ADV cells;three fixed joint-rank mechanisms with hash/reversal controls and original lowvol anchor.32 continuous CNY3m accounts are not32 independent evidence sets. Forty names per sleeve,four netted phases can imply up to160 distinct targets,not a persistent40-name account. Sparse cells retain cash;fills/suspensions affect realized holdings.",
        ),
        (
            "ranking",
            "全组增量比较 / Whole-family incremental comparison",
            f"按82bps下相对三个对照的最小总收益增量排序，最高为{best['account_key']}：总收益{best['net_return']:.4%}、2023年{best['return2023']:.4%}、2024年{best['return2024']:.4%}，Sharpe {best['sharpe']:.4f}、最大回撤{best['max_drawdown']:.4%}。相对最强预声明对照的差为{100 * best['minimum_control_increment']:.4f}个百分点。该排序是描述性展示，不是换一个评判标准；所有组仍需两成本及年度门槛同时通过。",
            f"The largest minimum increment versus all three declared controls at82bps is {best['account_key']}:total return{best['net_return']:.4%},2023{best['return2023']:.4%},2024{best['return2024']:.4%},Sharpe{best['sharpe']:.4f},MDD{best['max_drawdown']:.4%}. The gap to the strongest declared control is{100 * best['minimum_control_increment']:.4f}percentage points. This is descriptive ordering,not a new acceptance rule;all annual and two-cost conditions remain binding.",
        ),
        (
            "mechanism",
            "机制与匹配边界 / Mechanisms and matching limits",
            "资金承接=资金流路径一致性秩×低20日收益秩；安静吸筹=资金流路径一致性秩×筹码宽度收缩秩；竞价衰竭=负竞价尾部路径秩×低20日收益秩。每格按平均秩/(N+1)计算，无学习方向或全样本拟合。标签只是经济假设，不能据此称为真实主力吸筹。对照在粗风险/流动性格子中配额相同，但实际行业、规模、beta、换手、现金与填单不精确相等。",
            "Absorption combines flow-path consistency with weak20-session prices;quiet accumulation combines flow consistency with shrinking chip-width path;auction exhaustion combines negative auction-tail path with weak prices. Contemporaneous cell average ranks/(N+1),no direction learning or full-sample fit. Names describe hypotheses,not proof of institutional accumulation. Quotas match broad risk/liquidity cells only,not exact industry,size,beta,turnover,cash or fills.",
        ),
        (
            "costs",
            "费用、容量和执行限制 / Costs,capacity and execution limits",
            "82bps包括双边佣金6、卖税10、双边滑点30；164bps逐项翻倍，不是原132bps压力。ADV容量继续采用既有次日可知上限。复权碎股账户尚不含完整真实整手、最低佣金、分红支付/配股现金和开盘成交容量认证。净值=现金+标记持仓，收益相对300万本金；增量是对策略对照，不是相对沪深300。",
            "82bps comprises6bps commission each side,10bps sell tax and30bps slippage each side;164 doubles every component,not the old132bps stress. The existing lagged-ADV capacity proxy is unchanged. Adjusted fractional units lack complete raw lots,broker minimum fees,dividend-payment/rights cash and certified opening liquidity. NAV equals cash plus marked positions;returns use CNY3m initial capital. Increments are versus strategy controls,not CSI300.",
        ),
        (
            "qa",
            "验证和统计边界 / Verification and inference",
            "19项新增合成测试通过；完整864 passed、1 skipped（113.47秒）。CI口径src/tests及本轮scripts的Ruff通过；全库ruff另发现旧V11.12 notebook导入顺序问题，未改动旧证据。独立SQL/Python核对32账户现金/净值/持仓/费用/容量/年收益/SR/回撤、SQLite no-fit契约和筛选重算；原两成本锚点字节重放一致。历史Trial下界3366。DSR/PBO/placebo未在此开发筛选认证，不能输出Court PASS。",
            "19 new synthetic regressions pass;full suite864passed,1skipped in113.47s. CI-scope src/tests and new scripts pass Ruff;repository-wide Ruff also finds a pre-existingV11.12 notebook import-order issue,left unchanged. Independent SQL/Python reconciles32 cash/NAV/mark/fee/capacity/year/SR/drawdown paths,native SQLite no-fit contracts and screens;both original cost anchors replay byte-identically. Historical Trial lower bound3366. DSR/PBO/placebo are not certified by this development screen;no Court PASS.",
        ),
        (
            "next",
            "继续研究的条件 / Conditions for continuation",
            "经济筛选幸存者原样冻结，再做完整预登记的容量/延迟/跨期/伪造/统计挑战；普通失败保留完整族和原因，再提出不同的有限机制，不翻转本轮弱年的方向或降低门槛。已有数据不足以证明可用时应明确限制，不把补齐全库当作每次探索的前提，也不保证一定能找到Alpha。原V11.11卡不变，不解封2025/2026。",
            "Freeze any economic survivor unchanged,then preregister deeper capacity,delay,temporal,placebo and statistical challenges. Archive the whole failed family before a different bounded mechanism;do not reverse weak-year directions or lower thresholds. State evidentiary limits,without making a whole-database rebuild a prerequisite or guaranteeing Alpha. OriginalV11.11 remains frozen;no unsealing2025/2026.",
        ),
    ]
    table = [
        "|Group|Policy|bps|2023|2024|Total|Sharpe|Max DD|Profit CNY|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["rows"]:
        table.append(
            f"|{r['group']}|{r['policy']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|"
        )
    for lang, title in (
        ("zh", "V11.14 风险分组机制测试报告"),
        ("en", "V11.14 Risk-Stratified Mechanism Test Report"),
    ):
        lines = ["# " + title, ""]
        for key, heading, zh, en in sections:
            lines += ["## " + heading, "", zh if lang == "zh" else en, ""]
            if key == "scope":
                lines += table + [""]
        lines += [
            "Method: [Bailey and López de Prado—Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf). Sources: V11_14_RESULT.summary.json; INDEPENDENT_AUDIT.json; Issue184 preregistration5560865736.",
            "",
            "Native schema validation recorded separately;visible/pixel QA deferred under quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_14_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    audit = json.loads((ROOT / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
    source = {
        "id": "accounts",
        "label": "Independent account reconciliation",
        "path": "docs/V11_14_RESULT.summary.json",
        "query": {
            "sql": audit["query"],
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["artifacts/risk-stratified/epoch-001/accounts/*.jsonl"],
            "description": "Original executed account SQL;annual/control/selection metadata independently enriched by audit_risk_stratified.py. Minimum_control_increment is total return minus maximum total return across the three preregistered controls,not a new acceptance statistic.",
            "filters": ["reused2023-2024", "all32 preregistered accounts"],
            "metric_definitions": {
                "net_return": "lastNAV/3000000-1",
                "minimum_control_increment": "net_return-max(same-group hash,same-group reversal,original lowvol),samecost;fractional return",
            },
        },
    }
    title = "Risk-Stratified Discovery | 风险分组机制研究"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
        if key == "ranking":
            blocks.append({"id": "comparison", "type": "chart", "chartId": "increments"})
    chart_rows = [
        {
            **r,
            "allocation": r["group"] + " / " + r["policy"],
            "cost_label": str(r["roundtrip_bps"]) + "bps",
        }
        for r in candidates
    ]
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
                        "title": "Total Increment versus Declared Controls by Cost",
                        "description": "2023–2024;each allocation minus strongest of its three frozen controls;fractional return;not independent Alpha",
                        "sourceId": "accounts",
                        "source": source,
                        "encodings": {
                            "x": {"field": "allocation", "type": "nominal"},
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
            "chart": "18rows,9allocations x2costs;grouped bars;zero baseline;cost legend;fractional increments;rich32account source data",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(json.dumps({"reports": 2, "survivors": survivors, "validated_alpha": False}))


if __name__ == "__main__":
    build()
