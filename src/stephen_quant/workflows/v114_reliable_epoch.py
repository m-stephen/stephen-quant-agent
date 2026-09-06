"""Issue #180: one bounded repair/retest with immutable inputs and honest evidence."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from uuid import uuid4

from stephen_quant.discovery.reliability_calibration import family_placebo, run_calibration
from stephen_quant.discovery.reliable_research import (
    RELIABLE_VERSION,
    candidate_pack,
    fit_prefix_model,
    metric_bundle,
    run_candidate,
    temporal_selection,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import (
    daily_evidence,
    file_sha,
    freeze_inputs,
    load_frozen_days,
)


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def runtime_code_hash():
    root = Path(__file__).resolve().parents[1]
    files = (
        "discovery/reliable_research.py",
        "discovery/reliability_calibration.py",
        "qmt/reliable_panel.py",
        "workflows/v114_reliable_epoch.py",
        "baseline/stateful.py",
    )
    return sha256_json({name: file_sha(root / name) for name in files})


def protected_digest(paths):
    files = {}
    for value in paths:
        path = Path(value).resolve()
        if not path.exists():
            raise ValueError("configured protected state does not exist")
        selected = sorted(path.rglob("*.json")) if path.is_dir() else [path]
        for item in selected:
            files[str(item)] = file_sha(item)
    return sha256_json(files), len(files)


def calibrate(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    print(json.dumps({"stage": "calibration", "workers": 8}), flush=True)
    eight = run_calibration(workers=8)
    write_json(output / "eight.json", eight)
    print(json.dumps({"stage": "calibration", "workers": 1}), flush=True)
    one = run_calibration(workers=1)
    write_json(output / "one.json", one)
    passed = (
        eight["pass"]
        and one["pass"]
        and eight["content_sha256"] == one["content_sha256"]
        and len(eight["actual_worker_pids"]) > 1
        and len(one["actual_worker_pids"]) == 1
    )
    evidence = {
        "pass": passed,
        "code_sha256": runtime_code_hash(),
        "one_file_sha256": file_sha(output / "one.json"),
        "eight_file_sha256": file_sha(output / "eight.json"),
        "parity": eight["content_sha256"] == one["content_sha256"],
        "planted_recovered": eight["planted_recovered"],
        "planted_detected": eight["planted_detected"],
        "null_fwer": eight["null_fwer"],
        "null_wilson95": eight["null_wilson95"],
        "scope": eight["scope"],
        "not_covered": eight["not_covered"],
        "statistical_gate_planted_pass": eight["statistical_gate_planted_pass"],
        "statistical_gate_null_pass": eight["statistical_gate_null_pass"],
        "statistical_scope": eight["statistical_scope"],
    }
    write_json(output / "audit.json", evidence)
    return evidence


def validate_calibration(folder):
    evidence = json.loads((folder / "audit.json").read_text(encoding="utf-8"))
    if (
        not evidence["pass"]
        or evidence["code_sha256"] != runtime_code_hash()
        or evidence["one_file_sha256"] != file_sha(folder / "one.json")
        or evidence["eight_file_sha256"] != file_sha(folder / "eight.json")
    ):
        raise ValueError("calibration failed, changed, or refers to different runtime code")
    return evidence


def overlap_evidence(series, holding_sets):
    """All pairwise comparisons, not a post-hoc filter that hides duplicate trials."""
    pairs = []
    names = sorted(series)
    for i, left in enumerate(names):
        x = series[left]
        mx = mean(x)
        for right in names[i + 1 :]:
            y = series[right]
            my = mean(y)
            denominator = math.sqrt(sum((v - mx) ** 2 for v in x) * sum((v - my) ** 2 for v in y))
            correlation = (
                sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / denominator
                if denominator
                else None
            )
            daily = []
            for a, b in zip(holding_sets[left], holding_sets[right], strict=True):
                union = a | b
                if union:
                    daily.append(len(a & b) / len(union))
            pairs.append(
                {
                    "left": left,
                    "right": right,
                    "active_correlation": correlation,
                    "mean_actual_holdings_jaccard": mean(daily) if daily else None,
                    "near_duplicate": correlation is not None and correlation >= 0.85,
                }
            )
    return {"pairs": pairs, "raw_trial_count_reduced": False}


def replay_epoch(folder: Path):
    """Exact frozen replay, not a fresh experiment or permission to change the winner."""
    report = json.loads((folder / "RESULT.json").read_text(encoding="utf-8"))
    if runtime_code_hash() != report["spec"]["runtime_code_sha256"]:
        raise ValueError("replay requires the exact original runtime code")
    if report["spec"]["candidates"] != json.loads(
        json.dumps([asdict(c) for c in candidate_pack()])
    ):
        raise ValueError("replay candidate identity changed")
    registry_before = file_sha(folder / "registry.sqlite3")
    operation = folder / "replays" / str(uuid4())
    write_json(
        operation / "STARTED.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": "EXACT_FROZEN_REPLAY",
            "inferential_trial_delta": 0,
            "source_result_sha256": file_sha(folder / "RESULT.json"),
        },
    )
    try:
        days, _ = load_frozen_days(folder / "inputs")
        models = report["models"]
        references = {item["identity"]: item for item in report["candidates"]}
        compared = 0
        for stage, year in (("inner", "2023"), ("outer", "2024")):
            window = tuple(d for d in days if d.date.startswith(year))
            benchmarks = {}
            for c in candidate_pack():
                for cost in (1, 2):
                    deps = tuple(sorted(set(c.fields + ((c.gate_field,) if c.gate_field else ()))))
                    key = (deps, c.horizon, cost)
                    if key not in benchmarks:
                        benchmarks[key] = run_candidate(
                            window, c, models.get(c.identity), cost, benchmark=True
                        )[0]
                    account, _, targets_sha = run_candidate(window, c, models.get(c.identity), cost)
                    metrics = metric_bundle(account, benchmarks[key])
                    metrics["targets_sha256"] = targets_sha
                    if metrics != references[c.identity][stage][str(cost)]:
                        raise ValueError("exact replay metrics or targets differ")
                    compared += 1
                print(
                    json.dumps({"stage": "replay", "year": year, "candidate": c.name}), flush=True
                )
        unchanged = file_sha(folder / "registry.sqlite3") == registry_before
        if not unchanged:
            raise ValueError("exact replay modified trial registry")
        result = {
            "pass": True,
            "account_windows_compared": compared,
            "inferential_trial_delta": 0,
            "registry_unchanged": unchanged,
            "runtime_code_sha256": runtime_code_hash(),
        }
        write_json(operation / "RESULT.json", result)
        return result
    except Exception as exc:
        write_json(operation / "FAILED.json", {"error": str(exc), "inferential_trial_delta": 0})
        raise


def write_reports(output, report):
    for lang in ("zh", "en"):
        zh = lang == "zh"
        lines = [
            "# 可信研究修复与首轮复测" if zh else "# Reliable research repair and bounded retest",
            "",
            "## 结论" if zh else "## Decision",
            "",
            f"`{report['decision']}`",
            "",
            (
                "本轮使用2022训练、2023候选选择、2024受污染诊断。工程通过不代表可部署Alpha。"
                if zh
                else "Training:2022; selector development:2023; contaminated diagnostic:2024. "
                + "Engineering readiness is not deployable Alpha."
            ),
            "",
            "## 口径与执行" if zh else "## Definitions and execution",
            "",
            (
                "每个窗口独立从300万元开始；40只等权目标、10档缓冲，未触发留现金。"
                "41/82bps为往返费用；逐日盯市、参与率5%，保留停牌/拒单/减记。"
                "基准是在同日满足相同字段覆盖的股票等权组合，采用同一执行与成本，非沪深300。"
                if zh
                else "Each window starts with CNY3m. Top40, buffer10, inactive positions remain cash. "
                "Round-trip costs41/82bps, daily marking and5% participation. The benchmark is an "
                "equal-weight matched-availability portfolio with identical execution and costs, not CSI300."
            ),
            "",
            "## 冻结选择与统计" if zh else "## Frozen selection and statistics",
            "",
            f"- 2023 winner: `{report['winner_name']}`",
            f"- DSR: {report['selection']['dsr']:.6f}; PBO: {report['selection']['pbo']}",
            f"- Family placebo: {report['placebo']['p_value']:.6f}",
            "- DSR is a raw-count sensitivity, not calibrated full-history confidence; historical aligned Sharpe matrix is unavailable.",
            (
                f"- Daily/effective observations: {report['selection']['daily_observations']} / "
                f"{report['selection']['effective_observations']}"
            ),
            "",
            "## 逐候选账户结果（双倍成本）" if zh else "## Candidate accounts, double costs",
            "",
            "| Candidate | 2023 account | 2023 active pp | 2024 account | 2024 active pp | 2024 profit CNY |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for item in report["candidates"]:
            a, b = item["inner"]["2"], item["outer"]["2"]
            lines.append(
                f"| {item['name']} | {a['absolute_return']:.2%} | "
                f"{a['excess_percentage_points'] * 100:.2f} | {b['absolute_return']:.2%} | "
                f"{b['excess_percentage_points'] * 100:.2f} | {b['profit_cny']:,.2f} |"
            )
        lines += [
            "",
            "## 限制与下一步" if zh else "## Limitations and next step",
            "",
            (
                "数据为供应商历史修订版本；行业历史不用于本轮。竞价延迟一日；缺失20日保守减记，"
                "成交使用调整后价格/分数股而非券商逐笔和整手撮合。2025–2026已在历史研究中暴露，"
                "本轮继续限制访问；不能再次包装为全新留出。学习模型只在2022前缀训练，"
                "CPCV验证的是冻结预测器之间的选择，不检验模型在不同训练窗口下的重新拟合。"
                "本轮没有调用外部LLM，已实现结构化提案接口。后续以本轮失败归因和真正新增观测为依据。"
                if zh
                else "Vendor-revised history; industry metadata is unused. Auction signals lag one session. "
                "Missing holdings receive conservative20-session writeoffs. Adjusted prices/fractional shares "
                "approximate fills. Previously exposed2025–2026 remains restricted, not pristine holdout. "
                "Models fit only the2022 prefix; CPCV assesses selection among frozen predictors, not repeated "
                "model fitting across training windows. No external LLM call occurred; structured proposal "
                "validation is implemented. Use failure attribution and new observations for follow-up."
            ),
            "",
        ]
        (output / f"RESULT.{lang}.md").write_text("\n".join(lines), encoding="utf-8")


def run_reliable_epoch(config_path: str, *, code_version: str):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    output = Path(config["output_dir"]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    candidates = candidate_pack()
    spec = {
        "version": RELIABLE_VERSION,
        "candidates": [asdict(c) for c in candidates],
        "training_prefix": ["2022-01-01", "2022-12-31"],
        "selection": ["2023-01-01", "2023-12-31"],
        "diagnostic": ["2024-01-01", "2024-12-31"],
        "historical_exposure": "2022-2026 previously exposed;2025-2026 restricted this run",
        "account_capital": 3_000_000,
        "cost_variants": [1, 2],
        "raw_debt_before": 2770,
        "selector": "mean net daily active return, lower volatility, canonical identity",
        "model_fit": "common2022 training prefix in every selection fold; frozen afterwards",
        "maximum_predictor_identities": 24,
        "maximum_cost_variant_trials": 48,
        "code_version": code_version,
        "runtime_code_sha256": runtime_code_hash(),
        "stop": "one epoch, no threshold changes or automatic successor",
    }
    write_json(output / "frozen_spec.json", spec)
    protected = config.get("protected_paths", [])
    before, count = protected_digest(protected)
    if not count:
        raise ValueError(
            "configure the existing frozen-state artifacts for before/after verification"
        )
    calibration_folder = Path(config["calibration_dir"])
    if not calibration_folder.exists():
        calibrate(calibration_folder)
    calibration = validate_calibration(calibration_folder)
    # A first-read reservation is recorded before copying any source price bytes.
    write_json(
        output / "first_read_reservations.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "spec_sha256": sha256_json(spec),
            "trials": [
                {"identity": c.identity, "cost": cost, "status": "RESERVED_BEFORE_SOURCE_READ"}
                for c in candidates
                for cost in (1, 2)
            ],
        },
    )
    try:
        snapshot = freeze_inputs(Path(config["warehouse_root"]), output / "inputs")
        registry = ExperimentRegistry(output / "registry.sqlite3")
        snapshot_id = registry.register_snapshot(
            build_composite_snapshot_manifest({"bounded_inputs": snapshot["snapshot_sha256"]}),
            vendor_version=RELIABLE_VERSION,
        )
        experiment = registry.create_experiment_deterministic(
            ExperimentSpec(
                "reliable_bounded_epoch",
                "repair and bounded mechanism/model comparison",
                snapshot_id,
                code_version,
                json.dumps(spec),
            ),
            sha256_json(spec),
        )
        trials = {}
        for c in candidates:
            for cost in (1, 2):
                trials[(c.identity, cost)] = registry.create_trial_deterministic(
                    TrialSpec(
                        experiment,
                        c.name,
                        c.identity,
                        json.dumps({"candidate": asdict(c), "cost": cost}),
                        114,
                        "2022-01-01",
                        "2022-12-31",
                        "2023-01-01",
                        "2023-12-31",
                        "2024-01-01",
                        "2024-12-31",
                    ),
                    f"{c.identity}:{cost}",
                )[0]
        days, quality = load_frozen_days(output / "inputs")
        training = tuple(d for d in days if d.date < "2023-01-01")
        models = {
            c.identity: fit_prefix_model(training, c)
            for c in candidates
            if c.operator in ("linear", "stump")
        }
        write_json(output / "frozen_models.json", models)
        results = {
            c.identity: {
                "name": c.name,
                "identity": c.identity,
                "parent": c.parent,
                "inner": {},
                "outer": {},
            }
            for c in candidates
        }
        selection = placebo = None
        for stage, year in (("inner", "2023"), ("outer", "2024")):
            window = tuple(d for d in days if d.date.startswith(year))
            series = {}
            holding_sets = {}
            benchmarks = {}
            for c in candidates:
                model = models.get(c.identity)
                for cost in (1, 2):
                    deps = tuple(sorted(set(c.fields + ((c.gate_field,) if c.gate_field else ()))))
                    key = (deps, c.horizon, cost)
                    if key not in benchmarks:
                        benchmarks[key] = run_candidate(window, c, model, cost, benchmark=True)[0]
                    account, coverage, targets_sha = run_candidate(window, c, model, cost)
                    metrics = metric_bundle(account, benchmarks[key])
                    metrics["targets_sha256"] = targets_sha
                    results[c.identity][stage][str(cost)] = metrics
                    details = output / "accounts" / f"{stage}-{c.name}-{cost}.jsonl"
                    details.parent.mkdir(parents=True, exist_ok=True)
                    with details.open("x", encoding="utf-8") as stream:
                        for record in daily_evidence(account):
                            stream.write(json.dumps(record, separators=(",", ":")) + "\n")
                    write_json(output / "coverage" / f"{stage}-{c.name}-{cost}.json", coverage)
                    if cost == 2:
                        series[c.identity] = metrics["daily_active"]
                        holding_sets[c.identity] = [
                            {m.instrument for m in p.marks if m.market_value > 0}
                            for p in account.periods
                        ]
                print(
                    json.dumps({"stage": stage, "candidate": c.name, "completed": True}), flush=True
                )
            write_json(output / f"{stage}_overlap.json", overlap_evidence(series, holding_sets))
            if stage == "inner":
                selection = temporal_selection([d.date for d in window], series, 2770 + len(trials))
                placebo = family_placebo(series)
                write_json(output / "inner_selection_frozen.json", selection)
                write_json(output / "inner_placebo.json", placebo)
        for c in candidates:
            for cost in (1, 2):
                registry.record_trial_result(
                    trials[c.identity, cost],
                    json.dumps(
                        {
                            "inner": results[c.identity]["inner"][str(cost)],
                            "outer": results[c.identity]["outer"][str(cost)],
                        },
                        sort_keys=True,
                    ),
                )
        after, after_count = protected_digest(protected)
        unchanged = before == after and count == after_count
        if not unchanged:
            raise ValueError("protected state changed during the epoch")
        chosen = results[selection["winner"]]
        stat_pass = (
            selection["dsr"] >= 0.95
            and selection["pbo"] is not None
            and selection["pbo"] <= 0.05
            and placebo["p_value"] <= 0.05
        )
        attractive = (
            chosen["outer"]["2"]["excess_percentage_points"] > 0
            and chosen["outer"]["2"]["active_sharpe"] >= 0.5
            and chosen["outer"]["2"]["max_drawdown"] >= -0.25
        )
        report = {
            "version": RELIABLE_VERSION,
            "issue": 180,
            "decision": "FROZEN_DIAGNOSTIC_CANDIDATE"
            if stat_pass and attractive
            else "ENGINEERING_PASS_NO_VALIDATED_ALPHA",
            "engineering_pass": True,
            "validated_alpha": False,
            "research_lead_economic_diagnostic": attractive,
            "statistics_pass_under_stated_sensitivity": stat_pass,
            "winner_name": chosen["name"],
            "selection": selection,
            "placebo": placebo,
            "calibration": calibration,
            "candidates": list(results.values()),
            "models": models,
            "runtime_quality": quality,
            "source_snapshot": snapshot,
            "raw_global_trial_lower_bound": 2770 + len(trials),
            "new_trials": len(trials),
            "protected_state": {
                "files": count,
                "before": before,
                "after": after,
                "unchanged": unchanged,
            },
            "old_results": "preserved as legacy diagnostics, not restated as absolute P&L",
            "external_llm_calls": 0,
            "forced_stop": True,
            "spec": spec,
        }
        write_json(output / "RESULT.json", report)
        write_reports(output, report)
        print(
            json.dumps(
                {
                    "result": str(output / "RESULT.json"),
                    "decision": report["decision"],
                    "winner": chosen["name"],
                }
            ),
            flush=True,
        )
        return report
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {
                "exception": type(exc).__name__,
                "message": str(exc),
                "reservations_preserved": True,
                "no_automatic_retry": True,
            },
        )
        raise


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--calibrate")
    parser.add_argument("--replay")
    parser.add_argument(
        "--code-version", default=os.environ.get("RESEARCH_CODE_VERSION", "unknown")
    )
    args = parser.parse_args()
    if args.replay:
        print(json.dumps(replay_epoch(Path(args.replay))))
    elif args.calibrate:
        print(json.dumps(calibrate(Path(args.calibrate))))
    elif args.config:
        run_reliable_epoch(args.config, code_version=args.code_version)
    else:
        parser.error("--config, --calibrate or --replay is required")


if __name__ == "__main__":
    main()
