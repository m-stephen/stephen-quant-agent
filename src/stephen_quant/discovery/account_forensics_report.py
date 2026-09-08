"""Deterministic saved-evidence report projection, never a research rerun.

The launcher must supply the actual frozen external acceptance receipt. This
component does not turn a caller-provided receipt into a launch authorization.
"""

import math
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_acceptance import (
    SCORES_UNAVAILABLE,
    bind_files,
    check_fields,
    digest,
    exact,
    expected_outputs,
    read,
)
from .flow_response_launch import write
from .search_power_dsl import sha256_json

STATUS = "FORENSIC_REPORT_RENDERED_NOT_LAUNCH_ACCEPTED"
WINDOWS = ("2023", "2024", "continuous")
METRICS = {
    "opening_nav_cny": ("期初净值（元）", "Opening NAV (CNY)", "money"),
    "closing_nav_cny": ("期末净值（元）", "Closing NAV (CNY)", "money"),
    "profit_cny": ("净利润（元）", "Net profit (CNY)", "money"),
    "net_return": ("净收益率", "Net return", "percent"),
    "sharpe_252_zero_risk_free": ("夏普", "Sharpe", "number"),
    "max_drawdown": ("最大回撤", "Max drawdown", "percent"),
    "fees_cny": ("实际总费用（元）", "Actual total fees (CNY)", "money"),
    "traded_notional_cny": ("实际成交额（元）", "Executed notional (CNY)", "money"),
    "sum_one_way_turnover": ("累计单边换手（倍）", "Sum one-way turnover (x)", "number"),
    "mean_daily_one_way_turnover": ("日均单边换手", "Mean daily one-way turnover", "percent"),
    "mean_cash_nav_weight": ("平均现金/净值", "Mean cash/NAV", "percent"),
    "max_actual_positions": ("最大实际持仓数", "Max actual positions", "count"),
    "writeoff_events": ("核销事件数", "Writeoff events", "count"),
    "writeoff_cny": ("核销估值（元）", "Writeoff valuation (CNY)", "money"),
    "recovery_events": ("恢复事件数", "Recovery events", "count"),
    "recovery_valuation_cny": ("恢复估值（元）", "Recovery valuation (CNY)", "money"),
}
SOURCE_LABELS = {
    "UNKNOWN": ("未知，证据不足", "Unknown; insufficient evidence"),
    "IMPLEMENTATION_MISMATCH": ("实现不一致，需调查", "Implementation mismatch; investigate"),
    "EXPLAINED_BY_FROZEN_SOURCE": ("与冻结来源相符，非真实停牌证明", "Consistent with frozen source; not proof of suspension"),
    "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS": ("无核销/恢复事件或未恢复尾链", "No writeoff/recovery events or open stale chains"),
}
DISCLAIMER = {
    "zh": (
        "本报告没有认证可用 Alpha。所有指标是冻结账户的描述性证据，不是新实验。",
        "年度使用真实承接净值，不将每年本金重置为300万元。收益与费用直接取保存字段，不加回成本或核销。",
        "82/164 bps 是冻结往返成本契约，不是每次买入和卖出各收该费率；实际累计费用另列。",
        "单边换手为每日 0.5×实际绝对成交额/前收净值；夏普使用日净收益样本标准差、年化252日、零无风险利率。",
        "回撤包含窗口期初净值。核销与恢复是估值事件，恢复额不等于现金收款；未来恢复只用于事后核查。",
        "每次维护只刷新一个子组合，不等于整个账户持有40只股票；名单变化不等于成交换手。",
        "20单元暴露使用前一市场交易日映射，未知股票仍留在已投资市值分母，现金单列。",
        "来源相符不证明真实停牌/退市；UNKNOWN或实现不一致不得改写为来源真实性通过。",
        "DSR、PBO、placebo：未识别；评分及top60排名：未保存。缺失值不是零。",
    ),
    "en": (
        "This report certifies no usable Alpha. All metrics describe frozen saved accounts, not a new experiment.",
        "Annual windows use actual carried NAV, not a reset to CNY3m each year. Saved returns and costs are projected directly; no fee or writeoff addbacks.",
        "82/164 bps denote the frozen round-trip cost contract, not that charge on each buy and each sell. Actual cumulative fees are reported separately.",
        "One-way turnover is daily 0.5 times absolute executed notional divided by prior close NAV. Sharpe uses sample daily net-return SD,252-day annualization and zero risk-free rate.",
        "Drawdown includes opening NAV. Writeoff/recovery are valuation events, not recovery cash receipts. Later recovery is retrospective evidence only.",
        "Each maintenance event refreshes one sleeve, not a complete40-name account. Membership churn is not executed turnover.",
        "Twenty-cell exposures use the immediately prior market-session map; unknown names remain in the full invested-value denominator and cash is separate.",
        "Source consistency does not prove actual suspension/delisting. UNKNOWN and implementation mismatch must not become source-truth approval.",
        "DSR, PBO and placebo are not identifiable; raw scores and top60 ranks were not saved. Missing values are not zero.",
    ),
}


def accepted_files(root, acceptance):
    names, files = expected_outputs()
    expected = files | {"START.json", "INPUT_BINDINGS.json", "BEFORE.json", "AFTER.json",
                        "SUMMARY.json", "TERMINAL.json"}
    check_fields(acceptance, {"status": "ARTIFACT_INTEGRITY_ACCEPTED_NOT_LAUNCH_ACCEPTED",
        "account_count": 12, "output_count": 51, "numerical_reexecution": False,
        "source_truth_verified": False, "validated_alpha": False})
    for key in ("input_evidence_sha256", "producer_code_sha256", "acceptor_file_sha256"):
        digest(acceptance[key])
    exact(set(acceptance["verified_artifact_files"]), expected)
    bind_files(root, acceptance["verified_artifact_files"])
    return names


def project_report(root, acceptance):
    """Pure projection of already verified saved fields, retaining full detail rows."""
    root = Path(root)
    names = accepted_files(root, acceptance)
    summary = read(root / "SUMMARY.json")
    exact(summary["input_evidence_sha256"], acceptance["input_evidence_sha256"])
    rows, sources, exposures = [], {}, {}
    for name in names:
        account = summary["accounts"][name]
        for window in WINDOWS:
            saved = account["continuous"] if window == "continuous" else account["years"][window]
            for key, spec in METRICS.items():
                if saved[key] is None and key != "sharpe_252_zero_risk_free":
                    raise ValueError("required saved accounting metric is missing")
                format_number(saved[key], spec[2], "en")
            rows.append({"account": name, "window": window,
                **{k: saved[k] for k in ("start", "end", "sessions", *METRICS)}})
        portable = name.replace("/", "--") + ".json"
        detail = read(root / "details" / portable)
        sources[name] = {k: detail[k] for k in ("source_explanation_status", "events", "open_stale_chains")}
        exposures[name] = read(root / "exposures" / portable)
    primary = [{"cost_bps_round_trip": cost, "window": window,
                **summary["primary"][str(cost)]["windows"][window]}
               for cost in (82, 164) for window in WINDOWS]
    membership = {p: read(root / f"membership/{p}.json") for p in ("global_response", "global_risk")}
    for item in membership.values():
        exact(item["membership"]["score_status"], SCORES_UNAVAILABLE)
    values = [row["net_return_difference_pp"] for row in primary]
    direction = ("MIXED" if min(values) < 0 < max(values) else "NONPOSITIVE" if max(values) <= 0
                 else "NONNEGATIVE_DESCRIPTIVE_ONLY")
    result = {
        "version": "V12.3", "status": STATUS, "validated_alpha": False,
        "source_truth_verified": False, "new_accounts": 0, "new_fits": 0, "new_predictions": 0,
        "raw_global_trial_lower_bound": 3737, "statistics_status": "NOT_IDENTIFIABLE",
        "dsr": None, "pbo": None, "placebo_pvalue": None,
        "account_keys": names, "account_windows": rows, "primary": primary,
        "primary_direction": direction, "source_details": sources,
        "exposures": exposures, "membership": membership,
        "input_evidence_sha256": acceptance["input_evidence_sha256"],
        "acceptance_sha256": sha256_json(acceptance),
        "source_files": acceptance["verified_artifact_files"],
    }
    accepted_files(root, acceptance)
    return result


def cell(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace("|", "&#124;").replace("\n", " ")


def format_number(value, kind, language):
    if value is None:
        return "未定义" if language == "zh" else "Undefined"
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("real numeric report field required")
    if kind == "count":
        if type(value) is not int:
            raise ValueError("integer report count required")
        return str(value)
    if kind == "percent":
        return f"{value * 100:.4f}%"
    return f"{value:,.2f}" if kind == "money" else f"{value:.6f}"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *("| " + " | ".join(map(cell, r)) + " |" for r in rows)])


def render_markdown(payload, language):
    if language not in ("zh", "en"):
        raise ValueError("exact zh/en report language required")
    zh, index = language == "zh", 0 if language == "zh" else 1
    title = "冻结账户法证报告" if zh else "Frozen Account Forensics"
    direction = {
        "MIXED": ("列示净收益率差方向不一致。", "Displayed net-return differences have mixed directions."),
        "NONPOSITIVE": ("所有列示窗口的净收益率差均非正。", "No displayed window has a positive net-return difference."),
        "NONNEGATIVE_DESCRIPTIVE_ONLY": ("净收益率差呈非负描述性增量，仍非可用Alpha。", "Nonnegative descriptive net-return differences are not usable Alpha."),
    }[payload["primary_direction"]][index]
    parts = [f"# V12.3 — {title}", "## 技术摘要" if zh else "## Technical summary",
             DISCLAIMER[language][0] + " " + direction,
             "固定12个账户、两档成本、2023/2024及连续期全部保留。" if zh else
             "All12 fixed accounts, both costs,2023/2024 and the continuous window are retained.",
             "## 指标口径与限制" if zh else "## Definitions and limitations",
             "\n".join("- " + s for s in DISCLAIMER[language][1:])]
    groups = (
        ("收益与风险", "Returns and risk", tuple(METRICS)[:6]),
        ("交易、费用与持仓", "Execution, fees and holdings", tuple(METRICS)[6:12]),
        ("核销与恢复估值", "Writeoff and recovery valuations", tuple(METRICS)[12:]),
    )
    for cn, en, keys in groups:
        parts.append("## " + (cn if zh else en))
        parts.append("直接列示保存字段，不作反事实加回。" if zh else
                     "Saved fields are shown directly, without counterfactual addbacks.")
        headers = (["账户", "窗口", "交易日"] if zh else ["Account", "Window", "Sessions"]) + [METRICS[k][index] for k in keys]
        parts.append(table(headers, [[row["account"], row["window"], row["sessions"],
            *(format_number(row[k], METRICS[k][2], language) for k in keys)] for row in payload["account_windows"]]))
    parts += ["## 响应减风险：配对主比较" if zh else "## Paired primary: response minus risk",
              "比较对象是风险基线，不是市场指数。正差值也不构成统计认证。" if zh else
              "The comparator is the risk baseline, not a market index. Positive differences are not statistical certification."]
    headers = (["往返成本(bps)", "窗口", "净收益差(pp)", "利润差(元)", "配对日均差(bps)"] if zh else
               ["Round-trip cost(bps)", "Window", "Net return difference(pp)", "Profit difference(CNY)", "Paired daily mean(bps)"])
    parts.append(table(headers, [[r["cost_bps_round_trip"], r["window"],
        format_number(r["net_return_difference_pp"], "number", language),
        format_number(r["profit_difference_cny"], "money", language),
        format_number(r["paired_mean_net_return_difference_bps"], "number", language)] for r in payload["primary"]]))
    parts += ["## 来源解释与未恢复尾链" if zh else "## Source explanations and open stale tails",
              DISCLAIMER[language][7]]
    for name in payload["account_keys"]:
        item = payload["source_details"][name]
        parts += ["### " + name, SOURCE_LABELS[item["source_explanation_status"]][index]]
        headers = (["类型", "日期", "股票", "状态"] if zh else ["Type", "Date", "Instrument", "Status"])
        rows = [[e["event_type"], e["date"], e["instrument"], SOURCE_LABELS[e["source_explanation_status"]][index]]
                for e in item["events"]]
        rows += [["未恢复尾链" if zh else "Open stale tail", t["through_date"], t["instrument"],
                  SOURCE_LABELS[t["source_explanation_status"]][index]] for t in item["open_stale_chains"]]
        parts.append(table(headers, rows) if rows else ("无该类事件。" if zh else "No such events."))
        portable = name.replace("/", "--")
        parts.append(f"[{'逐事件原始证据' if zh else 'Saved event evidence'}](../details/{portable}.json)")
    parts += ["## 成员维护与股票池变化" if zh else "## Membership maintenance and support changes",
              DISCLAIMER[language][5], DISCLAIMER[language][8]]
    for p, detail in payload["membership"].items():
        parts.append("### " + p)
        support = {r["execution_date"]: r for r in detail["support"]["maintenance_events"]}
        rows = []
        for row in detail["membership"]["maintenance_events"]:
            s = support[row["execution_date"]]
            fraction = ("无前期/不适用" if zh else "No prior membership/N.A.") if row["retention_fraction"] is None else format_number(row["retention_fraction"], "percent", language)
            rows.append([row["execution_date"], row["phase"], row["selected_count"], row["entered"],
                row["exited"], fraction, len(s["previous_selected_lost_support"]),
                len(s["previous_selected_exited_still_eligible"])])
        parts.append(table(["日期", "相位", "所选", "进入", "退出", "保留比例", "失去资格", "仍可选但退出"] if zh else
                           ["Date", "Phase", "Selected", "Entered", "Exited", "Retention", "Lost support", "Eligible exits"], rows))
        parts.append(f"[{'完整成员与支持证据' if zh else 'Complete membership and support'}](../membership/{p}.json)")
    parts += ["## 20单元暴露与未知权重" if zh else "## Twenty-cell exposure and unknown weights",
              DISCLAIMER[language][6],
              "不额外计算新的风险中性统计。机器报告保留每账户逐日20单元、未知权重及现金字段，以下链接供完整核查。" if zh else
              "No new risk-neutrality statistic is calculated. The machine report retains every account's daily20-cell, unknown-weight and cash fields; complete evidence is linked below."]
    for name in payload["account_keys"]:
        parts.append(f"- [{name}](../exposures/{name.replace('/', '--')}.json)")
    parts += ["## 下一步" if zh else "## Next step",
              "若发现具体实现不一致，先冻结有限修复/复测方案并独立复审；否则停止微调该响应机制，讨论不同研究假设。不要将诊断通过或正收益称为可用Alpha。" if zh else
              "If a concrete implementation mismatch is found, preregister a bounded repair/retest for independent review. Otherwise stop retuning this response mechanism and discuss a different hypothesis. Neither diagnostic acceptance nor positive returns are usable Alpha.",
              "[完整机器报告](report.json)" if zh else "[Complete machine-readable report](report.json)"]
    return "\n\n".join(parts) + "\n"


def write_reports(root, acceptance):
    """Fixed exclusive child directory; never alter the original57 input files."""
    root = Path(root).resolve()
    payload = project_report(root, acceptance)
    output = root / "reader-report"
    output.mkdir(exist_ok=False)
    write(output / "report.json", payload)
    for language in ("zh", "en"):
        with (output / f"report.{language}.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_markdown(payload, language))
    accepted_files(root, acceptance)
    result = _check_reports(root, acceptance)
    write(output / "RENDERED.json", result)
    return result


def verify_reports(root, acceptance):
    """Exact saved-field projection and deterministic text comparison, no new metrics."""
    result = _check_reports(root, acceptance)
    exact(read(Path(root) / "reader-report/RENDERED.json"), result)
    return result


def _check_reports(root, acceptance):
    root = Path(root).resolve()
    payload = project_report(root, acceptance)
    output = root / "reader-report"
    if output.resolve().parent != root:
        raise ValueError("reader-report directory must remain inside the frozen report")
    for rel in ("report.json", "report.zh.md", "report.en.md", "RENDERED.json"):
        if (output / rel).resolve().parent != output.resolve():
            raise ValueError("reader-report artifact path must not escape")
    exact(read(output / "report.json"), payload)
    for language in ("zh", "en"):
        exact((output / f"report.{language}.md").read_text(encoding="utf-8"), render_markdown(payload, language))
    files = {rel: file_sha(output / rel) for rel in ("report.json", "report.zh.md", "report.en.md")}
    accepted_files(root, acceptance)
    return {"status": STATUS, "files": files, "acceptance_sha256": sha256_json(acceptance),
            "report_payload_sha256": sha256_json(payload), "validated_alpha": False,
            "new_accounts": 0, "new_fits": 0, "new_predictions": 0}
