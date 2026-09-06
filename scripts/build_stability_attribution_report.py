"""Answer-first bilingual report from independently checked aggregate evidence."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/stability-attribution/epoch-001")


def build():
    s = json.loads(Path("docs/V11_13_RESULT.summary.json").read_text(encoding="utf-8"))
    if not s["independent_account_sql_ledger_pass"] or s["validated_alpha"]:
        raise ValueError("audited noncertified evidence required")
    rows = {r["account_key"]: r for r in s["rows"]}
    old, new = (rows[f"stable_lowrisk-{m}-82"] for m in ("full_target", "target_changes"))
    ticket_drop = 1 - new["executed_tickets"] / old["executed_tickets"]
    volume_drop = 1 - new["traded_cny"] / old["traded_cny"]
    gross = s["attribution"]["0"]["membership_increment"]["full_target"]
    net = s["attribution"]["82"]["membership_increment"]["full_target"]
    sections = [
        (
            "decision",
            "结论 / Decision",
            "未发现可用 Alpha。稳定成员配置仍有历史增量，但减少重复权重维护只带来小幅改善；原规则与新规则都因双倍成本下2023年亏损而未通过完整经济筛选。保留旧冻结记录，新规则保留为可选执行方式，不将其设成默认或授予认证。",
            "No usable Alpha was found. Membership stability retains historical increment, but avoiding repeated weight maintenance adds only a small improvement. Both modes fail the complete economic screen because2023 is negative at doubled costs. Keep the frozen observation and optional new execution mode;no default promotion or certificate.",
        ),
        (
            "scope",
            "范围与定义 / Scope and definitions",
            "2023–2024共484个交易日，300万元连续复权碎股模型账户。两份已冻结目标×两种维护方式×零费/82/164bps=12个账户，无新拟合或选股。82bps由双边佣金6、卖税10、双边滑点30组成；164bps逐项翻倍。零费仅作路径反事实。收益相对初始本金；对照是同维护规则的严格低波股票池，不是沪深300等市场指数。",
            "484 sessions in reused2023–2024;continuous CNY3m adjusted fractional-share model accounts. Two frozen target schedules × two maintenance modes ×0/82/164bps produce12 accounts without fitting or new stock selection.82bps comprises6bps commission each side,10bps sell tax and30bps slippage each side;164 doubles every term. Zero cost is a path counterfactual only. Returns are relative to initial capital;the matched control is strict low-volatility under the same maintenance mode,not a market index.",
        ),
        (
            "maintenance",
            "小单减少不等于经济优势 / Fewer tickets are not sufficient",
            f"82bps稳定配置的有效成交票据由{old['executed_tickets']:,}降至{new['executed_tickets']:,}（−{ticket_drop:.2%}），但累计绝对成交金额仅下降{volume_drop:.2%}。收益由{old['net_return']:.4%}升至{new['net_return']:.4%}，改善{100 * (new['net_return'] - old['net_return']):.4f}个百分点。新规则两年盈利{new['profit_cny']:,.2f}元，模型期末净值{new['final_nav']:,.2f}元，并非券商真实可兑现收益。有效票据按绝对成交金额>1e-8元计数，与V11.12逐笔>0的诊断口径不同。",
            f"At82bps,stable executed tickets fall from{old['executed_tickets']:,} to{new['executed_tickets']:,} ({ticket_drop:.2%}),but cumulative absolute traded notional falls only{volume_drop:.2%}. Return improves from{old['net_return']:.4%} to{new['net_return']:.4%},a{100 * (new['net_return'] - old['net_return']):.4f}percentage-point gain. New-policy model profit is CNY{new['profit_cny']:,.2f},final NAV CNY{new['final_nav']:,.2f};not brokerage-realizable performance. Tickets require absolute execution>1e-8CNY,unlike the priorV11.12 positive-ticket diagnostic.",
        ),
        (
            "membership",
            "成员稳定性与成本的拆分 / Membership and cost decomposition",
            f"原维护模式下，稳定成员相对严格低波的零费增量为{gross:.4%}，82bps净增量为{net:.4%}；两者差{100 * (net - gross):.4f}个百分点来自完整收费路径差异（含复利和现金缩放），不是简单加回手续费。新维护方式也保留约6.42个百分点的零费成员增量。历史优势不全是手续费节约，但尚不能区分行业/规模/风险暴露、成员路径运气和独立预测信息。",
            f"Under legacy maintenance,the stable-minus-lowvol zero-cost increment is{gross:.4%},versus{net:.4%} at82bps. The{100 * (net - gross):.4f}percentage-point difference is attributable to the full cost-path contrast within this simulator,including compounding and funding scaling,not fee add-back. New maintenance retains approximately6.42pp zero-cost membership increment. The advantage is not entirely fee savings,but industry/size/risk exposure,membership-path luck and independent predictive information remain unresolved.",
        ),
        (
            "stress",
            "未通过的门槛 / Failed condition",
            "164bps下，原稳定规则2023年−1.4452%，新规则−1.2170%；两者2024年仍为正。年度均正的冻结条件失败，不能事后删除2023年或把164bps降成132bps来过关。该结果不是全部历史压力都失败，也不证明永远无效；它表明当前优势不够稳健。",
            "At164bps,2023 returns are−1.4452% for original stable maintenance and−1.2170% for target_changes;2024 remains positive. The frozen both-years-positive condition fails. Do not discard2023 or relabel132bps as doubled82bps to pass. This is not failure of every previous stress or proof of permanent ineffectiveness;the current edge lacks robustness.",
        ),
        (
            "execution",
            "执行和统计边界 / Execution and inference limits",
            "实际盘后单股最大权重约3.05%–3.13%，超过声明目标2.5%，由价格漂移/受限订单造成；新规则仅在刷新时申请减仓，不能声称实际始终不超限。该账户仍没有真实整手、最低佣金、股数/分红到账/配股账本和实际开盘容量证明。12个相关账户不是12份独立证据；2023/2024反复暴露，DSR/PBO/placebo未在本轮认证，不能输出Court PASS。",
            "Maximum realized close weights are approximately3.05%–3.13%,above the declared2.5% target because of drift/constrained orders. Refresh-time trim requests are not an always-enforced cap. Raw lots,minimum commissions,physical share/dividend-payment/rights accounting and real opening liquidity remain unverified. Twelve related accounts are not twelve independent evidence sets;reused2023/2024 do not provide a new independent Court certificate. DSR/PBO/placebo are not certified in this run.",
        ),
        (
            "qa",
            "验证与复现 / Validation and reproducibility",
            "15项新增回归通过；完整843 passed、1 skipped（117.17秒）。两个82bps旧账户逐字节重放一致；独立SQL与Python核对12账户的净值、现金流、费用、持仓标记、年收益、夏普、回撤、反事实增量及SQLite无拟合契约。累计Trial下界3334。独立审计最初将首日非调仓现金目标的当日08:00时间误判，已更正为完整时间早于09:30；只重核已存证据，没有重跑行情或增加搜索。",
            "15 new regressions pass;full suite843passed,1skipped in117.17s. Both legacy82bps accounts replay byte-identically. Independent SQL/Python checks reconcile12 accounts,NAV,cashflow,fees,marks,annual returns,Sharpe,drawdown,contrasts and SQLite unfitted contracts. Raw Trial lower bound3334. The auditor initially rejected a valid first-day08:00 inactive cash target;corrected to full timestamps before09:30 and reread saved evidence only,no market rerun or search.",
        ),
        (
            "next",
            "后续方向 / Next direction",
            "不继续围绕2023弱年调成本或维护阈值。下一轮优先检验搜索股票池是否过窄：在已授权冻结源中，按当时波动率划分低/中/高风险组，做有限的机制排序与同组风险匹配对照，预登记完整预算和成本后再运行。保留旧低波对照，不用事后最优风险组替代全家族评估。后续有增量再做CPCV、伪造检验和可信成交深挖；独立窗口仍须遵守原封存授权。",
            "Do not tune cost or maintenance thresholds to repair the weak2023 year. Next test whether the search universe is too narrow:predeclare a finite mechanism-ranking experiment in as-of low/middle/high volatility groups using existing authorized frozen inputs,with same-group risk-matched controls and complete costs/budget. Keep old low-vol controls and evaluate the entire family,not the best observed risk group. Only surviving increments advance to CPCV,placebos and credible execution;independent windows retain their authorization protocol.",
        ),
    ]
    table = [
        "|Policy|Maintenance|bps|2023|2024|Total|Sharpe|Max DD|Cost CNY|",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in s["rows"]:
        table.append(
            f"|{row['policy']}|{row['mode']}|{row['roundtrip_bps']}|{row['return2023']:.4%}|{row['return2024']:.4%}|{row['net_return']:.4%}|{row['sharpe']:.4f}|{row['max_drawdown']:.4%}|{row['cost_cny']:,.2f}|"
        )
    reference = "Method reference:[Bailey and López de Prado—Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551). Evidence:docs/V11_13_RESULT.summary.json;single-use operation;independent audit;Issue184 preregistration5560589655."
    for lang, title in (
        ("zh", "V11.13 持仓稳定性归因测试报告"),
        ("en", "V11.13 Stability Attribution Test Report"),
    ):
        lines = ["# " + title, ""]
        for key, heading, zh, en in sections:
            lines += ["## " + heading, "", zh if lang == "zh" else en, ""]
            if key == "scope":
                lines += table + [""]
        lines += [
            reference,
            "",
            "Native report schema QA recorded separately;visible/pixel QA deferred under quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_13_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    audit = json.loads((ROOT / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
    source = {
        "id": "accounts",
        "label": "Independently reconciled frozen-target accounts",
        "path": "docs/V11_13_RESULT.summary.json",
        "query": {
            "sql": audit["query"],
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["artifacts/stability-attribution/epoch-001/accounts/*.jsonl"],
            "description": "Original executed SQL over12 saved continuous accounts;annual/turnover/group metadata independently enriched by audit_stability_attribution.py. No raw market query or selection.",
            "metric_definitions": {
                "net_return": "last NAV / CNY3000000 - 1;484 sessions;not annualized",
                "roundtrip_bps": "0diagnostic,82base,164exact doubled modeled costs",
            },
        },
    }
    title = "Stability Attribution | 持仓稳定性归因"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
        if key == "scope":
            blocks.append({"id": "comparison", "type": "chart", "chartId": "returns"})
    chart_rows = [
        {
            **r,
            "allocation": r["policy"] + " / " + r["mode"],
            "cost_label": str(r["roundtrip_bps"]) + "bps",
        }
        for r in s["rows"]
    ]
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": title,
            "blocks": blocks,
            "sources": [source],
            "charts": [
                {
                    "id": "returns",
                    "type": "bar",
                    "dataset": "accounts",
                    "title": "2023–2024 Model Returns by Allocation and Cost",
                    "description": "Zero-cost diagnostic and82/164bps accounts;reused development history,not independent Alpha",
                    "sourceId": "accounts",
                    "source": source,
                    "encodings": {
                        "x": {"field": "allocation", "type": "nominal"},
                        "y": {"field": "net_return", "type": "quantitative"},
                        "color": {"field": "cost_label", "type": "nominal"},
                    },
                    "height": 380,
                    "palette": {"kind": "categorical", "name": "default"},
                }
            ],
        },
        "snapshot": {"version": 1, "status": "ready", "datasets": {"accounts": chart_rows}},
        "sources": [source],
    }
    write_json(ROOT / "report-artifact.json", artifact)
    write_json(
        ROOT / "report-qa.json",
        {
            "surface": "codex_desktop:mcp-app",
            "mode": "unknown",
            "chart": "12rows;4allocations x3costlevels;grouped bars withcostlegend;zero baseline;fractional returns;380px",
            "confidence": "SHARE_WITH_CAVEATS",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
        },
    )
    print(json.dumps({"reports": 2, "chart_rows": len(chart_rows), "validated_alpha": False}))


if __name__ == "__main__":
    build()
