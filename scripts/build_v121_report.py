"""Build canonical bilingual technical report inputs from completed frozen evidence."""

import argparse
import json
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from stephen_quant.discovery.research_reset.contracts import digest
from stephen_quant.discovery.research_reset.runner import read_json, write_new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    dev = read_json(ROOT / "artifacts/v121-development/RESULT.json")
    audit = read_json(ROOT / "artifacts/v121-audit/RESULT.json")
    validations = [
        read_json(ROOT / f"artifacts/{folder}/VERIFICATION.v2.json")
        for folder in ("v121-development", "v121-audit")
    ]
    for result, validation in zip((dev, audit), validations, strict=True):
        if (
            validation["result_sha256"] != digest(result)
            or validation["status"] != "PASS_HASH_LEDGER_PAIRED_NAV"
        ):
            raise ValueError("verified completed results required")
    suite = ET.parse(ROOT / "artifacts/v121-full.xml").getroot().find("testsuite")
    tests = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
    tests["passed"] = tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"]
    report_suite = ET.parse(ROOT / "artifacts/v121-report-tests.xml").getroot().find("testsuite")
    report_tests = {
        key: int(report_suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")
    }
    if report_tests["failures"] or report_tests["errors"] or report_tests["skipped"]:
        raise ValueError("report-only reconciliation regressions must pass")
    tests["additional_report_tests_passed"] = report_tests["tests"]
    if tests["failures"] or tests["errors"]:
        raise ValueError("complete successful regression required for final report")
    summary = {
        "audit": {
            key: audit[key]
            for key in ("calibration", "scenarios", "counts", "plan_sha256", "elapsed_seconds")
        },
        "design": dev["design"],
        "measurement": dev["measurement"],
        "development_counts": dev["counts"],
        "validations": validations,
        "tests": tests,
        "validated_alpha": False,
        "historical_raw_attempts": 3733,
        "empirical_trial_delta": 0,
    }
    write_new(output / "summary.json", summary)
    created = datetime.now(timezone.utc).isoformat()
    source = {
        "id": "verified",
        "label": "V12.1 completed synthetic development, reserved audit and independent reconciliation",
        "path": str((output / "summary.json").resolve().relative_to(ROOT)).replace("\\", "/"),
        "query": {
            "engine": "Python 3.10",
            "language": "python",
            "id": digest(summary),
            "executed_at": created,
            "description": "build_v121_report.py reads hashed complete results, independent verifier receipts and full JUnit; no new label or account evaluation.",
            "tables_used": [
                "artifacts/v121-development/RESULT.json",
                "artifacts/v121-audit/RESULT.json",
                "artifacts/v121-full.xml",
            ],
            "filters": [
                "144 fixed development paths;8 per cell",
                "all reserved paths; no failed-seed exclusion",
                "synthetic only; CNY3m and0/82/164bps costs",
            ],
            "metric_definitions": {
                "promotion": "both positive costs:paired mean>=1bp/day,HAC(10)t>=2.5,both evaluation halves positive",
                "coverage": "fraction of2000 independent stationary zero-mean repetitions with0 inside mean+-1.96SE",
                "audit_interval": "exact binomial,0.05/(4scenarios*3looks*2tails)",
                "dev_rate": "promotion count divided by8; not adjusted power evidence",
            },
        },
    }
    for language in ("zh", "en"):
        zh = language == "zh"
        title = (
            "V12.1：测量边界与因子检出能力"
            if zh
            else "V12.1: measurement limits and signal detectability"
        )
        rows = []
        names = {
            "linear": "线性" if zh else "Linear",
            "interaction": "交互" if zh else "Interaction",
        }
        for cell in dev["design"]["cells"]:
            if cell["scenario"].endswith("null") or cell["strength_multiplier"] != 1.0:
                continue
            for field, label in (
                ("promoted", "原政策" if zh else "Gross primary"),
                ("net_promoted", "训练净重排" if zh else "Train-net diagnostic"),
            ):
                rows.append(
                    cell
                    | {
                        "label": f"{cell['length']} / {names[cell['scenario']]}",
                        "policy": label,
                        "rate_pct": cell[field] / 8 * 100,
                    }
                )
        coverage = [
            {
                "rho": row["rho"],
                "n": row["n"],
                "rho_group": f"rho={row['rho']}",
                "length_label": str(row["n"]),
                "coverage_pct": row["nominal_interval_coverage"] * 100,
            }
            for row in dev["measurement"]["rows"]
        ]
        # The portable chart widget requires SQL provenance. Execute this actual
        # read-only JSON projection in memory; upstream arithmetic remains the
        # hash-verified Python summary, not an invented market database query.
        sql = "SELECT value AS row_json FROM json_each(:rows) ORDER BY CAST(key AS INTEGER)"
        chart_sources = []
        datasets = {}
        with sqlite3.connect(":memory:") as connection:
            for name, values in (("development", rows), ("coverage", coverage)):
                payload = json.dumps(values, ensure_ascii=False, allow_nan=False)
                datasets[name] = [
                    json.loads(row[0]) for row in connection.execute(sql, {"rows": payload})
                ]
                chart_sources.append(
                    {
                        "id": name,
                        "label": f"{name}: verified summary JSON projection",
                        "path": source["path"],
                        "query": {
                            "engine": "SQLite in-memory JSON1",
                            "language": "sql",
                            "sql": sql,
                            "executed_at": created,
                            "id": digest({"sql": sql, "rows": values}),
                            "parameters": {"rows_sha256": digest(values)},
                            "tables_used": ["json_each(:rows)"],
                            "description": "Actual SQL projection of the scalar chart rows produced above from verified summaries. No market reads or new trials.",
                            "upstream_source_id": "verified",
                        },
                    }
                )
        charts = [
            {
                "id": "development",
                "type": "bar",
                "title": "开发晋级比例" if zh else "Development promotion rates",
                "description": "每格8路径；跨长度相关，不是保留验收"
                if zh
                else "8 paths per cell; paired across lengths, not reserved evidence",
                "showDescription": True,
                "dataset": "development",
                "sourceId": "development",
                "encodings": {
                    "x": {"field": "label", "type": "nominal"},
                    "y": {"field": "rate_pct", "type": "quantitative"},
                    "color": {"field": "policy", "type": "nominal"},
                },
                "palette": {"kind": "categorical", "colors": ["#3B6FB6", "#C9973B"]},
                "options": {"orientation": "horizontal", "grouping": "grouped", "showLegend": True},
            },
            {
                "id": "coverage",
                "type": "bar",
                "title": "名义95%区间的实际覆盖"
                if zh
                else "Actual coverage of nominal95% intervals",
                "description": "每格2,000次零均值重复；单位%；目标95%"
                if zh
                else "2,000 zero-mean replications per cell;percent; nominal target95%",
                "showDescription": True,
                "dataset": "coverage",
                "sourceId": "coverage",
                "encodings": {
                    "x": {"field": "length_label", "type": "nominal"},
                    "y": {"field": "coverage_pct", "type": "quantitative"},
                    "color": {"field": "rho_group", "type": "nominal"},
                },
                "palette": {"kind": "categorical", "colors": ["#3B6FB6", "#C9973B", "#D07A38"]},
                "options": {"grouping": "grouped", "showLegend": True},
            },
        ]
        blocks = [{"id": "title", "type": "markdown", "body": "# " + title}]

        def text(key, body, blocks=blocks):
            blocks.append({"id": key, "type": "markdown", "body": body, "sourceId": "verified"})

        text(
            "summary",
            (
                f"## 技术摘要\n\n唯一360日合成保留验收：**{audit['calibration']}**。当前没有已认证市场Alpha；真实标签新增0，历史尝试下界3,733未变。\n\n本版完成了审查共识、实现复审、144开发路径及独立证据核验。全量回归{tests['passed']}通过、{tests['skipped']}跳过。公式计算正确与统计覆盖可靠必须分开；增加观察长度也无法挽救被成本消耗的微弱信号。"
                if zh
                else f"## Technical summary\n\nThe single360-session synthetic reserved audit is **{audit['calibration']}**. No certified market Alpha; no new empirical trials; historical lower bound3733 retained.\n\nIndependent reviewer agreement preceded implementation and the144-path development run. Full regression:{tests['passed']} passed,{tests['skipped']} skipped. Numerical correctness is distinct from valid statistical coverage; longer observation cannot rescue an economic effect consumed by costs."
            ),
        )
        text(
            "test-scope",
            f"全量回归针对冻结决策代码：{tests['passed']}通过、{tests['skipped']}跳过；之后新增的只读报告核验单独{report_tests['tests']}项通过。报告和包版本说明不修改已冻结研究流水线。"
            if zh
            else f"Full regression on frozen decision code:{tests['passed']} passed,{tests['skipped']} skipped. Subsequently added read-only report verification:{report_tests['tests']} tests passed separately. Reporting and package metadata do not change the frozen research pipeline.",
        )
        text(
            "scope",
            (
                "## 这些数字衡量什么\n\n全部为程序生成的24只虚构股票、六风险组；训练1–95日，评估从第100日开始，长度120/360/720。原毛评分搜索固定48结构，300万连续账户，0/82/164bps往返成本。晋级要求双成本下相对risk-only日均增量≥1bp、HAC(10)t≥2.5、两个评估半段均为正。\n\n开发每格8条路径，长短长度及强弱机制之间配对相关，不把144当成144个独立真实市场证据。保留验收的独立单位是完整来源与搜索路径，不是股票数、公式数或账户数。"
                if zh
                else "## Scope and definitions\n\nAll sources are generated:24 fictional assets,six groups;train1–95,evaluate from100 for120/360/720 sessions.48-structure gross search,CNY3m continuous accounts,0/82/164bps roundtrip costs. Promotion requires paired mean>=1bp/day,HAC(10)t>=2.5 and both half-means positive at BOTH positive costs.\n\nDevelopment has8 paths per cell,paired across lengths and strength.144 is not144 independent market observations. A reserved independent unit is the complete generated source/search path,not an asset,formula or account."
            ),
        )
        text(
            "dev-finding",
            (
                "## 较长观察改善全强度检出，但净重排没有显示替换价值\n\n360日全强度线性7/8、交互8/8晋级，正确表达参考均8/8；两类null均0/8，满足事先规定的最短长度粗筛。720不被事后改选。净重排在360日分别5/8、6/8，仅作为训练目标错配诊断，不取代主政策。样本很小，不能宣称净重排普遍更差。"
                if zh
                else "## Longer observation helps full-strength signals; no evidence to replace the primary\n\nAt360 sessions,full-strength linear7/8 and interaction8/8 promote;known-expression references each8/8;both nulls0/8. This satisfies the predeclared shortest-length development screen,not a power confidence bound. Net reranking yields5/8 and6/8,and remains diagnostic. Eight paths cannot establish universal inferiority."
            ),
        )
        blocks.append({"id": "dev-chart", "type": "chart", "chartId": "development"})
        text(
            "measurement",
            (
                "## HAC数值正确，不等于95%置信覆盖有效\n\n独立Bartlett矩阵与生产公式的SE最大差约2.78e−17。固定lag10的名义95%区间，在120日、rho=0/0.3/0.8下实际覆盖91.90%/90.35%/82.95%；720日强AR也只有87.65%。这不是单纯过于保守，而是有限样本及相关性下低估不确定性。成本后null的零晋级不能代替零均值统计尺寸验证。\n\n下图每格2,000次独立重复，误差区间是逐格描述性区间。保留验收只能约束指定合成分布的完整路径规则，不把HAC的t值当通用有效p值。"
                if zh
                else "## Correct HAC arithmetic does not guarantee95% coverage\n\nThe independent Bartlett matrix agrees with production SE to about2.78e-17. At120 sessions,nominal95% intervals cover zero only91.90%/90.35%/82.95% for rho0/.3/.8;strong-AR720-session coverage is87.65%. Uncertainty is underestimated,not simply over-conservative. Cost-negative account nulls do not replace zero-mean test-size checks.\n\nEach plotted cell has2000 independent replications;Monte Carlo intervals are pointwise descriptive. Reserved calibration constrains only the named complete-path rule,not generic HAC p-values."
            ),
        )
        blocks.append({"id": "coverage-chart", "type": "chart", "chartId": "coverage"})
        table = (
            "| 场景 | 指标 | 事件数 / 路径数 | 校正区间 | 判定 |\n|---|---|---:|---:|---|\n"
            if zh
            else "| Scenario | Estimand | Count / N | Adjusted interval | Status |\n|---|---|---:|---:|---|\n"
        )
        for name, scene in audit["scenarios"].items():
            label = (
                {
                    "linear": "线性植入",
                    "interaction": "交互植入",
                    "correlated_null": "相关性空模型",
                    "regime_null": "状态切换空模型",
                }[name]
                if zh
                else name
            )
            estimand = (
                ("检出率" if scene["kind"] == "power" else "完整路径误报率")
                if zh
                else scene["kind"]
            )
            table += f"| {label} | {estimand} | {scene['count']} / {scene['n']} | {scene['lower']:.4f}–{scene['upper']:.4f} | {scene['status']} |\n"
        text(
            "audit",
            ("## 一次性保留验收\n\n" if zh else "## Single reserved audit\n\n")
            + table
            + (
                "\n固定四场景×三检查点×双尾，总覆盖错误预算0.05。植入功效下界≥0.80；null路径误报上界≤0.05。未通过不补seed、不改变强度、成本或期限重测。"
                if zh
                else "\nFour scenes,three finite looks,two tails;total coverage error0.05. Power lower>=.80,null path-FWER upper<=.05. Failure never grants a seed/strength/cost/length replacement or second audit."
            ),
        )
        text(
            "weak",
            (
                "## 弱机制不能仅靠延长时间修复\n\n半强度线性在360/720日的双倍成本（164 bps）下平均配对净增量约−0.05/−0.56bp/日，晋级均0/8；交互720日主政策也0/8。所有压力样本均保留，不从分母排除。完整表见机器可读汇总；这些合成收益不用于推算真实本金盈利。"
                if zh
                else "## Longer observation does not rescue cost-consumed weak mechanisms\n\nHalf-strength linear mean paired increment at164bps is about−.05/−.56bp per day at360/720 sessions,with0/8 promotions;interaction720 also0/8 for the primary. All stress cases remain in evidence. These generated returns must not be annualized into real capital profit forecasts."
            ),
        )
        text(
            "limits",
            (
                "## 限制与后续\n\n合成分布、固定24只股票和已知机制族不代表真实市场。HAC覆盖限制、参考不是最优交易oracle、训练只有95日、成本和容量为冻结模型均需保留。独立核对覆盖来源绑定、事件账本、原生Trial、日收益净值及配对增量；不冒充券商级独立撮合认证。历史Court仍NOT_IDENTIFIABLE，DSR/PBO/placebo不填造。\n\n下一版先与独立审查Agent讨论。优先采用现有准入数据的极小机制诊断，预先冻结公式预算、年份、已揭示标志及成本容量；不购买数据、不用2025/2026调参、不重开旧验收。只有真实完整验证才能称可用Alpha。\n\n待回答：哪些可兑现机制带来匹配风险基准之上的净增量？弱效应如何与成本相容？可用的独立前向证据何时足够？"
                if zh
                else "## Limits and next steps\n\nKnown generated mechanisms,24 assets and fixed groups do not represent markets. Retain HAC coverage limitations,the non-optimal reference,95-session training,and model costs/capacity. Reconciliation covers source bindings,events,native Trials,daily NAV and paired increments,not broker-grade independent order reconstruction. Historical Court remains NOT_IDENTIFIABLE;DSR/PBO/placebo stay null.\n\nDiscuss the next bounded spec with an independent reviewer before implementation. Prefer a tiny mechanism diagnostic on existing admitted data with fixed expressions,years,revealed-history flag,costs and capacity. No data purchases,2025/2026 tuning or replay of old audits. Only complete real validation can establish usable Alpha.\n\nOpen questions:which mechanisms add realizable net value beyond matched risk? Can weak effects survive costs? When is independent forward evidence sufficient?"
            ),
        )
        text(
            "next-approved",
            "## 已批准的下一步\n\n核心开发与独立审查Agent已同意V12.2（Issue #204）：沿用冻结response/risk年度模型，仅新增global40/top60下的四个双成本账户，主要比较global_response−global_risk。不新增公式或拟合，不读取2025/2026。纯目标核心已测试，完整启动器、CI、精确计划及启动复审尚未完成，真实账户没有运行。"
            if zh
            else "## Agreed next step\n\nThe developer and independent reviewer agreed V12.2 (Issue #204):reuse frozen annual response/risk models for four global40/top60 accounts at two costs;primary comparison global_response minus global_risk. No new formulas,fits or2025/2026 reads. The allocation core is tested;launcher,full CI,exact plan and launch review are pending. No empirical account has run.",
        )
        artifact = {
            "surface": "report",
            "manifest": {
                "version": 1,
                "title": title,
                "surface": "report",
                "generatedAt": created,
                "blocks": blocks,
                "charts": charts,
                "sources": [source] + chart_sources,
            },
            "snapshot": {
                "version": 1,
                "status": "ready",
                "generatedAt": created,
                "datasets": datasets,
            },
            "sources": [source] + chart_sources,
        }
        write_new(output / f"artifact.{language}.json", artifact)
        (output / f"report.{language}.md").write_text(
            "\n\n".join(b["body"] for b in blocks if b["type"] == "markdown"), encoding="utf-8"
        )
    write_new(
        output / "source-notes.json",
        {
            "mode": "portable HTML in Codex runtime",
            "audience": "technical",
            "questions": "bounded capability and inference limitations",
            "structure": "technical summary; definitions; findings; methods; limits; next; open questions",
            "charts": [
                "Grouped bars compare6 mechanism-length cells by primary/diagnostic policy; two-root blue/gold; full width",
                "Grouped bars compare3 lengths x3 correlation levels,actual coverage percent; blue/gold/orange; full width",
            ],
            "table_reason": "audit power and FWER have distinct meanings/thresholds; exact count/interval table avoids misleading shared axis",
            "no_new_trials": True,
        },
    )
    print(output)


if __name__ == "__main__":
    main()
