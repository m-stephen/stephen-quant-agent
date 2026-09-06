"""Bilingual evidence report, native artifact and offline notebook companion."""

import contextlib
import io
import json
from pathlib import Path

import duckdb

from stephen_quant.workflows.v114_reliable_epoch import write_json

ROOT = Path("artifacts/execution-evidence/epoch-001")


def build():
    s = json.loads(Path("docs/V11_12_RESULT.summary.json").read_text(encoding="utf-8"))
    if not s["independent_audit_pass"]:
        raise ValueError("independent reconciliation required")
    by_policy = {r["policy"]: r for r in s["rows"]}
    a, b = by_policy["stable_lowrisk"], by_policy["lowvol"]
    sections = [
        (
            "finding",
            "结论 / Finding",
            "冻结配置仍值得保留，但尚不能声明为可用 Alpha。真实数量审计暴露了小额再平衡订单的可执行性缺口；本轮没有新回测，也没有将旧收益改成所谓‘整手收益’。",
            "Retain the frozen allocation as an observation, not usable Alpha. Raw-ticket diagnostics reveal a small-rebalancing-order execution gap. No new account was simulated and no historical return was relabeled as a lot-executable return.",
        ),
        (
            "scope",
            "范围与定义 / Scope and definitions",
            "两条冻结的82bps账户，2023–2024共484个交易日，初始300万元。只检查已执行票据和上日实际持仓，不选择新股票、不调参数、不读取2025/2026。累计未分配金额=每笔原买入金额减按当日原价向下取整后的金额再求和；分母为累计买入金额，不是本金、净值、独立订单机会或收益。",
            "Two frozen 82bps accounts,484 sessions in reused2023–2024,starting CNY3m. Only saved executed tickets and prior-close holdings are inspected; no stock selection, tuning or2025/2026 reads. Cumulative unallocated notional sums each original buy minus its raw-price-rounded ticket. Its denominator is cumulative buys,not capital,NAV,independent opportunities or return.",
        ),
        (
            "quantity",
            "买入数量诊断 / Buy-ticket quantities",
            f"稳定配置{a['buy_tickets']:,}笔买单中{a['below_minimum_buy_tickets']:,}笔（{a['below_minimum_buy_tickets'] / a['buy_tickets']:.2%}）不足最低数量；严格低波动为{b['below_minimum_buy_tickets']:,}/{b['buy_tickets']:,}（{b['below_minimum_buy_tickets'] / b['buy_tickets']:.2%}）。所有买单均匹配到原价和已覆盖的沪深规则，没有缺价或未知市场。数量少的订单不代表同等比例的收益损失；下图比较的是票据数量。",
            f"{a['below_minimum_buy_tickets']:,}/{a['buy_tickets']:,} stable-allocation buys ({a['below_minimum_buy_tickets'] / a['buy_tickets']:.2%}) are below the minimum quantity; strict low-vol has {b['below_minimum_buy_tickets']:,}/{b['buy_tickets']:,} ({b['below_minimum_buy_tickets'] / b['buy_tickets']:.2%}). All buys have matched raw prices and supported SH/SZ rules. Small tickets do not imply a proportional return loss; the chart compares ticket counts.",
        ),
        (
            "cash",
            "金额和最低佣金 / Notional and minimum commissions",
            f"稳定配置累计买入{a['buy_notional_cny']:,.2f}元，逐笔舍入累计未分配{a['unallocated_buy_notional_cny']:,.2f}元（{a['unallocated_buy_fraction']:.2%}）；对照为{b['unallocated_buy_fraction']:.2%}。假设6bps佣金且每票最低5元，原始买卖票据需额外{a['extra_minimum_commission_cny']:,.2f}/{b['extra_minimum_commission_cny']:,.2f}元。5元未获用户券商确认；票据在真实整手账户中会变化，因此这些金额既不是收益损失估计，也不能直接扣减旧NAV。",
            f"Stable cumulative buys are CNY{a['buy_notional_cny']:,.2f};ticket-wise rounding leaves CNY{a['unallocated_buy_notional_cny']:,.2f} ({a['unallocated_buy_fraction']:.2%}) unallocated,versus {b['unallocated_buy_fraction']:.2%} for control. Assuming6bps commission with a CNY5 minimum adds CNY{a['extra_minimum_commission_cny']:,.2f}/{b['extra_minimum_commission_cny']:,.2f} on the unchanged saved buy/sell tickets. The broker minimum is unconfirmed. Actual lot-account tickets would change;these are not loss estimates or direct NAV deductions.",
        ),
        (
            "events",
            "公司行为复核范围 / Scoped event evidence",
            f"稳定配置上日持仓有{a['held_factor_change_keys']}个复权因子变化键及{a['held_raw_missing_keys']}个原价缺失键；对照为{b['held_factor_change_keys']}/{b['held_raw_missing_keys']}。两者合并去重为512个键、253只股票：477个变化键和35个缺价键。已生成私有逐项清单，无需先补全市场。因子变化只是线索，不能反推出分红、送转、配股和支付时间；无变化不等于无事件。缺价可能与停牌等有关，本轮不自行填补。",
            f"Prior-close holdings yield{a['held_factor_change_keys']} adjustment-change keys and{a['held_raw_missing_keys']} missing-price keys for stable allocation;control has{b['held_factor_change_keys']}/{b['held_raw_missing_keys']}. Their union is512keys across253stocks:477changes and35missing prices. A private itemized worklist avoids requiring whole-market completion first. Changes are review clues,not dividend/split/rights or payment-date records;no change does not establish event absence. Missing prices may reflect suspensions;none are imputed.",
        ),
        (
            "methods",
            "方法与质量验证 / Methods and QA",
            "原始快照、候选卡、父账户先验SHA-256检查；2个无拟合原生Trial预占后才解析账户/源数值，累计债务3320→3322。独立SQL重算订单和佣金，逐笔核对10,311笔买单的数量上限、下限、最大可买数量及原价对账，重建持仓待核实键并核对SQLite。17项新增针对性测试通过，全套828 passed/1 skipped。报告数据只含汇总；源数据、个股清单和本机路径不入Git。",
            "Snapshot,card and parent-account SHA-256 checks precede two explicitly unfitted native Trial reservations and parsed account/source reads;debt3320→3322. Independent SQL recomputes orders/fees,checks10,311buy tickets for quantity limits,maximal affordable sizing and raw-price reconciliation,reconstructs held review keys and checks SQLite.17new targeted tests pass;full suite828passed/1skipped. Public reports contain aggregates only;raw data,stock lists and local paths remain outside Git.",
        ),
        (
            "limitations",
            "推断边界 / Inference limits",
            "没有真实原股数账本、零股卖出、T+1库存、分红税和到账/送转/配股现金流，也没有真实开盘成交容量证明。当前库元数据有申万行业表，但未发现corporate/action名称表；不据此断言所有旧staging无资料。历史配置事后选中，旧32.06%仍仅为复权碎股模型收益；本轮未执行Alpha Court，不产生DSR/PBO或独立样本认证。",
            "No physical-share inventory,odd-lot sale,T+1 inventory,dividend tax/payment/split/rights cashflow or real-opening-capacity proof is supplied. Catalog metadata contains SW industry tables but no corporate/action-named table;this does not prove every older staging source is empty. The allocation was selected post hoc;the old32.06% remains an adjusted fractional-share model return. This diagnostic runs no Alpha Court and issues no DSR/PBO or independent-evidence certificate.",
        ),
        (
            "next",
            "下一步 / Next actions",
            "保持冻结卡。先用现有数据做有限的‘低波风格×持仓稳定性’匹配对照，区分少换仓收益与预测增量；不要重复5个已完成压力情景，也不要因暂缺全市场PIT而停止一切研究。并行的执行改进仅围绕上述清单和原股数/现金守恒，不能用因子变化伪造公司行为。任何改动后的交易政策另计Trial、另命名候选；认证还须独立窗口及完整Court，不以本轮工程测试代替。",
            "Keep the card frozen. Next preregister a finite matched low-vol-style versus holding-stability comparison using existing data to separate turnover savings from predictive increment. Do not repeat completed stresses or block all research on whole-market PIT completion. Execution engineering is scoped to this worklist and raw-share/cash conservation,never fabricated events. Modified trading policies require new Trials and separate candidate identities;certification still needs independent evidence and full Court.",
        ),
    ]
    sources_text = "Sources: [SSE STAR](https://edu.sse.com.cn/tib/), [SZSE 2023](https://investor.szse.cn/knowledge/qa/t20230306_599093.html), [SSE quantity notice](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/tz/c/c_20230209_5716007.shtml). Local: docs/V11_12_RESULT.summary.json; scripts/verify_execution_evidence.py; immutable execution-evidence operation."
    for language in ("zh", "en"):
        lines = [
            "# V11.12 执行可行性审计"
            if language == "zh"
            else "# V11.12 Execution Feasibility Audit",
            "",
        ]
        for key, heading, cn, en in sections:
            lines.extend(["## " + heading, "", cn if language == "zh" else en, ""])
            if key == "quantity":
                lines += [
                    "|Policy|Buys|Below minimum|Unallocated / buy notional|Extra commission CNY|Held factor changes|",
                    "|---|---:|---:|---:|---:|---:|",
                ]
                for r in s["rows"]:
                    lines.append(
                        f"|{r['policy']}|{r['buy_tickets']:,}|{r['below_minimum_buy_tickets']:,}|{r['unallocated_buy_fraction']:.2%}|{r['extra_minimum_commission_cny']:,.2f}|{r['held_factor_change_keys']}|"
                    )
                lines += [""]
        lines += [
            sources_text,
            "",
            "Notebook QA: code cells replayed sequentially in Python; native Jupyter kernel/nbformat unavailable in both installed runtimes. Widget schema validation recorded separately; visible/pixel QA deferred under the user's quiet-until-usable instruction.",
            "",
        ]
        with Path(f"docs/V11_12_RESULT.{language}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as f:
            f.write("\n".join(lines))
    query = "SELECT a.* FROM (SELECT unnest(chart_rows) a FROM read_json_auto('docs/V11_12_RESULT.summary.json')) ORDER BY a.quantity_status,a.policy"
    with duckdb.connect() as c:
        cur = c.execute(query)
        cols = [x[0] for x in cur.description]
        chart_rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    source = {
        "id": "execution",
        "label": "Independently reconciled saved-ticket audit",
        "path": "docs/V11_12_RESULT.summary.json",
        "query": {
            "sql": query,
            "engine": "DuckDB",
            "language": "sql",
            "tables_used": ["docs/V11_12_RESULT.summary.json"],
            "description": "All two frozen accounts and both buy quantity outcomes; counts are tickets,not independent samples or returns.",
            "metric_definitions": {
                "ticket_count": "number of original executed buy tickets in each raw-size category",
                "share_of_buy_tickets": "category count / all original executed buy tickets for the same policy",
            },
        },
    }
    title = "Execution Evidence | 执行证据审计"
    blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]
    for key, heading, cn, en in sections:
        blocks.append(
            {
                "id": key,
                "type": "markdown",
                "body": f"## {heading}\n\n{cn}\n\n{en}",
                "sourceId": "execution",
            }
        )
        if key == "quantity":
            blocks.append({"id": "quantities", "type": "chart", "chartId": "quantity"})
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
                    "id": "quantity",
                    "type": "bar",
                    "dataset": "quantities",
                    "title": "2023–2024 Buy-ticket Quantity Status",
                    "description": "Two frozen policies; ticket counts,not return or independent sample counts",
                    "sourceId": "execution",
                    "source": source,
                    "encodings": {
                        "x": {"field": "quantity_status", "type": "nominal"},
                        "y": {"field": "ticket_count", "type": "quantitative"},
                        "color": {"field": "policy", "type": "nominal"},
                    },
                    "height": 350,
                    "palette": {"kind": "categorical", "name": "default"},
                }
            ],
        },
        "snapshot": {"version": 1, "status": "ready", "datasets": {"quantities": chart_rows}},
        "sources": [source],
    }
    write_json(ROOT / "report-artifact.json", artifact)
    write_json(
        ROOT / "report-qa.json",
        {
            "surface": "codex_desktop:mcp-app",
            "mode": "unknown",
            "chart_contract": "4 rows,2 quantity categories x2 policies; grouped count bars,zero baseline,visible policy legend,350px; blue and gold intent",
            "confidence": "SHARE_WITH_CAVEATS",
            "pixel_qa": "DEFERRED_USER_QUIET_INSTRUCTION",
            "sources": "frozen raw-price extract and original saved orders; independent SQL and quantity audit; aggregated in summary",
            "no_parallel_html": True,
        },
    )
    notebook()
    print(
        json.dumps(
            {"bilingual_reports": True, "chart_rows": len(chart_rows), "validated_alpha": False}
        )
    )


def notebook():
    def md(text):
        return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}

    def code(text):
        return {
            "cell_type": "code",
            "metadata": {},
            "source": text.splitlines(keepends=True),
            "execution_count": None,
            "outputs": [],
        }

    cells = [
        md(
            "# V11.12 Execution Evidence Companion\n\n## tl;dr\nNo usable-Alpha certification. Buy-ticket constraints and scoped corporate-action gaps require physical-account validation.\n\n## Context and methods\nReplay the public aggregate audit,not a new market test. Two previously exposed2023–2024 accounts; counts are not independent samples. Detailed reconciliation lives in scripts/verify_execution_evidence.py with private frozen artifacts."
        ),
        md(
            "## Data\nRun from the repository or notebooks directory. Only a public aggregate JSON is read; no warehouse access,credentials or sealed dates."
        ),
        code(
            "import json\nfrom pathlib import Path\nimport duckdb\nroot = Path.cwd()\nif not (root / 'docs/V11_12_RESULT.summary.json').exists():\n    root = root.parent\nsource = root / 'docs/V11_12_RESULT.summary.json'\ndata = json.loads(source.read_text(encoding='utf-8'))\nassert data['independent_audit_pass'] and not data['validated_alpha']\nprint('Source:', source.name, 'Trial lower bound:', data['raw_trial_lower_bound'])\n"
        ),
        md(
            "## Results\nThe denominator is original executed buy tickets for each frozen policy. Aggregate unallocated notional is not lost capital or return."
        ),
        code(
            "with duckdb.connect() as con:\n    rows = con.execute(\"SELECT a.policy,a.buy_tickets,a.below_minimum_buy_tickets,a.unallocated_buy_fraction,a.extra_minimum_commission_cny FROM (SELECT unnest(rows) a FROM read_json_auto(?)) ORDER BY a.policy\", [str(source)]).fetchall()\nassert len(rows) == 2\nassert sum(r[1] for r in rows) == 10311\nfor row in rows:\n    print(row)\nassert data['worklist_reason_counts'] == {'held_adjustment_change':477,'held_raw_missing':35}\nprint('Scoped keys:', data['scoped_worklist_keys'], 'stocks:', data['worklist_unique_instruments'])\n"
        ),
        md(
            "## Takeaways\nFreeze the observation. Diagnose turnover/style on current data; use the scoped worklist for raw-share/cash reconciliation. No fabricated dividend events,no revised PnL and no Alpha Court PASS.\n\n## QA boundary\nCode cells were replayed in order in one standard Python namespace. Native Jupyter kernel and nbformat validation are unavailable in this host's installed runtimes; this is not a claim of kernel execution. Full engine tests and the independent audit were executed separately."
        ),
    ]
    namespace, count = {}, 0
    for cell in cells:
        if cell["cell_type"] != "code":
            continue
        count += 1
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture):
            # Only the fixed code cells authored above; never source data or user-provided code.
            exec(compile("".join(cell["source"]), f"notebook-cell-{count}", "exec"), namespace)  # noqa: S102
        cell["execution_count"] = count
        cell["outputs"] = [
            {
                "output_type": "stream",
                "name": "stdout",
                "text": capture.getvalue().splitlines(keepends=True),
            }
        ]
    value = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
            "qa": {
                "sequential_python_cell_replay": "PASS",
                "native_jupyter_kernel": "UNAVAILABLE",
                "nbformat_validator": "UNAVAILABLE",
            },
        },
        "cells": cells,
    }
    write_json(Path("notebooks/V11_12_execution_evidence.ipynb"), value)
    write_json(ROOT / "notebook-qa.json", value["metadata"]["qa"])


if __name__ == "__main__":
    build()
