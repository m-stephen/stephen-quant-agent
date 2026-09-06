"""Read audited immutable evidence; no candidate selection, refit or market query."""

import json
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/pairwise-ranking/epoch-002")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build():
    audit, result = read(ROOT / "INDEPENDENT_AUDIT.json"), read(ROOT / "RESULT.json")
    summary = audit["summary"]
    if (
        not audit["pass"]
        or result["validated_alpha"]
        or summary["source_result_sha256"] != file_sha(ROOT / "RESULT.json")
    ):
        raise ValueError("audited immutable result required")
    rows = summary["rows"]
    bykey = {r["account_key"]: r for r in rows}
    comparisons = []
    for row in rows:
        if row["policy"] != "full":
            continue
        b, c = row["identity"], row["roundtrip_bps"]
        names = [f"{b}-{k}-{c}" for k in ("risk", "shuffle", "regression")] + [
            f"control-{k}-{c}" for k in ("hash", "lowvol", "original_lowvol", "original_stable")
        ]
        increments = {
            "increment_vs_" + k: row["net_return"] - bykey[k]["net_return"] for k in names
        }
        comparisons.append(
            {
                **row,
                **increments,
                "label": f"{b} / {c}bps",
                "minimum_control_increment": min(increments.values()),
                "failed_gates": ", ".join(
                    k for k, v in summary["checks"][b][str(c)].items() if not v
                )
                or "none",
            }
        )
    summary["primary_comparisons"] = comparisons
    summary["independent_audit_sha256"] = file_sha(ROOT / "INDEPENDENT_AUDIT.json")
    summary["models_summary"] = {
        p.stem: {
            k: v
            for k, v in read(p).items()
            if k
            in (
                "year",
                "basis",
                "kind",
                "fit_cutoff",
                "maximum_label_end",
                "training_signal_dates",
                "training_pairs",
                "parameter_count",
                "weights",
            )
        }
        for p in sorted((ROOT / "models").glob("*.json"))
    }
    diagnostics = read(ROOT / "selection_diagnostics.json")
    summary["selection_summary"] = {
        k: {
            y: {
                "decisions": len(ds),
                "coverage": sum(d["selected"] for d in ds) / (40 * len(ds)),
                "minimum_eligible": min(d["eligible"] for d in ds),
                "new_members": sum(d["new_members"] for d in ds),
            }
            for y in ("2023", "2024")
            if (ds := [d for d in values if d["date"].startswith(y)])
        }
        for k, values in diagnostics.items()
    }
    write_json(Path("docs/V11_19_RESULT.summary.json"), summary)
    winners = [k for k, v in summary["screen_survived"].items() if v]
    tests = read(ROOT / "TEST_VERIFICATION.json")
    sections = [
        (
            "summary",
            "结论 / Technical summary",
            f"两个主要身份中{len(winners)}个通过完整探索筛选，已认证可用Alpha为0。"
            + (
                "需原样冻结再深入证伪：" + ", ".join(winners)
                if winners
                else "本轮负结果留档，不追调参数或修改验收线。"
            ),
            f"{len(winners)} of two primary identities survive the full exploratory screen; certified usable Alpha remains zero. "
            + (
                "Freeze unchanged for deeper falsification: " + ", ".join(winners)
                if winners
                else "Archive the negative result without parameter or gate chasing."
            ),
        ),
        (
            "scope",
            "重复开发史与七种对照 / Reused history and seven comparators",
            "24个连续300万元账户，2023–2024共484交易日；2022训练/预热。每个完整排序模型与同基风险排序、打乱排序、收益差回归及固定hash、同格低波、原低波、原稳定组合比较，不是沪深300。2023/24已多次开发使用，不是独立OOS；2025/26未读取。",
            "24 continuous CNY3m accounts span484 sessions in2023–2024;2022 provides training/warmup. Each full ranking model is compared with same-basis risk,shuffled and regression models plus hash,matched-cell lowvol and two original portfolios, notCSI300. Reused development history is not independentOOS;2025/26 were not accessed.",
        ),
        (
            "comparison",
            "全部主检验增量 / All primary increments",
            "图中四条柱表示两个身份×两成本，总收益减去七个预声明对照中的最大总收益；0.03代表3个百分点，负值表示至少一个对照更好。完整24账户收益、费用、换手及现金一并列出，不能只挑最好的曲线。",
            "Four bars show two identities at both costs: total return minus the strongest of seven declared controls.0.03 denotes3 percentage points;negative values mean at least one control is better. All24 accounts retain return,cost,turnover and cash evidence;no best-curve cherry-picking.",
        ),
        (
            "model",
            "排序目标与拟合边界 / Ranking objective and fit boundary",
            "六输入为当前波动、收益、ADV和20日资金、竞价、筹码路径。先按波动5格、格内ADV4格，再取当前同格平均并列秩。完整线性6维/二次27维；风险对照3/9维。成对分类与收益差回归使用日期等权损失，L2=.01固定，不搜索符号/期限/正则。所有模型先拟合成熟年度前缀，再通过原生fit检查预测。",
            "Six inputs combine current risk/liquidity with20-session flow,auction and chip paths. Five volatility bins each split into four ADV bins; ranks use current peers only. Full linear/quadratic models have6/27 parameters,risk controls3/9. Date-balanced pair classification versus relative-return regression uses fixedL2=.01. Annual mature prefixes and native fit checks precede prediction;no direction,horizon or regularization search.",
        ),
        (
            "labels",
            "毛收益代理不等于可交易收益 / Gross proxy versus executable returns",
            "同格固定hash前64只先配对后读标签；下一开盘到第21后续交易日开盘，缺入场留拒绝，缺终点保留过去标记。该标签不计价格限制、成交和成本。2023用2022，2024用2022–23，末尾5日embargo，至少30信号日。20日标签每5日采样有重叠，股票对数不是独立时间样本数；一个日期/格内打乱不是placebo p值。",
            "Within each cell,pairs are fixed from the first64 hashed names before outcomes. Labels cover next open to the21st subsequent session open;unsupported entry is recorded and absent endpoints retain past marks. These proxies omit executable constraints/costs.2023 fits2022;2024 fits2022–23 withfive-session embargo and>=30 signal dates.20-session labels sampled everyfive sessions overlap;pair counts are not independent time samples. One within-date/cell shuffle is not a placebo p-value.",
        ),
        (
            "execution",
            "成本、容量和风险解释 / Costs,capacity and risk interpretation",
            "每格2只、前三名缓冲，四个20日分仓合成一个连续净额账户；缺额现金不重分配，次日开盘。新政策target_changes，两原锚点full_target按原字节重放。82bps为双边各6佣金/30滑点加卖税10；164bps逐项翻倍，容量为前60观察日ADV的5%。风险格不是精确beta/行业/换手匹配；复权碎股不是整手、最低佣金或公司行为现金的实盘认证。",
            "Two names per cell,top-three retention and four20-session cohorts form one continuous netted account. Shortfalls remain cash;execution is next open. New policies use target_changes;both byte-frozen anchors use full_target.82bps=6commission+30slippage per side plus10sell tax;164bps doubles components. Capacity is5% of prior60-observation ADV. Cells do not exactly match beta,industry or turnover;adjusted fractional shares are not live lots,minimum-commission or corporate-action-cash certification.",
        ),
        (
            "audit",
            "独立复算与全部尝试 / Independent reconstruction and all attempts",
            f"全套{tests['passed']}通过、{tests['skipped']}跳过，Ruff通过。独立源复核{summary['source_feature_rows']:,}条可用特征、{summary['rank_dates']}个rank日期、{summary['training_pairs']:,}对训练证据；16模型严格凸驻点、12目标集、24账户和32原生fit均通过。首轮在数值求解处中止，0个账户但保留24次；修正仅处理浮点终止判据、不改1e−9梯度或经济门槛。另登记24次，因此Trial下界3600→3624→3648，包含所有失败、对照和成本。",
            f"Full suite:{tests['passed']} passed,{tests['skipped']} skipped;Ruff passes. Independent source checks cover{summary['source_feature_rows']:,} usable feature rows,{summary['rank_dates']} rank dates and{summary['training_pairs']:,} pair evidence rows;16 strictly convex model solutions,12target sets,24accounts and32native fits pass. The first numerical abort produced no accounts but retained24Trials. A terminal-roundoff fix preserves1e-9 stationarity and all economic gates;24corrective trials yield debt3600→3624→3648,including failures,controls and costs.",
        ),
        (
            "limitations",
            "探索筛选不是Alpha Court / Exploratory screening is not certification",
            "两成本均需两年正收益、SR≥.7、MDD≥−25%、相对每个对照总增量≥3pp、年度差≥−5pp、年度选中配额≥95%及全审计通过。DSR/PBO/placebo本轮未运行，保持null；不能将筛选通过写成Court PASS。反复使用的开发史无法靠更漂亮回测变成独立证据。",
            "Both costs require annual positivity,SR>=.7,MDD>=-.25,>=3pp total and>=-5pp annual increment against every control,>=95% annual selected quota and full audit. DSR/PBO/placebo are NOT_RUN/null,notPASS. Repeatedly used development history cannot become independent evidence through better-looking backtests.",
        ),
        (
            "next",
            "下一步与仍待回答的问题 / Next steps and open questions",
            "完整幸存者先冻结后进行有限预登记的延迟、跨状态、成本容量和伪造挑战；失败则归档换真正不同的机制，不能改门槛追通过。待回答：排序能力是否跨年稳定，收益是否只是风险暴露，实际成交摩擦是否吞噬毛收益。认证仍需全历史多重尝试、purged CPCV/PBO、经验偏度峰度DSR、placebo和独立前向证据；门槛不降。不自动合并main或交易。",
            "Freeze full survivors before finite registered delay,regime,cost/capacity and falsification challenges;otherwise archive and design a genuinely different mechanism. Open questions:year-to-year ranking stability,risk-only explanation and gross-to-net friction. Certification still requires full trial multiplicity,purgedCPCV/PBO,empirical-momentDSR,placebo and independent forward evidence without lowered thresholds. No automatic main merge or trading.",
        ),
    ]
    table = [
        "|Account|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Fees CNY|Traded CNY|Mean cash|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        table.append(
            f"|{r['account_key']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|{r['cost_cny']:,.2f}|{r['traded_cny']:,.2f}|{r['mean_cash_fraction']:.2%}|"
        )
    gates = ["|Identity|bps|Failed gates|Minimum increment pp|", "|---|---:|---|---:|"] + [
        f"|{r['identity']}|{r['roundtrip_bps']}|{r['failed_gates']}|{r['minimum_control_increment'] * 100:.4f}|"
        for r in comparisons
    ]
    for language in ("zh", "en"):
        lines = ["# Pairwise Ranking Results / 成对排序测试结果", ""]
        for key, title, zh, en in sections:
            lines += ["## " + title, "", zh if language == "zh" else en, ""]
            if key == "comparison":
                lines += gates + [""] + table + [""]
        lines += [
            "[Preregistration / 预登记](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562552983)",
            "",
            "Evidence: V11_19_RESULT.summary.json and immutable operation hashes. Native schema QA recorded separately; visible/pixel QA deferred under the quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_19_RESULT.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as f:
            f.write("\n".join(lines))
    query = (
        Path("scripts/lead_challenge_audit.sql")
        .read_text()
        .replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix())
    )
    source = {
        "id": "accounts",
        "label": "Independently audited pairwise-ranking accounts",
        "path": "docs/V11_19_RESULT.summary.json",
        "query": {
            "sql": query,
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": [(ROOT / "accounts/*.jsonl").as_posix()],
            "description": "Executed saved-account aggregates;annual returns and declared control differences are enriched by independent audit and this builder.",
            "filters": ["all24registered accounts", "reused2023-2024"],
            "metric_definitions": {
                "net_return": "finalNAV/3000000-1",
                "minimum_control_increment": "full model return minus maximum of seven same-cost controls;fractional rate",
            },
        },
    }
    title = "Pairwise Ranking Results | 成对排序结果"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in sections:
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
        if key == "comparison":
            blocks += [
                {"id": "plot", "type": "chart", "chartId": "increments"},
                {"id": "allaccounts", "type": "table", "tableId": "accounts"},
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
                    "id": "increments",
                    "type": "bar",
                    "dataset": "increments",
                    "title": "Net Return Increment by Identity and Cost",
                    "description": "2023–2024;fractional return relative to strongest declared control;0.03=3pp",
                    "sourceId": "accounts",
                    "source": source,
                    "encodings": {
                        "x": {"field": "label", "type": "nominal"},
                        "y": {"field": "minimum_control_increment", "type": "quantitative"},
                    },
                    "height": 420,
                    "palette": {"kind": "categorical", "name": "default"},
                }
            ],
            "tables": [
                {
                    "id": "accounts",
                    "dataset": "accounts",
                    "title": "All24 continuous accounts",
                    "sourceId": "accounts",
                    "source": source,
                    "defaultSort": {"field": "account_key", "direction": "asc"},
                    "columns": [
                        {"field": k, "label": label}
                        for k, label in (
                            ("account_key", "Account"),
                            ("net_return", "Net return"),
                            ("return2023", "2023"),
                            ("return2024", "2024"),
                            ("sharpe", "Sharpe"),
                            ("cost_cny", "Fees CNY"),
                            ("mean_cash_fraction", "Mean cash"),
                        )
                    ],
                }
            ],
        },
        "snapshot": {
            "version": 1,
            "status": "ready",
            "datasets": {"increments": comparisons, "accounts": rows},
        },
        "sources": [source],
    }
    write_json(ROOT / "report-artifact.json", artifact)
    write_json(
        ROOT / "report-qa.json",
        {
            "surface": "codex_desktop:mcp-app",
            "mode": "unknown",
            "audience": "technical",
            "structure_mapping": "Summary,scope,findings,model,labels,execution,audit,limitations,next/open questions;scope moved ahead of findings for baseline clarity;methods split for model-heavy report",
            "chart_contract": "4fixedprimary-cost categories;bar,zero baseline,single blue root/no redundant legend;fractional deltas;complete24account table for exact lookup",
            "report_spine": "Does date-balanced relative ranking provide a robust increment over all controls?",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(
        json.dumps(
            {
                "reports": 2,
                "accounts": len(rows),
                "screen_survivors": winners,
                "validated_alpha": False,
            }
        )
    )


if __name__ == "__main__":
    build()
