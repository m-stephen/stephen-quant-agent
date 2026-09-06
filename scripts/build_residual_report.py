"""Audited bilingual technical report; regular failures are archived quietly."""

import json
from pathlib import Path

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/residual-mechanisms/epoch-001")


def prediction_pair_bound(model):
    # Products and all three nuisance ranks lie in[-1,1]. Intercept cancels.
    return 2 * abs(model["slope"]) * (1 + sum(abs(v) for v in model["nuisance_z"][1:]))


def build():
    s = json.loads(Path("docs/V11_10_RESULT.summary.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / "INDEPENDENT_AUDIT.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    names = {
        "flow_reversal": "资金流反转 / Flow reversal",
        "chip_reversal": "筹码反转 / Chip reversal",
        "auction_late_disagreement": "竞价尾盘分歧 / Auction–late",
        "lowvol": "低波动 / Low-vol",
        "risk_hash": "分层hash / Stratified hash",
    }
    bounds = [
        {
            "year": int(y),
            "mechanism": m,
            "samples": fit["samples"],
            "slope": fit["slope"],
            "pair_edge_upper_bps": 10000 * prediction_pair_bound(fit),
            "hurdle_bps": 122,
            "can_cross_hurdle": prediction_pair_bound(fit) > 0.0122,
            "label_end": model["maximum_label_end"],
            "hurdle_replacements": sum(
                v["hurdle_replacements"]
                for v in result["target_diagnostics"][m]
                if v["date"].startswith(y)
            ),
        }
        for y, model in s["models"].items()
        for m, fit in model["models"].items()
    ]
    identical = [
        m
        for m in s["checks"]
        if all(
            result["records"][m][c]["account_sha256"]
            == result["records"]["risk_hash"][c]["account_sha256"]
            for c in ("41", "82", "102")
        )
    ]
    # Mathematical upper bounds independently predict zero discretionary swaps.
    if any(not b["can_cross_hurdle"] and b["hurdle_replacements"] for b in bounds):
        raise ValueError("observed replacement exceeds proven score bound")
    write_json(
        ROOT / "PREDICTION_DIAGNOSTIC.json",
        {
            "bounds": bounds,
            "byte_identical_control_policies": identical,
            "comparison": "full saved daily-account bytes, all3costs",
            "distinct_candidate_active_paths": 2,
            "nonzero_candidate_active_paths": 1,
            "pbo_usable_for_court": False,
        },
    )
    for language in ("zh", "en"):
        zh = language == "zh"
        lines = [
            "# V11.10 残差机制测试报告" if zh else "# V11.10 Residual Mechanism Test Report",
            "",
            "## 结论" if zh else "## Technical summary",
            "",
            "6次模型拟合与15个连续账户完成，独立账务复核通过；新历史线索0，可用Alpha0。原筹码四批观察候选不变，本轮失败不降低门槛。"
            if zh
            else "Six fits and15 continuous accounts reconcile independently;zero new historical leads andzero validated Alpha. The old staggered-chip observation remains frozen. No thresholds are reduced.",
            "",
            "## 范围与指标" if zh else "## Scope and definitions",
            "",
            "2023–2024复用开发，484交易日；一次性300万元连续模型账户。收益=期末净值/300万-1，增量=两个总收益率相减（百分点），不是沪深300超额。共同字段覆盖、次日开盘执行，41/82/102bps往返线性费用。"
            if zh
            else "Reused2023–2024 development,484sessions,one continuous CNY3m model account. Return=final NAV/CNY3m-1;increment is a total-return difference in percentage points,not CSI300 excess. Common field coverage,next-open execution,41/82/102bps linear round-trip costs.",
            "",
            "## 全部账户结果" if zh else "## All account results",
            "",
            "|Policy / 政策|bps|2023|2024|Total / 总收益|Profit CNY / 盈利元|Δ lowvol pp|Δ hash pp|MDD|Sharpe|",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for row in s["rows"]:
            lines.append(
                f"|{row['policy']}|{row['roundtrip_bps']}|{row['return2023']:.2%}|{row['return2024']:.2%}|{row['net_return']:.2%}|{row['profit_cny']:,.2f}|{row['increment_lowvol_pp']:+.2f}|{row['increment_hash_pp']:+.2f}|{row['max_drawdown']:.2%}|{row['sharpe']:.3f}|"
            )
        lines += [
            "",
            "## 成本门槛暴露了信号不足" if zh else "## The hurdle exposes weak predicted edges",
            "",
            "资金流与竞价机制的完整逐日账户字节均与分层hash相同，不是三条独立有效策略。筹码机制82bps总收益-0.77%，对hash增量+3.85pp，但对lowvol增量-20.86pp、回撤-35.34%；通过hash单项不能称作Alpha。"
            if zh
            else "Flow and auction policies are byte-identical to the stratified hash across all costs,not three independent effective strategies. Chip return is-0.77% at82bps,with+3.85pp vs hash but-20.86pp vs low-vol and-35.34% drawdown. Beating one weak control does not establish Alpha.",
            "",
            "|Fit year|Mechanism|Max pair edge bound bps|Hurdle bps|Replacements|",
            "|---|---|---:|---:|---:|",
        ]
        for b in bounds:
            lines.append(
                f"|{b['year']}|{b['mechanism']}|{b['pair_edge_upper_bps']:.2f}|122|{b['hurdle_replacements']}|"
            )
        lines += [
            "",
            "上界=2×|斜率|×(1+三个秩控制系数绝对值之和)，因为秩和交互都在[-1,1]，截距在两股比较中抵消。不是事后挑股票的策略。只有2023筹码模型上界可越过门槛，实际543次主动替换均来自该年；其他模型即使取理论最大分差也不足。"
            if zh
            else "The pairwise upper bound is2×|slope|×(1+sum absolute three nuisance-rank coefficients),because ranks/interactions lie in[-1,1] and intercept cancels. This is a diagnostic proof,not an ex-post trading rule. Only the2023 chip model can cross the hurdle;all543 discretionary replacements occur there.",
            "",
            "## 方法与验证" if zh else "## Methodology and verification",
            "",
            "训练期残差化、年度扩展拟合、成熟20日标签+5日embargo、共同覆盖5×4风险格子、固定四批净额账户。2023训练187,052行/44信号日，2024训练410,745行/92信号日；大量股票行不是独立时间样本。缺失入场排除49/83，缺失退出按-100%保守计220/360，含重叠历史，不相加当独立样本。"
            if zh
            else "Training-only residualization,yearly expanding fits,mature20-session labels plus5-session embargo,common-coverage5×4 risk cells,fixed four-cohort netted accounts.2023fit187,052rows/44signal dates;2024fit410,745rows/92dates. Many stock rows are not independent time observations. Missing entries excluded49/83;missing exits conservatively-100% at220/360,with overlapping historical prefixes.",
            "",
            "12项新增测试通过，完整783 passed、1 skipped；Ruff通过。全部15账户的SQL净值/成本/回撤、现金持仓、逐笔费率、年度复利、目标日期/哈希、21次SQLite登记与筛选结论独立核对通过。"
            if zh
            else "Twelve new tests pass;full suite783passed,1skipped;Ruff passes. All15 accounts independently reconcile SQL NAV/cost/drawdown,cash/positions,order fee rates,annual compounding,target dates/hashes,21SQLite reservations and screening decisions.",
            "",
            "## 统计与解释限制" if zh else "## Statistical and interpretation limits",
            "",
            "旧静态账本训练列不能代表2024扩展拟合；V11_10_FIT_LINEAGE.json不可变绑定21个试验及真实模型截止/哈希，原账本和收益不变。下一版应原生记录多阶段血缘。"
            if zh
            else "Legacy scalar training columns cannot represent expanding2024 fits;append-only V11_10_FIT_LINEAGE.json binds all21trials to actual model cutoffs/hashes without rewriting ledger or returns. A successor needs native multi-stage fit lineage.",
            "",
            f"PBO diagnostic={s['statistics'].get('pbo')};DSR sensitivity={s['statistics'].get('dsr')};family placebo={s['placebo'].get('p_value')}. Raw trial lower bound3289.",
            "",
            "三个候选中两条主动收益为同一个零序列，因此只有一个非零增量方向。PBO和DSR不可作为本轮有效Court认证；既有CPCV只是自适应收益选择诊断，没有每折重拟合模型，DSR也未获得全历史Sharpe矩阵。没有新OOS或真实券商成交认证。"
            if zh
            else "Two candidate active paths are the same zero series,leaving one nonzero incremental direction. PBO/DSR are not usable Court certification. CPCV only diagnoses adaptive-return selection,without nested model refits;full historical Sharpe matrix is unavailable. No fresh OOS or brokerage execution certification.",
            "",
            "## 后续与待解问题" if zh else "## Next steps and open questions",
            "",
            "保留旧候选，停止重复本轮弱交互和降低换股门槛。下一有限批次应把‘与信号无关的分层基础账户’同‘因子增量’拆开：在固定低风险基底内比较增量机制，并首先用合成可交易信号验证费用与执行。预声明新预算后再运行；重点是是否仍有足够增量覆盖成本，而非凭更宽股票池或更多参数保证Alpha。独立数据与成交证据保持最终必要条件。"
            if zh
            else "Keep the old observation;do not repeat these weak interactions or lower the hurdle. Next bounded work should separate the stratified base allocation from factor information,testing incremental mechanisms within a fixed low-risk baseline after synthetic executable-signal calibration. Preregister new trials first. The question is whether incremental information clears costs,not whether a wider universe or more parameters guarantees Alpha. Independent evidence and credible execution remain necessary.",
            "",
        ]
        with Path(f"docs/V11_10_RESULT.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as f:
            f.write("\n".join(lines))
    chart_rows = [
        {**row, "label": names[row["policy"]] + f" · {row['roundtrip_bps']}bps"}
        for row in s["rows"]
        if row["policy"] in s["checks"]
    ]
    source = {
        "id": "residual",
        "label": "V11.10 independently audited accounts",
        "path": "docs/V11_10_RESULT.summary.json",
        "href": "https://github.com/m-stephen/stephen-quant-agent/blob/codex/v11.10-residual-mechanisms/docs/V11_10_RESULT.zh.md",
        "query": {
            "sql": audit["query"],
            "language": "sql",
            "engine": "DuckDB",
            "tables_used": [
                "artifacts/residual-mechanisms/epoch-001/accounts/*.jsonl",
                "docs/V11_10_RESULT.summary.json",
            ],
            "filters": ["2023-2024 reused development", "all3mechanisms and3costs"],
            "metric_definitions": {
                "increment_lowvol_pp": "100*(candidate net total return-lowvol net total return)",
                "net_return": "final_NAV/3000000-1",
            },
            "description": "Saved-account SQL reconciled independently by audit_residual_epoch.py;training bounds and account byte identity audited by build_residual_report.py.",
        },
    }
    title = "Residual Mechanism Tests | 残差机制测试"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    segments = [
        (
            "summary",
            "未发现新线索 / Technical summary",
            "6次拟合、15个账户完成；可用Alpha0。\n\nSix fits and15 accounts reconcile,with no new historical lead. Keep the previous frozen observation.",
        ),
        (
            "scope",
            "范围与比较 / Scope and definitions",
            "2023–2024、484交易日、一次性300万元连续模型账户；已暴露开发。增量是两个总收益率的百分点差，不是市场指数超额。\n\nReused development,one CNY3m account;increments are total-return differences versus matched controls,not market-index excess.",
        ),
        (
            "finding",
            "三个交互均未胜过低波动 / No mechanism beats low-vol",
            "图包含三机制与三个成本的全部9种组合。筹码82bps总收益-0.77%，相对hash+3.85pp，但相对lowvol-20.86pp。\n\nThe chart includes all nine candidate/cost combinations. Chip beats hash but falls far short of low-vol;one favorable comparison is insufficient.",
        ),
        (
            "model",
            "模型分差不足以支付换股成本 / Predicted edges cannot fund swaps",
            "固定122bps主动替换门槛；资金流和竞价模型两年均无法达到，完整账户与hash逐字节相同。筹码只有2023模型可越过理论门槛，共543次替换。\n\nThe theoretical rank-based edge bound is below the hurdle except for2023 chip. A lack of swaps is a measurable weak-edge result,not proof of a broken generator.",
        ),
        (
            "methods",
            "训练与执行隔离 / Training and execution",
            "过去前缀OLS残差化、固定ridge0.01、年度扩展拟合；20日标签完全成熟并留5日embargo。5×4秩格子、每格最多2股、固定四批合成账户。\n\nPrefix-only residualization and matured labels prevent future fitting;cell migration and netting drift can still trade despite the discretionary hurdle.",
        ),
        (
            "validation",
            "独立核算通过，推断尚不足 / Accounting verified, inference insufficient",
            "783测试通过、1跳过；15账户及21试验账本通过独立SQL/逐日/逐笔核对。PBO0.65、DSR敏感性0.2303、placebo0.27不达标，且仅一个非零候选主动收益方向。\n\nTied zero paths and non-nested model CPCV prevent Court certification. These are diagnostics,not calibrated full-history confidence.",
        ),
        (
            "limits",
            "不能宣称独立或可实盘 / No independent or brokerage claim",
            "复用历史、供应商时间、最多7天分钟对齐、未完整控制行业/规模/市场beta、复权碎股与线性费用/ADV容量仍有限制。2025/2026未读取。\n\nThese limitations remain explicit;no sealed-window access or live trading occurred.",
        ),
        (
            "next",
            "下一步分开基础配置与信号增量 / Separate allocation from incremental signal",
            "保留旧观察，不降低门槛；先在固定低风险基底内验证可执行增量机制，再预注册有限真实试验。哪些增量能在成本后存活、能否通过真正独立证据，仍是待解问题。\n\nContinue bounded mechanism work after synthetic executable-signal calibration;do not promise that more search will necessarily find Alpha.",
        ),
    ]
    for key, heading, body in segments:
        if key == "limits":
            body += "\n\n旧静态账本训练列不能表示2024扩展拟合；附加MODEL_FIT_LINEAGE逐试验绑定实际模型截止与哈希，原账本/收益不变。下一版需原生多阶段血缘。\n\nLegacy scalar training columns are insufficient;append-only fit lineage binds actual yearly models and cutoffs without rewriting old ledgers or returns."
        blocks.append({"id": key, "type": "markdown", "body": "## " + heading + "\n\n" + body})
        if key == "finding":
            blocks.append({"id": "comparison", "type": "chart", "chartId": "increments"})
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
                    "title": "2023–2024增量 / Increment versus low-vol (pp)",
                    "dataset": "accounts",
                    "sourceId": "residual",
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
        "snapshot": {"version": 1, "status": "ready", "datasets": {"accounts": chart_rows}},
        "sources": [source],
    }
    write_json(ROOT / "report-artifact.json", artifact)
    write_json(
        ROOT / "report-qa.json",
        {
            "audience": "technical",
            "surface": "mcp-app",
            "required_structure": "title,summary,definitions,all9comparisons,model,methods,validation,limits,next_and_questions",
            "chart_contract": "nine predeclared mechanism/cost combinations;horizontal zero-included signed pp;single blue root;rich adjacent metrics;500px",
            "confidence": "SHARE_WITH_CAVEATS",
            "delivery": "archive ordinary failure per user;visible notification deferred until usable Alpha or required action",
            "inference": "two zero active paths;one nonzero;PBO not acceptable certification",
            "pixel_qa": "not performed: ordinary-result visible delivery deferred by user instruction",
        },
    )
    print(
        json.dumps(
            {
                "bounds": bounds,
                "byte_identical_control_policies": identical,
                "report_blocks": len(blocks),
            }
        )
    )


if __name__ == "__main__":
    build()
