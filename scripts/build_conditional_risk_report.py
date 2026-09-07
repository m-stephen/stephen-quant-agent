"""Archive audited results without rerunning or selecting market experiments."""

import json
from collections import Counter
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/conditional-risk/epoch-001")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build():
    audit = read(ROOT / "INDEPENDENT_AUDIT.json")
    result = read(ROOT / "RESULT.json")
    summary = audit["summary"]
    if not audit["pass"] or result["validated_alpha"]:
        raise ValueError("audited exploratory evidence required")
    if summary["source_result_sha256"] != file_sha(ROOT / "RESULT.json"):
        raise ValueError("result changed")
    labels = {identity: f"R{i + 1}" for i, identity in enumerate(summary["checks"])}
    by_key = {r["account_key"]: r for r in summary["rows"]}
    chart_rows = []
    for row in summary["rows"]:
        record = result["records"][row["account_key"]]
        row.update(base=record["base"], rule=record["rule"])
        if row["policy"] != "model":
            continue
        identity, cost, base = row["identity"], row["roundtrip_bps"], row["base"]
        keys = [f"{identity}-{p}-{cost}" for p in ("fixed", "lag20", "shuffle")]
        keys += [f"{base}-{p}-{cost}" for p in ("risk_only", "unscaled", "original")]
        increments = {k: row["net_return"] - by_key[k]["net_return"] for k in keys}
        chart_rows.append(
            {
                **row,
                "label": labels[identity],
                "cost_label": f"{cost}bps",
                "minimum_control_increment": min(increments.values()),
                "control_increments": increments,
            }
        )
    summary["primary_comparisons"] = chart_rows
    summary["models_summary"] = {
        f"{kind}-{year}": {
            k: v
            for k, v in read(ROOT / f"models/{kind}-{year}.json").items()
            if k
            in (
                "training_signal_dates",
                "fit_cutoff",
                "maximum_label_end",
                "mean_return",
                "mean_second",
                "training_mean_exposure",
                "rotation",
            )
        }
        for kind in ("direct", "shuffle")
        for year in (2023, 2024)
    }
    summary["independent_audit_sha256"] = file_sha(ROOT / "INDEPENDENT_AUDIT.json")
    predictions = read(ROOT / "predictions-direct.json")
    summary["daily_prediction_exposure_counts"] = {
        str(year): {
            rule: dict(
                Counter(
                    str(row[rule])
                    for date, row in predictions.items()
                    if date.startswith(str(year))
                )
            )
            for rule in ("mean", "mean_second", "risk_only")
        }
        for year in (2023, 2024)
    }
    write_json(Path("docs/V11_18_RESULT.summary.json"), summary)
    winners = [k for k, v in summary["screen_survived"].items() if v]
    tests = read(ROOT / "TEST_VERIFICATION.json")
    coverage = "; ".join(f"{y}: {v:.2%}" for y, v in summary["coverage"].items())
    sections = [
        (
            "summary",
            "结论 / Conclusion",
            f"本轮4个条件风险配置身份中，{len(winners)}个通过完整探索筛选。已认证可用 Alpha 仍为0。"
            + (
                f"应原样冻结并深入证伪：{', '.join(winners)}。"
                if winners
                else "本轮机制留档，不追调符号、仓位阈值或期限。"
            ),
            f"{len(winners)} of 4 conditional-risk identities pass the complete exploratory screen. Certified usable Alpha remains zero. "
            + (
                f"Freeze unchanged for deeper falsification: {', '.join(winners)}."
                if winners
                else "Archive this mechanism without sign, exposure-threshold or horizon chasing."
            ),
        ),
        (
            "scope",
            "范围与基准 / Scope and comparators",
            "44个连续300万元账户，2023–2024共484交易日，2022训练及预热。仅在原冻结lowvol/stable_lowrisk选股目标上缩放仓位，不是新增选股因子。比较基准为同base、同成本的固定仓位、滞后20日、打乱标签、仅风险、未缩放以及旧撮合锚点，不是沪深300。2023/24已多次用于开发，不是独立样本；未读取2025/26。",
            "44 continuous CNY3m accounts over 484 sessions in 2023–2024, with 2022 training/warmup. Exposure scales original frozen lowvol/stable_lowrisk stock targets; it is not a new stock selector. Comparators are same-base, same-cost fixed, lag20, shuffled, risk-only, unscaled and original-execution anchors, not CSI300. Repeatedly reused 2023/24 are development evidence, not independent samples; 2025/26 were not accessed.",
        ),
        (
            "mechanism",
            "模型及可知时点 / Model and information clock",
            "共同有效股票的20日上涨广度、平均收益、平均波动率与相邻日收益离散度为4输入。下一年模型仅使用历史前缀，去掉最后5个交易日并要求全部标签已成熟；标准化和ridge λ=1均在训练集完成。预测未来5交易日收益均值与二阶矩R²（不是条件方差）。γ=10，仓位限制25%–100%，按25%档量化，每5日刷新，信号晚于拟合cutoff且早于执行。",
            "Four inputs are common eligible-stock 20-day breadth, mean return, mean volatility and adjacent-session dispersion. Next-year models use past prefixes with five-session embargo and mature labels; scaling and ridge lambda=1 are training-only. Outputs predict five-session mean return and second moment R², not conditional variance. Gamma=10, exposure 25%–100%, quarter-step quantization and five-session refresh. Fit cutoff precedes signal, which precedes execution.",
        ),
        (
            "labels",
            "训练标签与限制 / Training labels and limitations",
            "标签为当时200只低波股票等权篮子、下一开盘至5交易日后开盘的gross proxy。缺失买入价保留现金，不重分配权重；终点无价使用严格过去mark。非重叠、支持度至少95%，训练至少30行。它不含价格限制、容量及费用，并非实际可交易组合收益；只有最终44账户应用交易约束。共同状态覆盖："
            + coverage,
            "Labels are gross equal-weight 200-low-vol-stock basket proxies from next open to the open five sessions later. Missing entry prices remain cash without renormalization; missing endpoints use strictly past marks. Labels are non-overlapping with >=95% support and >=30 training rows. They omit limits, capacity and fees and are not executable portfolio returns; those constraints apply to the 44 final accounts. Common-state coverage: "
            + coverage,
        ),
        (
            "comparison",
            "全部主身份增量 / Every primary incremental result",
            "图展示4身份×2成本相对最强预声明对照的总收益差，单位为收益率小数（0.03=3个百分点）。负值表示至少一个简单对照更好。固定对照仅匹配训练平均仓位，不是事后精确匹配测试风险或换手；下表同时列现金、费用与成交额，禁止将降仓、降摩擦直接称为alpha。",
            "The chart shows all four identities at both costs: total return minus the strongest declared control, in fractional rates (0.03=3 percentage points). Negative values mean at least one simple control is better. Fixed controls match training mean exposure, not realized test risk or turnover. Cash, fees and traded notional remain visible; lower exposure or friction is not automatically alpha.",
        ),
        (
            "diagnosis",
            "输出行为诊断 / Prediction behavior diagnosis",
            "下列完整预测仓位分布说明模型是否实际产生时变决策。它是已审计预测文件的计数，不是新的阈值搜索，也不是5日执行后实际平均仓位。"
            + json.dumps(summary["daily_prediction_exposure_counts"], ensure_ascii=False),
            "The complete prediction-exposure counts show whether the model actually changes decisions. These count already audited predictions, not a new threshold search or realized exposure after five-session execution. "
            + json.dumps(summary["daily_prediction_exposure_counts"]),
        ),
        (
            "execution",
            "交易与门槛 / Execution and gates",
            "82bps口径为买卖各6佣金、卖出10税、买卖各30滑点；164bps逐项翻倍。现金收益0，无杠杆，目标单名上限2.5%。两成本都需两年正收益、Sharpe≥0.7、最大回撤≥−25%、相对每个对照总增量≥3个百分点、每年差≥−5个百分点，且每年状态覆盖≥95%及完整审计通过。除旧锚点full_target外均为target_changes。现有复权碎股模型不是整手、最低佣金及公司行为现金的实盘认证。",
            "82bps means 6 commission each side, 10 sell tax and 30 slippage each side; 164bps doubles each component. Cash earns zero, no leverage, desired name cap 2.5%. Both costs require positive returns in both years, Sharpe>=.7, MDD>=-.25, >=3pp total and >=-5pp annual increment against every control, >=95% annual state coverage and complete audit. All use target_changes except original full_target anchors. Adjusted fractional units do not certify live lots, minimum commission or corporate-action cash.",
        ),
        (
            "audit",
            "复核与试验账本 / Audit and trial ledger",
            f"完整测试{tests['passed']} passed、{tests['skipped']} skipped；Ruff通过。独立源SQL复核{summary['states']}个状态、{summary['proxy_components']:,}个标签组成、{summary['proxy_labels']}个标签；独立正规方程重算4模型、22目标集、44账户及72原生fit。历史Trial下界3556→3600，全部44尝试保留。单次结构打乱不是统计placebo p值。",
            f"Full suite: {tests['passed']} passed, {tests['skipped']} skipped; Ruff passes. Independent source SQL checks {summary['states']} states, {summary['proxy_components']:,} label components and {summary['proxy_labels']} labels; independent normal equations reconstruct four models, 22 target sets, 44 accounts and 72 native fits. Raw trial lower bound rises 3556 to 3600; all 44 attempts are retained. One structural shuffle is not a statistical placebo p-value.",
        ),
        (
            "next",
            "解释与下一步 / Interpretation and next steps",
            "当前仅回答条件仓位是否产生可继续验证的历史增量，不证明可用alpha。完整幸存者先冻结再做有限预登记延迟、容量、跨状态和伪造检验；失败则换真正不同机制，不降低门槛。最终仍需可识别全部历史尝试、多重检验、purged CPCV/PBO、经验偏度峰度DSR、placebo及独立前向证据；DSR 0.95、PBO 0.05、placebo 0.05门槛不变。不合并main、不交易。",
            "This asks whether conditional exposure supplies a historical increment worth deeper testing, not whether usable alpha is certified. Freeze full survivors before finite registered delay, capacity, regime and falsification challenges; otherwise change to a genuinely different mechanism, not lower gates. Certification still needs identifiable trial history, multiplicity, purged CPCV/PBO, empirical-moment DSR, placebo and independent forward evidence. DSR .95, PBO .05 and placebo .05 gates remain unchanged. No main merge or trading.",
        ),
    ]
    table = [
        "|Account|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Fees CNY|Traded CNY|Mean cash|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary["rows"]:
        table.append(
            f"|{r['account_key']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|{r['cost_cny']:,.2f}|{r['traded_cny']:,.2f}|{r['mean_cash_fraction']:.2%}|"
        )
    gate_table = ["|Identity|bps|Failed gates|Minimum control increment pp|", "|---|---:|---|---:|"]
    for r in chart_rows:
        failed = [
            k for k, v in summary["checks"][r["identity"]][str(r["roundtrip_bps"])].items() if not v
        ]
        gate_table.append(
            f"|{r['identity']}|{r['roundtrip_bps']}|{', '.join(failed) or 'none'}|{r['minimum_control_increment'] * 100:.4f}|"
        )
    for language in ("zh", "en"):
        lines = ["# V11.18 条件风险配置测试报告 / Conditional Risk Test Report", ""]
        for key, heading, zh, en in sections:
            lines += ["## " + heading, "", zh if language == "zh" else en, ""]
            if key == "scope":
                lines += [f"- {v}: `{k}`" for k, v in labels.items()] + [""]
            if key == "comparison":
                lines += gate_table + [""] + table + [""]
            if key == "labels":
                lines += ["```json", json.dumps(summary["models_summary"], indent=2), "```", ""]
        lines += [
            "## Evidence / 证据",
            "",
            "[Preregistration](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562202690)",
            "",
            "Source: V11_18_RESULT.summary.json; independent audit and immutable operation hashes. Native report schema validation is recorded separately; visible/pixel QA is deferred under the quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_18_RESULT.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write("\n".join(lines))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text()
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    source = {
        "id": "accounts",
        "label": "Independently audited conditional-risk accounts",
        "path": "docs/V11_18_RESULT.summary.json",
        "query": {
            "sql": query,
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": [(ROOT / "accounts/*.jsonl").as_posix()],
            "description": "Executed account aggregates; annual results and same-base control increments enriched by independent auditor and report builder.",
            "filters": ["all 44 registered accounts", "reused 2023-2024"],
            "metric_definitions": {
                "net_return": "finalNAV/3000000-1",
                "minimum_control_increment": "model total return minus maximum of six same-base same-cost controls, fractional rate",
            },
        },
    }
    title = "Conditional Risk Allocation | 条件风险配置"
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
        ROOT / "report-artifact.v2.json",
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
                        "title": "Net Return Increment by Identity and Cost",
                        "description": "2023–2024, fractional return; zero means no advantage over the strongest declared control",
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
                "datasets": {
                    "increments": [
                        {
                            **{k: v for k, v in row.items() if k != "control_increments"},
                            **{
                                f"increment_vs_{k}": v for k, v in row["control_increments"].items()
                            },
                        }
                        for row in chart_rows
                    ],
                    "accounts": summary["rows"],
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
            "chart_contract": "8 rows; all4 identities x2costs; zero baseline, cost legend, identity mapping; fractional rates",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(
        json.dumps({"reports": 2, "accounts": 44, "survivors": winners, "validated_alpha": False})
    )


if __name__ == "__main__":
    build()
