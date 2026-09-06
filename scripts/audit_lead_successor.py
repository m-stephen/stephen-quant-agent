"""Independent accounting/SQL verification of the complete conditional60 family."""

import argparse
import json
import math
import sqlite3
from pathlib import Path

import duckdb

from stephen_quant.discovery.incremental_alpha import IncrementalHypothesis
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json
from stephen_quant.workflows.v117_incremental_epoch import inventory


def audit(folder):
    result = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    batch = result["batches"][0]
    query = (
        Path("scripts/incremental_account_audit.sql")
        .read_text(encoding="utf-8")
        .replace(
            "artifacts/incremental-alpha/epoch-001/batch-01/accounts/*.jsonl",
            (folder / "batch-01" / "accounts" / "*.jsonl").as_posix().replace("'", "''"),
        )
    )
    with duckdb.connect() as con:
        cur = con.execute(query)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    lookup = {(r["account"], r["year"], str(r["cost"])): r for r in rows}
    evidence = {}
    residual = 0.0
    for p in sorted((folder / "batch-01" / "accounts").glob("*.jsonl")):
        daily = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
        prior = 3e6
        for d in daily:
            residual = max(
                residual, abs(d["nav"] - d["cash"] - sum(x["market_value"] for x in d["positions"]))
            )
            if residual > 1e-5 or d["cash"] < -1e-7:
                raise ValueError("saved account cash/NAV mismatch")
            if not math.isclose(d["return"], d["nav"] / prior - 1, abs_tol=1e-12):
                raise ValueError("daily return mismatch")
            if not math.isclose(sum(o["total_cost"] for o in d["orders"]), d["cost"], abs_tol=1e-6):
                raise ValueError("order cost mismatch")
            prior = d["nav"]
        evidence[p.stem] = {"sha256": file_sha(p), "daily_returns": [d["return"] for d in daily]}
    expected = set()
    compact = []
    for c in batch["candidates"]:
        summary = {key: c[key] for key in ("name", "identity", "hypothesis", "assessment")}
        summary["years"] = {}
        for year, costs in c["years"].items():
            summary["years"][year] = {}
            for cost, r in costs.items():
                label = f"{year}-{c['name']}-{cost}"
                expected.add(label)
                sql = lookup[c["name"], year, cost]
                if (
                    evidence[label]["sha256"] != r["account_sha256"]
                    or evidence[label]["daily_returns"] != r["daily_returns"]
                ):
                    raise ValueError("candidate hash/daily mismatch")
                for a, b in (
                    ("net", "absolute_return"),
                    ("profit_cny", "profit_cny"),
                    ("fees_cny", "cost_cny"),
                    ("drawdown", "max_drawdown"),
                ):
                    if not math.isclose(sql[a], r[b], abs_tol=1e-6, rel_tol=1e-10):
                        raise ValueError("candidate SQL mismatch")
                summary["years"][year][cost] = {
                    key: val for key, val in r.items() if not key.startswith("daily_")
                }
        compact.append(summary)
    # Different coverage controls can legitimately have identical daily hashes.
    # Bind by policy identity/name, never by a lossy reverse hash dictionary.
    control_names = {
        item["identity"]: item["name"]
        for item in inventory(
            tuple(IncrementalHypothesis(**c["hypothesis"]) for c in batch["candidates"])
        )
        if item["kind"] != "candidate"
    }
    if set(control_names) != set(batch["controls"]):
        raise ValueError("control inventory mismatch")
    for identity, control in batch["controls"].items():
        for year, costs in control.items():
            for cost, r in costs.items():
                name = control_names[identity]
                label = f"{year}-{name}-{cost}"
                expected.add(label)
                if evidence[label]["sha256"] != r["account_sha256"]:
                    raise ValueError("control hash mismatch")
                sql = lookup[name, year, cost]
                for a, b in (
                    ("net", "net_total_return"),
                    ("fees_cny", "total_cost"),
                    ("drawdown", "max_drawdown"),
                ):
                    if not math.isclose(sql[a], r["metrics"][b], abs_tol=1e-6, rel_tol=1e-10):
                        raise ValueError("control SQL mismatch")
    if expected != set(evidence) or len(rows) != batch["account_windows"]:
        raise ValueError("missing/extra accounts")
    with sqlite3.connect(
        f"file:{(folder / 'registry.sqlite3').as_posix()}?mode=ro", uri=True
    ) as con:
        trials = con.execute("SELECT count(*) FROM trials").fetchone()[0]
    if trials != result["completed_new_trials"]:
        raise ValueError("trial count mismatch")
    summary = {
        "version": result["version"],
        "issue": 184,
        "decision": result["decision"],
        "validated_alpha": False,
        "account_windows": len(rows),
        "max_balance_residual_cny": residual,
        "independent_sql_pass": True,
        "new_trials": trials,
        "raw_global_trial_lower_bound": result["raw_global_trial_lower_bound"],
        "candidates": compact,
        "suspected_count": batch["suspected_count"],
        "winner": batch["winner"],
        "statistics": {
            k: v for k, v in batch["statistics"].items() if k not in ("split_manifest", "folds")
        },
        "placebo": batch["placebo"],
        "source_result_sha256": file_sha(folder / "RESULT.json"),
        "snapshot_sha256": result["snapshot_sha256"],
        "protected_unchanged": result["protected_unchanged"],
        "restricted_rows_read": result["restricted_rows_read"],
    }
    write_json(
        folder / "INDEPENDENT_AUDIT.json",
        {"pass": True, "rows": rows, "query": query, "max_balance_residual_cny": residual},
    )
    return summary


def reports(s, docs):
    write_json(docs / "V11_8_SUCCESSOR.summary.json", s)
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# V11.8 低换手机制测试" if zh else "# V11.8 Lower-Turnover Mechanism Test",
            "",
            "## 结论 / Technical summary",
            "",
            f"Historical economic leads: {s['suspected_count']}; validated Alpha: zero. {s['decision']}.",
            "",
            (
                "8类信号×双方向，在低波动30%股票内排序，持有60交易日，Top40/10档缓冲；"
                "下表完整保留16个候选，不只展示最好的结果。2023/2024仍为已暴露历史开发样本。"
                if zh
                else "Eight signals times two directions, ranked inside the bottom30% volatility cohort;60-session holding, Top40/buffer10. All16 candidates are retained;2023/2024 remain exposed historical development."
            ),
            "",
            "## 双倍成本结果 / Doubled-cost results",
            "",
            "| Candidate | 2023 net | 2024 net | Pooled Sharpe | Linked increment vs low-vol pp | Economic lead |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for c in s["candidates"]:
            a = c["assessment"]
            lines.append(
                f"|{c['name']}|{c['years']['2023']['2']['absolute_return']:.2%}|{c['years']['2024']['2']['absolute_return']:.2%}|{a['pooled_sharpe']:.3f}|{a['compound_increment_vs_lowvol'] * 100:+.2f}|{a['suspected_lead']}|"
            )
        lines += [
            "",
            "## 口径、统计与限制 / Definitions and statistical limits",
            "",
            (
                "各年独立300万元，双倍成本82bps往返；复合增量是年度重置账户的链接，不是连续资金。"
                "若有经济线索，必须再检验连续账户、真实成交及独立证据。"
                if zh
                else "Each year independently starts CNY3m;82bps modeled round trip. Linked annual-reset increment is not a continuous account. Any lead needs continuous-capital, brokerage-realism and independent validation."
            ),
            "",
            "```json",
            json.dumps({"statistics": s["statistics"], "placebo": s["placebo"]}, indent=2),
            "```",
            "",
            (
                "CPCV按60日持有期purge并保留embargo；DSR仍仅为当前家族离散度外推全历史Trial数的敏感性，不是已校准正式置信度。"
                "未降低任何统计门槛，不报告Alpha Court通过。"
                if zh
                else "CPCV purges the60-session holding horizon and retains embargo. DSR remains a raw-count sensitivity extrapolating current-family dispersion, not calibrated full-history confidence. No thresholds were relaxed; no Alpha Court PASS."
            ),
            "",
            "## 账本与核验 / Ledger and verification",
            "",
            f"- {s['new_trials']} new trials; cumulative raw lower bound {s['raw_global_trial_lower_bound']}.",
            f"- {s['account_windows']} independently reconciled accounts; maximum NAV residual CNY{s['max_balance_residual_cny']:.3g}.",
            "- All account hashes and SQL/Python return, cost and drawdown comparisons match.",
            "- Existing candidate/parent evidence unchanged; no2025/2026 access.",
            "",
            "## 后续 / Next step",
            "",
            (
                "先判断有没有经济线索及失败主要来源，再预声明下一有限批次。既有线索不覆盖，所有修改保留谱系并计Trial。"
                "下一步优先连续账户和期限/成交机制，不把更多公式当作独立证据。"
                if zh
                else "Inspect the complete family and its failure mechanism, then preregister the next bounded step. Keep frozen leads and count every amendment. Prioritize continuous-capital and horizon/execution mechanisms; more formulas are not independent evidence."
            ),
            "",
        ]
        with (docs / f"V11_8_SUCCESSOR.{lang}.md").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--docs", default="docs")
    args = parser.parse_args()
    result = audit(Path(args.folder))
    reports(result, Path(args.docs))
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "account_windows",
                    "suspected_count",
                    "decision",
                    "raw_global_trial_lower_bound",
                )
            }
        )
    )
