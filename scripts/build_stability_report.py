"""Bilingual stress report and SQL-backed native companion for the frozen lead."""

import json
from pathlib import Path

import duckdb

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/stability-challenge/epoch-001")


def build():
    s = json.loads(Path("docs/V11_11_DEEP.summary.json").read_text(encoding="utf-8"))
    if not s["independent_sql_account_target_and_native_trial_pass"]:
        raise ValueError("independent audit required")
    d = s["diagnostics"]["baseline_82"]
    a = d["lowvol_attribution"]
    sections = [
        (
            "summary",
            "结论 / Technical summary",
            "冻结的稳定低风险配置通过全部5个压力情景、10个配对账户。仍为历史配置观察线索，未成为可用Alpha；资金流/竞价/筹码新机制的独立增量仍为0。132bps下2023仅盈利0.43%，不能忽略薄弱年份。",
            "The frozen stable low-risk allocation survives all five stress scenarios and ten matched accounts. It remains a historical allocation observation,not usable Alpha;the three new signals still add zero. At132bps,2023profit is only0.43%,a thin cushion.",
        ),
        (
            "scope",
            "范围与定义 / Scope and definitions",
            "2023–2024已暴露历史、484交易日、300万元连续模型账户；增量=相同情景下两条净总收益率的百分点差，不是相对沪深300收益。目标冻结、无重新拟合；低风险200池、40股/批、四批固定相位保持原样。",
            "Reused2023–2024 history,484sessions,one CNY3m model account. Increment is the total-return difference versus the same-scenario strict low-vol control,not CSI300 excess. Targets are immutable with no refitting:low-risk200pool,40names per cohort,four fixed phases.",
        ),
        (
            "finding",
            "全部压力结果 / Complete stress findings",
            "82/102/132bps、四分之一ADV代理容量及额外延迟一天全部满足两年为正、Sharpe≥0.7、回撤≥−25%、增量≥3pp、年度增量≥−5pp。容量1/4与基线的收益相同，说明此代理约束在这轮没有改变实际成交，并不证明真实开盘流动性充足。",
            "82/102/132bps,quarter ADV capacity and one extra session delay all satisfy positive returns in both years,Sharpe≥0.7,drawdown≥−25%,total increment≥3pp and annual increment≥−5pp. Quarter-capacity returns equal baseline:the proxy constraint did not change realized fills here;this does not prove real opening liquidity.",
        ),
        (
            "diagnostics",
            "增量来源与风险暴露 / Increment and risk exposure",
            f"82bps相比严格低波动多赚{d['net_pnl_difference_cny']:,.2f}元，其中实际费用少{d['fee_saving_cny']:,.2f}元。相减后的记账差不是零费用反事实，不能称为纯因子收益。低波动收益回归beta={a['beta_to_lowvol']:.4f}，R²={a['r_squared']:.4f}；名义年化截距{a['annualized_intercept']:.2%}、lag20 HAC区间[{a['hac95_annualized_intercept_interval'][0]:.2%},{a['hac95_annualized_intercept_interval'][1]:.2%}]。这未校正事后选择，也未控制行业/规模/市场。最高5个正主动收益日替换为对照后增量仍有{100 * d['tail']['increment_if_top_active_days_equal_control']:.2f}pp，仅为不可交易的描述性诊断。",
            f"At82bps,net P&L exceeds strict low-vol by CNY{d['net_pnl_difference_cny']:,.2f},with CNY{d['fee_saving_cny']:,.2f} lower actual fees. Subtracting these is accounting,not a zero-fee counterfactual or pure factor return. Low-vol beta={a['beta_to_lowvol']:.4f},R²={a['r_squared']:.4f};nominal annualized intercept={a['annualized_intercept']:.2%},lag20 HAC interval=[{a['hac95_annualized_intercept_interval'][0]:.2%},{a['hac95_annualized_intercept_interval'][1]:.2%}]. Neither selection correction nor industry/size/market controls are applied. Replacing the five best active days with control returns leaves{100 * d['tail']['increment_if_top_active_days_equal_control']:.2f}pp increment;a nontradable descriptive diagnostic.",
        ),
        (
            "methods",
            "方法与独立验证 / Methods and independent checks",
            "读取前预登记10份显式无拟合原生契约，历史Trial3310→3320；失败/未执行预留保留。82/102账户与父结果逐字节一致。逐条检验父目标+声明延迟、目标时序、权重、现金持仓净值、收益、每笔费率、记录容量、年度复利、SQL回撤及10份SQLite结果。完整测试811 passed/1 skipped，Ruff通过。",
            "Ten explicit unfitted native contracts precede source reads;raw Trial debt3310→3320,retaining failures and unused reservations.82/102accounts replay parent bytes exactly. Audit verifies frozen target+declared delay,chronology,weights,NAV/cash/positions,returns,order fees,recorded capacity,annual compounding,SQL drawdown and all ten SQLite results. Full suite811passed/1skipped;Ruff passes.",
        ),
        (
            "limits",
            "不能越过的结论边界 / Limits on inference",
            "这不是新OOS，也未通过完整历史DSR、PBO、signal/return/universe placebo和独立前向Court。单条事后挑出的配置无法构成可识别的策略选择PBO。账务PASS不等于原始股数/整手/最低佣金/公司行为完整、真实开盘容量或可实盘。2025/2026未读取，旧候选及main未修改。",
            "This is not fresh OOS or full-history DSR/PBO,signal/return/universe placebo or independent forward Court. One post-selected allocation cannot support identifiable strategy-selection PBO. Accounting PASS does not certify raw shares/lots/minimum fees/corporate events,real open liquidity or deployability.2025/2026,old leads and main remain untouched.",
        ),
        (
            "next",
            "下一步与待解问题 / Next steps and open questions",
            "保持冻结，不继续调200池/40持仓/调仓相位来美化历史。下一有限任务先查原始价格/复权/公司行为及实际股数执行证据，明确哪些现有数据能支持保守的整手费用重放；再设计固定的风格/基准匹配反证与可用独立窗口。若缺必要证据，说明缺口而非宣称可用。只有新的已登记机制才增加探索预算；不能重用本次claims或把成本情景当独立Alpha。",
            "Keep the policy frozen;do not beautify history by tuning200pool/40positions/calendar. Next bounded work inventories raw-price/adjustment/corporate-action and executable-share evidence,identifies a defensible lot/fee replay,then specifies fixed style/benchmark falsification and available independent windows. Report genuinely missing evidence instead of asserting usability. New mechanism work requires new reservations;never replay this claim or call cost scenarios independent Alpha.",
        ),
    ]
    for language in ("zh", "en"):
        zh = language == "zh"
        lines = [
            "# V11.11 稳定持仓线索深挖" if zh else "# V11.11 Frozen Allocation: Stress Report",
            "",
        ]
        for key, heading, cn, en in sections:
            lines += ["## " + heading, "", cn if zh else en, ""]
            if key == "finding":
                lines += [
                    "|Scenario|Policy|bps|2023|2024|Total|Profit CNY|Δ low-vol pp|MDD|Sharpe|Fees CNY|",
                    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
                for x in s["rows"]:
                    lines.append(
                        f"|{x['scenario']}|{x['policy']}|{x['roundtrip_bps']}|{x['return2023']:.2%}|{x['return2024']:.2%}|{x['net_return']:.2%}|{x['profit_cny']:,.2f}|{x['increment_pp']:+.2f}|{x['max_drawdown']:.2%}|{x['sharpe']:.3f}|{x['cost_cny']:,.2f}|"
                    )
                lines += [""]
        lines += [
            "Sources: docs/V11_11_DEEP.summary.json; scripts/audit_stability_challenge.py; immutable RESULT/INDEPENDENT_AUDIT/accounts/targets/native ledger.",
            "",
        ]
        with Path(f"docs/V11_11_DEEP.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as out:
            out.write("\n".join(lines))
    query = "SELECT a.* FROM (SELECT unnest(rows) AS a FROM read_json_auto('docs/V11_11_DEEP.summary.json')) WHERE a.policy='stable_lowrisk' ORDER BY a.scenario"
    with duckdb.connect() as con:
        cur = con.execute(query)
        columns = [c[0] for c in cur.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    source = {
        "id": "stability",
        "label": "Independently audited matched allocation stresses",
        "path": "docs/V11_11_DEEP.summary.json",
        "href": "https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.11-temporal-increments/docs/V11_11_DEEP.zh.md",
        "query": {
            "sql": query,
            "language": "sql",
            "engine": "DuckDB",
            "tables_used": ["docs/V11_11_DEEP.summary.json"],
            "description": "All five predeclared stable-allocation stress accounts; full controls remain in the source summary.",
            "metric_definitions": {
                "increment_pp": "100*(stable net total return-matched strict lowvol net total return),2023-2024,CNY3m continuous",
                "net_return": "final NAV/3000000-1",
            },
        },
    }
    title = "Frozen Allocation Stress | 稳定持仓压力测试"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, cn, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{cn}\n\n{en}"})
        if key == "finding":
            blocks.append({"id": "stress_chart", "type": "chart", "chartId": "stress"})
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
                    "id": "stress",
                    "type": "bar",
                    "dataset": "stresses",
                    "title": "2023–2024 Δ matched low-vol (pp)",
                    "sourceId": "stability",
                    "source": source,
                    "encodings": {
                        "x": {"field": "scenario", "type": "nominal"},
                        "y": {"field": "increment_pp", "type": "quantitative"},
                    },
                    "options": {"orientation": "horizontal"},
                    "height": 350,
                    "palette": {"kind": "sequential", "name": "blue"},
                }
            ],
        },
        "snapshot": {"version": 1, "status": "ready", "datasets": {"stresses": rows}},
        "sources": [source],
    }
    json.dumps(artifact, allow_nan=False)
    write_json(ROOT / "report-artifact.json", artifact)
    write_json(
        ROOT / "report-qa.json",
        {
            "audience": "technical",
            "surface": "mcp-app",
            "confidence": "SHARE_WITH_CAVEATS",
            "chart_contract": "all5 stresses; signed pp; zero baseline; rich matched-control metrics; 350px blue",
            "pixel_qa": "not performed; user requested notification only for usable Alpha or actionable blocker",
            "delivery": "archived non-certified historical observation; no usable Alpha claim",
        },
    )
    print(
        json.dumps(
            {
                "stress_survived": s["stress_survived"],
                "validated_alpha": False,
                "chart_rows": len(rows),
            }
        )
    )


if __name__ == "__main__":
    build()
