"""Build bilingual response evidence,without presenting gross labels as traded NAV."""

import json
from pathlib import Path

from stephen_quant.discovery.risk_stratified import MECHANISMS
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/signal-timing/epoch-001")


def build():
    summary = json.loads(Path("docs/V11_15_RESULT.summary.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
    assert audit["pass"]
    rows = summary["rows"]
    lookup = {(r["group"], r["policy"], r["label"], r["year"]): r for r in rows}
    chart_rows = []
    for r in rows:
        if r["policy"] in MECHANISMS:
            controls = [
                lookup[r["group"], p, r["label"], r["year"]]["mean_gross"]
                for p in ("hash", "price_reversal", "cell_equal_weight")
            ]
            chart_rows.append(
                {
                    **r,
                    "period": r["label"] + " / " + r["year"],
                    "minimum_control_increment": r["mean_gross"] - max(controls),
                }
            )
    strong = [k for k, passed in summary["strong_responses"].items() if passed]
    sections = [
        (
            "decision",
            "结论 / Decision",
            (
                f"本轮完成90个固定响应诊断，强响应线索{len(strong)}个，可用Alpha仍未认证。"
                "这是时点诊断，不是新账户回测；不可将毛收益、重叠事件或条件均值写成净收益率、年化Sharpe或资金利润。"
            ),
            (
                f"All90 fixed response diagnostics completed;{len(strong)} strong responses merit a separately frozen execution study."
                " No usable Alpha is certified. Gross overlapping event labels are not net account returns,annualized Sharpe or capital profits."
            ),
        ),
        (
            "scope",
            "数据范围与分母 / Scope and denominators",
            (
                f"共同成熟信号日期{summary['signal_dates']}个，从{summary['first_signal']}到{summary['last_signal']}；"
                "2022预热，2023/2024重复暴露开发数据，不读取2025/2026。每个年度按信号年汇总，不是该年的自融资净值收益。"
                "相同日期固定分母，每日每格前10名各2.5%，不沿用buffer；格内等权每格25%。"
            ),
            (
                f"{summary['signal_dates']} common mature signal dates,{summary['first_signal']} through {summary['last_signal']}."
                "2022warmup,reused2023/24,no2025/26. Years refer to signal dates,not accounting years."
                "Daily top10 per cell,2.5% each,no retention buffer;cell-equal-weight assigns25% per nonempty cell."
            ),
        ),
        (
            "timing",
            "收益发生时点 / Response timing",
            (
                "before_entry是信号日收盘至次日开盘，入场前已发生；same_day是次日开盘至收盘，A股新买入不可同日卖出。"
                "只有open_1/5/20在时间上兼容T+1，但尚未经真实执行验证。五个区间不是可相加的互斥收益分解。"
            ),
            (
                "before_entry occurs before next-open entry;same_day is next-open to same-close and is not a same-day roundtrip for newly bought A-shares."
                "Only open_1/5/20 are T+1-compatible in timing,not execution-certified. The five intervals overlap and must not be added."
            ),
        ),
        (
            "missing",
            "缺失、涨跌停与压力情景 / Missingness and stress",
            (
                "未来端点缺失不删除股票、不重分配权重。固定分母贡献缺失记0，并展示可见价格权重；完整价格条件均值可能有选择偏差。"
                "压力情景：买不进记现金0，已买但缺失或不可卖退出记损失100%。这不是实际清算模型，不能拿来做净值。"
            ),
            (
                "Missing future endpoints never alter selection or weights. Missing contribution is0 with missing weight exposed;"
                "complete-price conditional means may be selection-biased. Stress assignscash0 to unavailable entry and loss100% to unavailable/unsellable exit after entry."
                "It is a diagnostic stress convention,not actual liquidation or NAV."
            ),
        ),
        (
            "gate",
            "后续账户实验条件 / Gate for a separate execution study",
            (
                "两年均需毛收益>1.64%，分别超出同档hash/反转/等权至少0.30个百分点，价格覆盖>=99%，入场权重>=98%，压力均值>0。"
                "只是足够强响应的筛选，不是低换手策略存在Alpha的必要条件；本轮没有扣常数费用伪装账户、没有调门槛。"
            ),
            (
                "Both years require gross mean>1.64%,at least0.30pp above EACH same-stratum hash/reversal/EW,price coverage>=99%,entry>=98%,stress>0."
                "This is a strong-response screen,not a necessary condition for every low-turnover alpha. No flat-cost pseudo-account or threshold adjustment."
            ),
        ),
        (
            "methods",
            "方法、验证与统计边界 / Methods,verification and limits",
            (
                f"独立SQL逐端点比对冻结原日K，重建风险格、全部排名/权重和{audit['date_rows']}条日期统计，最大重算差{audit['maximum_aggregate_difference']:.3g}。"
                "全部90个原生无拟合Trial已完成，累计下界3456。无独立OOS/Court/DSR/PBO/placebo认证。源时间字段仍非实时首见证明，复权价格仍非分红现金或整手成交证明。"
            ),
            (
                f"Independent SQL checks every endpoint against frozen daily data,rebuilds all risk cells/ranks/weights and{audit['date_rows']} date readouts;maximum difference{audit['maximum_aggregate_difference']:.3g}."
                "90 native no-fit Trials complete;raw historical lower bound3456. No independent OOS/Court/DSR/PBO/placebo certification."
                "Vendor timing is not live-first-seen proof;adjusted prices do not certify dividend cash,raw lots or opening liquidity."
            ),
        ),
        (
            "next",
            "后续工作 / Next work",
            (
                "只将强响应另行冻结为真实连续300万元账户实验，测试标准及双倍成本、延迟、容量、市场状态和伪造检验。"
                "没有强响应则封存当前三机制的时点/期限诊断，不翻转方向或无限换窗口；下一轮必须说明新的经济机制和有限预算。原观察卡不变。"
            ),
            (
                "Freeze any strong response separately before continuous CNY3m execution,standard/double costs,delay,capacity,regimes and falsification."
                "Otherwise close this diagnostic without sign flips or endless horizon sweeps;the next epoch needs a distinct economic mechanism and finite budget. Preserve the original observation card."
            ),
        ),
    ]
    table = [
        "|Group|Policy|Label|Signal year|Dates|Gross mean|Valid weight|Entry weight|Stress mean|",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        stress = "N/A" if r["mean_stress"] is None else f"{r['mean_stress']:.4%}"
        table.append(
            f"|{r['group']}|{r['policy']}|{r['label']}|{r['year']}|{r['dates']}|"
            f"{r['mean_gross']:.4%}|{r['valid_weight']:.4%}|{r['entry_weight']:.4%}|{stress}|"
        )
    for lang, title in (
        ("zh", "V11.15 信号时点与衰减诊断报告"),
        ("en", "V11.15 Signal Timing and Decay Report"),
    ):
        lines = ["# " + title, ""]
        for _, heading, zh, en in sections:
            lines.extend(["## " + heading, "", zh if lang == "zh" else en, ""])
        lines.extend(
            [
                "## 完整结果 / Complete results",
                "",
                *table,
                "",
                "Source: docs/V11_15_RESULT.summary.json; scripts/audit_signal_timing.py.",
                "Trading rule: https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml",
            ]
        )
        with Path(f"docs/V11_15_RESULT.{lang}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write("\n".join(lines))
    source = {
        "id": "responses",
        "label": "Independent endpoint-response aggregation",
        "path": "docs/V11_15_RESULT.summary.json",
        "query": {
            "sql": audit["query"],
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["artifacts/signal-timing/epoch-001/endpoints.csv.gz"],
            "description": "Original endpoint/weight SQL;minimum control increment computed from same group,label,year means.",
            "filters": [
                "reused2023/24",
                "common20-session mature signals",
                "90fixed diagnostic identities",
            ],
            "metric_definitions": {
                "mean_gross": "mean across signal dates of sum of fixed weights times endpoint price returns;missing contribution0;fractional,not NAV",
                "minimum_control_increment": "mean_gross minus maximum same-year,label,group gross mean across hash,reversal,cell-EW",
            },
        },
    }
    title = "Signal Timing | 信号时点与衰减"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
        if key == "timing":
            blocks.extend(
                {"id": "chart-" + g, "type": "chart", "chartId": g}
                for g in ("low", "middle", "high")
            )
    charts = [
        {
            "id": g,
            "type": "bar",
            "dataset": g,
            "title": f"{g} risk: gross response increment by mechanism",
            "description": "Five discrete overlapping intervals × two signal years;fractional return gap to strongest declared control;not net alpha",
            "sourceId": "responses",
            "source": source,
            "encodings": {
                "x": {"field": "period", "type": "nominal"},
                "y": {"field": "minimum_control_increment", "type": "quantitative"},
                "color": {"field": "policy", "type": "nominal"},
            },
            "height": 420,
            "palette": {"kind": "categorical", "name": "default"},
        }
        for g in ("low", "middle", "high")
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
                "charts": charts,
            },
            "snapshot": {
                "version": 1,
                "status": "ready",
                "datasets": {
                    "all_responses": rows,
                    **{
                        g: [r for r in chart_rows if r["group"] == g]
                        for g in ("low", "middle", "high")
                    },
                },
            },
            "sources": [source],
        },
    )
    write_json(
        ROOT / "report-qa.json",
        {
            "surface": "codex_desktop:mcp-app",
            "mode": "unknown",
            "chart_map": "three stratum grouped bars;each30rows,5intervalsx2yearsx3mechanisms;zero baseline,visible mechanism legend",
            "family_rationale": "same diagnostic comparison repeated across disjoint risk strata",
            "raw_private_rows_exposed": 0,
            "pixel_qa": "DEFERRED_USER_QUIET_UNTIL_USABLE",
            "no_parallel_html": True,
        },
    )
    print(json.dumps({"reports": 2, "strong_responses": strong, "validated_alpha": False}))


if __name__ == "__main__":
    build()
