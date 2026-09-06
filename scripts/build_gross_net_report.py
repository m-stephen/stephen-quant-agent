"""Publish all audited diagnostic aggregates; no research, ranking, or refitting."""

import json
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/gross-net/epoch-001")


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def build():
    audit, result = read(ROOT / "INDEPENDENT_AUDIT.json"), read(ROOT / "RESULT.json")
    s = audit["summary"]
    if (
        not audit["pass"]
        or result["validated_alpha"]
        or s["source_result_sha256"] != file_sha(ROOT / "RESULT.json")
        or len(s["rows"]) != 36
    ):
        raise ValueError("complete independently audited diagnostic required")
    s["independent_audit_sha256"] = file_sha(ROOT / "INDEPENDENT_AUDIT.json")
    tests = read(ROOT / "TEST_VERIFICATION.json")
    primary = [
        r | {"label": f"{r['identity']} / {r['roundtrip_bps']}bps"}
        for r in s["rows"]
        if r["policy"] == "full"
    ]
    sections = [
        (
            "summary",
            "结论",
            "Technical summary",
            "已完成12个零费用反事实和24个原付费账户的完整核对。两个原主要身份仍为失败；已认证可用Alpha为0。此诊断解释毛收益与执行摩擦，不进行新的候选晋升。",
            "Twelve zero-fee counterfactuals and24 immutable paid accounts are fully reconciled. Both original primary identities remain failed; certified usable Alpha is zero. This diagnoses gross strength and implementation friction, not candidate promotion.",
        ),
        (
            "scope",
            "范围和比较口径",
            "Scope and comparator definitions",
            "2023–2024共484个交易日，一个连续300万元账户；2022预热。全部历史已多次用于开发，不是新OOS，2025/26未读取。参照为同基风险、打乱、回归、hash、同格低波、两原组合；不代表沪深300或市场超额。",
            "Each continuous CNY3m account spans484 sessions in2023–2024 with2022 warmup. History is reused development,not freshOOS;2025/26 are unread. Comparators are same-basis risk/shuffle/regression,hash,matched lowvol and two original portfolios,notCSI300 or market excess return.",
        ),
        (
            "methods",
            "方法与冻结条件",
            "Methods and frozen conditions",
            "12份目标原字节复制：成员、权重、时间戳与开盘执行语义不变。仅将佣金、税、滑点一起置零，实际重新生成现金路径；不得在旧NAV上加回费用。原24个82/164bps账户只读。10个政策target_changes，两原锚点full_target，容量仍为前60观察日ADV的5%。",
            "Twelve target files are copied byte-for-byte with unchanged members,weights,clocks and open-execution semantics. Only commission,tax and slippage jointly become zero;cash paths are rerun rather than adding fees back to oldNAV. The24 paid82/164bps accounts remain read-only. Ten policies use target_changes,two anchors full_target;capacity remains5% of prior60-observation ADV.",
        ),
        (
            "results",
            "全部账户结果",
            "All account results",
            "图中展示两个完整排序身份在0/82/164bps下的累计收益。表内完整列出36条曲线，不选择最好曲线作为新发现。零费用是不可交易的反事实条件。",
            "The chart shows both full ranking identities at0/82/164bps. The table retains all36 paths rather than selecting the best as a discovery. Zero fees are an untradeable counterfactual.",
        ),
        (
            "drag",
            "费用路径与简单加回误差",
            "Cost-path drag and fee-addback error",
            "路径拖累=零费用收益−付费收益；加回误差=路径拖累−直接费用/300万元。单位均为收益率或百分点，包含资金缩放、复利及成交变化，不是费用的干净因果估计，也不代表可节省金额。",
            "Path drag=zero-fee minus paid return. Addback error=path drag minus direct fees/CNY3m. These rate/percentage-point differences include cash scaling,compounding and changed fills;they are neither causal fee estimates nor achievable savings.",
        ),
        (
            "increments",
            "相对全部对照的增量",
            "Increment versus every declared control",
            "以下42项完整比较两身份×七对照×三成本。总增量和每年增量均保留。零费用增量−同成本净增量也是描述性差值，不是Alpha统计量。",
            "All42 comparisons cover two identities,seven controls and three costs. Total and both annual increments remain visible. Gross increment minus same-cost net increment is descriptive,not an Alpha statistic.",
        ),
        (
            "validation",
            "验证与尝试账本",
            "Validation and trial ledger",
            f"全套{tests['passed']}通过、{tests['skipped']}跳过，Ruff通过。12个新原生重放Trial，0个新fit，但继承绑定16模型/32fit，不是假装无训练。Trial下界3648→3660，保留旧失败。独立源开盘股数、收盘标记、ADV容量及36账户核对通过。",
            f"Full suite:{tests['passed']} passed,{tests['skipped']} skipped;Ruff passes. Twelve new native replayTrials,zero new fits,explicitly inherit16models/32fits. Trial lower bound3648→3660 retains prior failures. Independent source-open units,closing marks,ADV capacity and36 saved accounts reconcile.",
        ),
        (
            "limits",
            "局限与后续决策",
            "Limitations and next decision",
            "复权碎股不是原始整手股数、最低佣金、分红现金或实盘容量认证。零成本结果不能挽救原门槛失败者。DSR/PBO/placebo未运行且为null，绝不等于Court PASS。若毛增量仍弱，改信息机制；若毛强净弱，单独登记训练期换手约束目标；跨年不稳不能删除年份。每次新尝试仍先登记，门槛不降，不自动合并main或交易。",
            "Adjusted fractional units are not raw lots,minimum-commission,dividend-cash or live-capacity certification. Zero fees cannot rescue failed registered gates. DSR/PBO/placebo are NOT_RUN/null,notCourtPASS. Weak gross increments call for a different mechanism;gross strength lost after costs calls for a separately registered train-prefix turnover objective. Unstable years cannot be discarded. Register every new attempt,keep thresholds,no automatic main merge or trading.",
        ),
    ]
    tables = {}
    tables["results"] = [
        "|Account|bps|2023|2024|Total|Sharpe|MDD|Profit CNY|Fees CNY|Traded CNY|Mean cash|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["rows"]:
        tables["results"].append(
            f"|{r['account_key']}|{r['roundtrip_bps']}|{r['return2023']:.4%}|{r['return2024']:.4%}|{r['net_return']:.4%}|{r['sharpe']:.4f}|{r['max_drawdown']:.4%}|{r['profit_cny']:,.2f}|{r['cost_cny']:,.2f}|{r['traded_cny']:,.2f}|{r['mean_cash_fraction']:.2%}|"
        )
    tables["drag"] = [
        "|Target|bps|Path drag pp|Direct fees / capital pp|Addback error pp|2023 drag pp|2024 drag pp|",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in s["attribution"]["path_drag"]:
        tables["drag"].append(
            f"|{r['target_key']}|{r['roundtrip_bps']}|{100 * r['cost_path_drag']:.4f}|{100 * r['direct_cost_fraction_initial_capital']:.4f}|{100 * r['addback_error']:.4f}|{100 * r['drag2023']:.4f}|{100 * r['drag2024']:.4f}|"
        )
    tables["increments"] = [
        "|Identity|Control|bps|Increment pp|2023 pp|2024 pp|Gross minus paid increment pp|",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in s["attribution"]["increments"]:
        tables["increments"].append(
            f"|{r['identity']}|{r['control']}|{r['roundtrip_bps']}|{100 * r['increment']:.4f}|{100 * r['increment2023']:.4f}|{100 * r['increment2024']:.4f}|{100 * r['increment_path_drag']:.4f}|"
        )
    for lang in ("zh", "en"):
        lines = [
            "# " + ("V11.20 毛净收益诊断" if lang == "zh" else "V11.20 Gross-to-Net Diagnosis"),
            "",
        ]
        for key, zh_title, en_title, zh, en in sections:
            lines += [
                "## " + (zh_title if lang == "zh" else en_title),
                "",
                zh if lang == "zh" else en,
                "",
            ]
            lines += tables.get(key, []) + [""]
        lines += [
            f"[Preregistration / 预登记](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-{result['spec']['preregistration_comment']})",
            "",
            "Evidence: V11_20_RESULT.summary.json; runtime " + result["spec"]["runtime_commit"],
            "",
            "Visible/pixel QA: DEFERRED_USER_QUIET_INSTRUCTION.",
            "",
        ]
        with Path(f"docs/V11_20_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    write_json(Path("docs/V11_20_RESULT.summary.json"), s)
    query = Path("scripts/lead_challenge_audit.sql").read_text(encoding="utf-8")
    source = {
        "id": "audited",
        "label": "36 independently audited frozen-policy cost paths",
        "path": "docs/V11_20_RESULT.summary.json",
        "query": {
            "sql": query.replace("__ACCOUNT_GLOB__", (ROOT / "accounts/*.jsonl").as_posix()),
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": [
                (ROOT / "accounts/*.jsonl").as_posix(),
                "../v11.19-pairwise-ranking/artifacts/pairwise-ranking/epoch-002/accounts/*.jsonl",
            ],
            "description": "Same saved-account aggregate SQL executed separately on12 new and24 inherited paths; independent audit adds annual rates and full-minus-control differences.",
            "filters": ["all36 accounts", "2023-2024 reused development"],
            "metric_definitions": {
                "net_return": "finalNAV/3000000-1",
                "increment": "candidate minus same-cost control fractional return",
            },
        },
    }
    blocks = [
        {"id": "title", "type": "markdown", "body": "# Gross-to-Net Diagnosis | 毛净收益诊断"}
    ]
    for key, zh_title, en_title, zh, en in sections:
        blocks.append(
            {"id": key, "type": "markdown", "body": f"## {zh_title} / {en_title}\n\n{zh}\n\n{en}"}
        )
        if key == "results":
            blocks += [
                {"id": "primaryplot", "type": "chart", "chartId": "primary"},
                {"id": "allaccounts", "type": "table", "tableId": "accounts"},
            ]
        elif key == "increments":
            blocks.append({"id": "allincrements", "type": "table", "tableId": "increments"})
        elif key == "drag":
            blocks.append({"id": "alldrags", "type": "table", "tableId": "drags"})
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "Gross-to-Net Diagnosis | 毛净收益诊断",
            "blocks": blocks,
            "sources": [source],
            "charts": [
                {
                    "id": "primary",
                    "type": "bar",
                    "dataset": "primary",
                    "title": "Frozen Full-Policy Return by Cost",
                    "description": "2023–2024; fractional total return,0.10=10%;zero fees are counterfactual",
                    "sourceId": "audited",
                    "source": source,
                    "encodings": {
                        "x": {"field": "label", "type": "nominal"},
                        "y": {"field": "net_return", "type": "quantitative"},
                    },
                    "height": 420,
                    "palette": {"kind": "categorical", "name": "default"},
                }
            ],
            "tables": [
                {
                    "id": name,
                    "dataset": name,
                    "title": title,
                    "sourceId": "audited",
                    "source": source,
                    "columns": [{"field": k, "label": k} for k in fields],
                }
                for name, title, fields in [
                    (
                        "drags",
                        "All24 cost-path drags",
                        (
                            "target_key",
                            "roundtrip_bps",
                            "cost_path_drag",
                            "direct_cost_fraction_initial_capital",
                            "addback_error",
                            "drag2023",
                            "drag2024",
                        ),
                    ),
                    (
                        "accounts",
                        "All36 audited accounts",
                        (
                            "account_key",
                            "return2023",
                            "return2024",
                            "net_return",
                            "sharpe",
                            "max_drawdown",
                            "cost_cny",
                            "traded_cny",
                            "mean_cash_fraction",
                        ),
                    ),
                    (
                        "increments",
                        "All42 declared increments",
                        (
                            "identity",
                            "control",
                            "roundtrip_bps",
                            "increment",
                            "increment2023",
                            "increment2024",
                            "increment_path_drag",
                        ),
                    ),
                ]
            ],
        },
        "snapshot": {
            "version": 1,
            "status": "ready",
            "datasets": {
                "primary": primary,
                "accounts": s["rows"],
                "increments": s["attribution"]["increments"],
                "drags": s["attribution"]["path_drag"],
            },
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
            "structure_mapping": "summary,scope,methods,findings,attribution,validation,limitations,next; methods precede findings for cost-counterfactual interpretation",
            "report_spine": "Do frozen failed policies lack gross incremental strength or lose it to costs?",
            "chart_contract": "6 fixed primary-cost bars;zero baseline;fractional return;no redundant legend;all36 and42 exact lookup rows",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "no_parallel_html": True,
            "confidence": "SHARE_WITH_CAVEATS",
        },
    )
    print(json.dumps({"reports": 2, "accounts": 36, "comparisons": 42, "validated_alpha": False}))


if __name__ == "__main__":
    build()
