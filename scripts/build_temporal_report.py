"""Publish all audited temporal accounts, not only the favorable comparisons."""

import json
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/temporal-increments/epoch-001")
NAMES = {
    "flow_consistency": "资金流持续性 / Flow consistency",
    "auction_tail_balance": "竞价尾部 / Auction tail",
    "chip_path_efficiency": "筹码路径 / Chip path",
    "stable_lowrisk": "稳定低风险 / Stable low-risk",
    "lowvol": "严格低波动 / Strict low-vol",
}


def build():
    s = json.loads(Path("docs/V11_11_RESULT.summary.json").read_text(encoding="utf-8"))
    r = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    if not s["independent_sql_and_gate_pass"] or s["native_model_bindings"] != 24:
        raise ValueError("independent accounting and native lineage audit required")
    bounds = []
    for year, model in s["models"].items():
        for mechanism, fit in model["models"].items():
            bound = 2 * abs(fit["slope"]) * (1 + sum(abs(x) for x in fit["nuisance_z"][1:]))
            swaps = sum(
                d["hurdle_replacements"]
                for d in r["target_diagnostics"][mechanism]
                if d["date"].startswith(year)
            )
            if bound <= 0.0122 and swaps:
                raise ValueError("swaps contradict mathematical prediction bound")
            bounds.append(
                {
                    "year": year,
                    "mechanism": mechanism,
                    "samples": fit["samples"],
                    "slope": fit["slope"],
                    "upper_pair_edge_bps": 10000 * bound,
                    "hurdle_bps": 122,
                    "replacements": swaps,
                }
            )
    identical = [
        m
        for m in s["checks"]
        if all(
            r["records"][m][c]["account_sha256"]
            == r["records"]["stable_lowrisk"][c]["account_sha256"]
            for c in ("41", "82", "102")
        )
    ]
    write_json(
        ROOT / "PREDICTION_DIAGNOSTIC.json",
        {
            "bounds": bounds,
            "byte_identical_control_policies": identical,
            "distinct_nonzero_active_paths": s["distinct_nonzero_active_paths"],
            "pbo_usable_for_court": False,
        },
    )
    if len(identical) != 3 or s["distinct_nonzero_active_paths"] != 0:
        raise ValueError("this narrative requires independently verified zero active paths")
    stable = {str(x["roundtrip_bps"]): x for x in s["rows"] if x["policy"] == "stable_lowrisk"}
    card = {
        "version": "11.11.0",
        "issue": 184,
        "status": "POST_SELECTION_ALLOCATION_OBSERVATION_NOT_VALIDATED_FACTOR",
        "policy": "stable_lowrisk",
        "source_result_sha256": s["source_result_sha256"],
        "snapshot_sha256": s["snapshot_sha256"],
        "runtime_code_sha256": s["runtime_code_sha256"],
        "contract": r["spec"]["contract"],
        "targets_file_sha256": {
            p: file_sha(ROOT / "targets" / (p + ".json")) for p in ("stable_lowrisk", "lowvol")
        },
        "targets_canonical_sha256": {
            p: r["records"][p]["82"]["targets_sha256"] for p in ("stable_lowrisk", "lowvol")
        },
        "initial_capital_cny": 3000000,
        "reference_accounts": stable,
        "selected_after_reused_2023_2024_results": True,
        "raw_trial_lower_bound": s["raw_global_trial_lower_bound"],
        "new_factor_increment": 0,
        "validated_alpha": False,
        "next": "freeze allocation; preregister matched cost/delay/capacity falsification",
    }
    write_json(Path("configs/v11.11-frozen-stability-observation.json"), card)
    definitions_zh = (
        "2023-01-03至2024-12-31，共484交易日，已暴露开发历史；一次性300万元连续账户。"
        "收益=期末净值/300万元−1；增量是两个净总收益率的百分点差，不是沪深300超额，也不是年化截距。"
        "41/82/102bps为名义往返线性成本；费用和资金路径均实际逐日记账。"
    )
    definitions_en = (
        "Reused development from2023-01-03 to2024-12-31,484sessions,one continuous CNY3m account. "
        "Return=final NAV/CNY3m−1;increment is a net total-return difference in percentage points, "
        "not CSI300 excess or annualized regression alpha.41/82/102bps denote nominal linear round-trip costs."
    )
    findings_zh = (
        "三个新机制均未通过：完整逐日账户在所有成本下与稳定低风险对照逐字节相同，主动替换0次、"
        "新增信号收益0。稳定低风险基础配置82bps收益32.06%（961,809.35元）、2023为3.50%、"
        "2024为27.59%，Sharpe1.079、回撤−12.69%；102bps收益29.24%、两年仍正。"
        "它对严格低波动的增量为12.60pp，但不能把基础配置的收益归于资金流、竞价或筹码新因子。"
        "因此冻结为事后发现的配置观察线索，尚未验证。"
    )
    findings_en = (
        "All three new mechanisms fail: their full daily account bytes equal the stable low-risk control "
        "at all costs,with zero discretionary swaps and zero incremental signal return. The stable baseline "
        "returns32.06% (CNY961,809.35) at82bps,with2023+3.50%,2024+27.59%,Sharpe1.079 and−12.69% drawdown; "
        "at102bps it returns29.24%,both years positive. Its12.60pp advantage over strict low-vol belongs "
        "to allocation,not the new signals. Freeze it as a post-selection allocation observation,not validated Alpha."
    )
    methods_zh = (
        "20个连续共同覆盖交易日构造资金流方向/幅度一致性、竞价有符号三阶尾部占比、筹码宽度路径效率。"
        "缺失任一源字段或股票日立即重置窗口；真实零分母才取零。筹码输入是成本85/15分位宽度，不是集中度高度。"
        "在当前最低20日波动率200股中研究；稳定基础每批40股，仍在200池内就保留，用低波动补空缺。"
        "四批固定0/5/10/15相位，20日调仓，一个净额账户；严格低波动对照Top40/10档缓冲。"
        "过去前缀年度扩展拟合，成熟20日标签、5日embargo，风险秩OLS残差化及固定ridge0.01，主动替换门槛122bps。"
        "保留退出所需的全部价格栏；维持原5%ADV代理容量、开盘交易限制。"
    )
    methods_en = (
        "Twenty consecutive common-coverage sessions define signed flow consistency,auction cubic tail balance "
        "and chip-width path efficiency. Missing observations reset windows;only true zero denominators map to zero. "
        "Chip width is the85th–15th cost quantile spread,not concentration height. Research occurs within the200 "
        "lowest current20-session-volatility names. Each stable cohort retains40 incumbents while eligible, "
        "filling vacancies by low-vol rank;strict low-vol usesTop40/buffer10. Four fixed phases0/5/10/15 feed "
        "one netted account. Prefix-only expanding annual fits use mature20-session labels,5-session embargo, "
        "risk-rank residualization,ridge0.01 and122bps discretionary hurdle. Exit prices remain available; "
        "the existing5%ADV proxy capacity and open restrictions are unchanged."
    )
    limits_zh = (
        "无非零主动收益路径，PBO/DSR记为NOT_IDENTIFIABLE，placebo p=1，不伪造统计PASS。"
        "本轮首次原生绑定6拟合+15账户的21份契约、24份模型证据；历史试验下界3310，包括失败和未执行预留。"
        "7997/17596股票样本分别只来自40/88训练信号日，不是同样数量的独立样本；训练前缀有重叠。"
        "仅重用历史，未读取2025/2026。稳定策略的选择也受多重研究影响，较低换手与不同风险暴露都可能解释收益。"
        "没有完整市场/行业/规模归因、独立前向、真实原始股数/手数/最低佣金/公司行为/开盘可成交量认证；"
        "复权碎股、线性费用和ADV代理仍限制实盘解释。加载器校验读取了冻结分钟源，但本轮机制未使用分钟特征。"
    )
    limits_en = (
        "Zero nonzero active paths make PBO/DSR NOT_IDENTIFIABLE;placebo p=1. No statistical PASS is manufactured. "
        "Native lineage binds21 fit/account contracts and24 model-evidence records;raw historical Trial lower bound3310 "
        "includes failed/unused reservations. The7997/17596 stock samples represent only40/88 signal dates with "
        "overlapping training prefixes.2025/2026 were not read. Selection of the stable allocation also incurs "
        "multiple-search bias;turnover and risk exposures may explain its return. Full market/industry/size attribution, "
        "independent forward evidence and raw shares/lots/minimum fees/corporate actions/open liquidity certification "
        "are absent. Adjusted fractional shares and ADV proxies limit live-trading interpretation. The loader verified "
        "and read frozen minute inputs,but this mechanism did not use minute features."
    )
    next_zh = (
        "不降低换股或Court门槛，不继续扫本轮参数。先冻结稳定基础和严格低波动的目标序列，预登记"
        "同成本配对的更高费用、额外执行延迟、四分之一容量挑战，检查增量是手续费节省还是更好的持仓。"
        "补充低波动收益回归、关键盈利日依赖等解释性诊断，不据此调仓或宣称新验证。若失败保留墓碑后转向新有限机制；"
        "若存活仍须独立数据和完整Court，不能保证最终找到可用Alpha。"
    )
    next_en = (
        "Do not lower the hurdle or Court gates,or sweep these parameters. Freeze the stable and strict-lowvol "
        "target sequences,then preregister matched higher-cost,execution-delay and quarter-capacity challenges. "
        "Separate fee savings from holdings performance and diagnose low-vol exposure and dependence on exceptional "
        "days,without trading or tuning on those diagnostics. Archive a failed lead before a new bounded mechanism; "
        "a survivor still needs independent evidence and full Court. Discovery is not guaranteed."
    )
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# V11.11 时间机制与持仓稳定性测试"
            if zh
            else "# V11.11 Temporal Mechanisms and Allocation Stability",
            "",
            "## 结论" if zh else "## Technical summary",
            "",
            findings_zh if zh else findings_en,
            "",
            "## 范围与指标" if zh else "## Scope and definitions",
            "",
            definitions_zh if zh else definitions_en,
            "",
            "## 全部账户" if zh else "## All accounts",
            "",
            "|Policy|bps|2023|2024|Total|Profit CNY|Δ low-vol pp|Δ stable pp|MDD|Sharpe|Fees CNY|",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in s["rows"]:
            lines.append(
                f"|{NAMES[row['policy']]}|{row['roundtrip_bps']}|{row['return2023']:.2%}|{row['return2024']:.2%}|{row['net_return']:.2%}|{row['profit_cny']:,.2f}|{row['increment_lowvol_pp']:+.2f}|{row['increment_hash_pp']:+.2f}|{row['max_drawdown']:.2%}|{row['sharpe']:.3f}|{row['cost_cny']:,.2f}|"
            )
        lines += [
            "",
            "## 预测分差与成本" if zh else "## Predicted edges versus costs",
            "",
            "Pair bound = 2 × abs(slope) × (1 + sum(abs(nuisance rank coefficients))). Ranks lie in[-1,1]; the intercept cancels.",
            "",
            "|Fit year|Mechanism|Upper pair edge bps|Hurdle bps|Swaps|",
            "|---|---|---:|---:|---:|",
        ]
        for b in bounds:
            lines.append(
                f"|{b['year']}|{b['mechanism']}|{b['upper_pair_edge_bps']:.2f}|122|{b['replacements']}|"
            )
        lines += [
            "",
            "## 方法" if zh else "## Methods",
            "",
            methods_zh if zh else methods_en,
            "",
            "## 验证与限制" if zh else "## Verification and limitations",
            "",
            "809 passed,1 skipped; Ruff PASS. Independent SQL/NAV/cash/positions/order fees,21 SQLite Trials,24 model bindings and all target hashes PASS.",
            "",
            limits_zh if zh else limits_en,
            "",
            "## 下一步与待解问题" if zh else "## Next steps and open questions",
            "",
            next_zh if zh else next_en,
            "",
            "Sources: V11_11_RESULT.summary.json; scripts/audit_temporal_epoch.py; immutable local RESULT, INDEPENDENT_AUDIT, NATIVE_FIT_LINEAGE and PREDICTION_DIAGNOSTIC.",
            "",
            "Machine field increment_hash_pp is a legacy label for the stable_lowrisk comparison here; it is NOT a hash-stock benchmark.",
            "",
        ]
        with Path(f"docs/V11_11_RESULT.{lang}.md").open("x", encoding="utf-8", newline="\n") as out:
            out.write("\n".join(lines))
    title = "Temporal Mechanisms | 时间机制与配置稳定性"
    source = {
        "id": "temporal",
        "label": "Independently audited V11.11 accounts",
        "path": "docs/V11_11_RESULT.summary.json",
        "href": "https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.11-temporal-increments/docs/V11_11_RESULT.zh.md",
        "query": {
            "description": "audit_temporal_epoch.py reconciles all saved account bytes with DuckDB SQL and native SQLite/model evidence.",
            "metric_definitions": {
                "net_return": "final_NAV/3000000-1",
                "increment_lowvol_pp": "100*(candidate net total return-strict lowvol net total return)",
                "increment_hash_pp": "100*(candidate net total return-stable lowrisk net total return); legacy field label",
            },
            "filters": ["2023-2024 reused development", "all three mechanisms and three costs"],
        },
    }
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, zh, en in (
        ("summary", "结论 / Technical summary", findings_zh, findings_en),
        ("scope", "范围 / Definitions", definitions_zh, definitions_en),
        (
            "comparisons",
            "全部增量比较 / All increments",
            "图含全部9种机制/成本组合；对low-vol为正，但对稳定基础全部为零。",
            "All nine combinations beat strict low-vol,but add zero to the matched stable baseline.",
        ),
        ("methods", "方法 / Methods", methods_zh, methods_en),
        ("limits", "验证与限制 / Verification and limitations", limits_zh, limits_en),
        ("next", "后续与问题 / Next steps and questions", next_zh, next_en),
    ):
        blocks.append({"id": key, "type": "markdown", "body": f"## {heading}\n\n{zh}\n\n{en}"})
        if key == "comparisons":
            blocks.append({"id": "comparison_chart", "type": "chart", "chartId": "increments"})
    rows = [
        {**x, "label": NAMES[x["policy"]] + f" · {x['roundtrip_bps']}bps"}
        for x in s["rows"]
        if x["policy"] in s["checks"]
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
                        "title": "2023–2024 Δ strict low-vol (pp)",
                        "dataset": "accounts",
                        "sourceId": "temporal",
                        "source": source,
                        "encodings": {
                            "x": {"field": "label", "type": "nominal"},
                            "y": {"field": "increment_lowvol_pp", "type": "quantitative"},
                        },
                        "options": {"orientation": "horizontal"},
                        "palette": {"kind": "sequential", "name": "blue"},
                        "height": 500,
                        "valueFormat": "number",
                    }
                ],
            },
            "snapshot": {"version": 1, "status": "ready", "datasets": {"accounts": rows}},
            "sources": [source],
        },
    )
    write_json(
        ROOT / "report-qa.json",
        {
            "audience": "technical",
            "surface": "mcp-app",
            "confidence": "SHARE_WITH_CAVEATS",
            "chart_contract": "all9 signed pp increments; horizontal zero baseline; 500px blue; paired-control caveat adjacent",
            "delivery": "archived; user requested no ordinary-failure notifications",
            "pixel_qa": "not performed; visible delivery deferred",
            "inference": "zero active paths; PBO/DSR not identifiable",
        },
    )
    print(json.dumps({"bounds": bounds, "identical": identical, "frozen": card["status"]}))


if __name__ == "__main__":
    build()
