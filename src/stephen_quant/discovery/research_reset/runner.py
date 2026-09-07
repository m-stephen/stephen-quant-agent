"""Once-only reserved synthetic audit, deterministic development runs and evidence."""

from __future__ import annotations

import json
import secrets
import subprocess
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest

from .accounts import execute_four_accounts, oracle_reference
from .contracts import ResetSpec, canonical, code_manifest, digest, evidence_state, runtime_manifest
from .search import discover
from .sources import generate, generator_contract
from .statistics import calibration_decision


def now():
    return datetime.now(timezone.utc).isoformat()


def workspace_root():
    return Path(__file__).resolve().parents[4]


def control_root():
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=workspace_root(),
        text=True,
    ).strip()
    return Path(common).resolve().parent / "artifacts" / "v12-reset-control"


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical(value) + "\n")
    return digest(value)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(
            handle,
            object_pairs_hook=_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )


def prepare_plan(mode="development", *, development_paths=4):
    if mode not in ("development", "audit"):
        raise ValueError("only development or reserved synthetic audit is implemented")
    if type(development_paths) is not int or not 1 <= development_paths <= 8:
        raise ValueError("development paths bounded at 1..8 per scenario")
    suite = "v12.0-reserved-audit-1" if mode == "audit" else "development-" + uuid.uuid4().hex
    root = control_root()
    if (root / "plans" / f"{suite}.json").exists():
        raise FileExistsError("reserved suite already prepared; use its immutable existing plan")
    payload = {
        "schema": "v12-reset-plan-1",
        "suite_id": suite,
        "mode": mode,
        "created_at": now(),
        "spec": ResetSpec().payload(),
        "code": code_manifest(),
        "runtime": runtime_manifest(),
        "source_generator": generator_contract(),
        "master_seed": secrets.randbits(62) if mode == "audit" else 20260908,
        "paths_per_scenario": 500 if mode == "audit" else development_paths,
        "authorization": "USER_APPROVED_M0_M2_SYNTHETIC_ONLY",
        "real_label_authorized": False,
        "blindness": "held-out seeds; known scenario families",
    }
    envelope = {"plan": payload, "sha256": digest(payload)}
    path = root / "plans" / f"{suite}.json"
    write_new(path, envelope)
    return path, envelope


def verify_plan(path):
    envelope = read_json(path)
    if set(envelope) != {"plan", "sha256"} or digest(envelope["plan"]) != envelope["sha256"]:
        raise ValueError("plan hash/schema mismatch")
    plan = envelope["plan"]
    expected_keys = {
        "schema",
        "suite_id",
        "mode",
        "created_at",
        "spec",
        "code",
        "runtime",
        "source_generator",
        "master_seed",
        "paths_per_scenario",
        "authorization",
        "real_label_authorized",
        "blindness",
    }
    if set(plan) != expected_keys or plan["schema"] != "v12-reset-plan-1":
        raise ValueError("plan has unauthorized extensions")
    if plan["mode"] not in ("audit", "development") or plan["real_label_authorized"] is not False:
        raise ValueError("real labels are not authorized")
    if plan["authorization"] != "USER_APPROVED_M0_M2_SYNTHETIC_ONLY":
        raise ValueError("wrong operation scope")
    if plan["runtime"] != runtime_manifest():
        raise ValueError("numerical runtime changed")
    suite = plan["suite_id"]
    if (
        not isinstance(suite, str)
        or not suite
        or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-." for c in suite)
    ):
        raise ValueError("unsafe suite identity")
    expected = control_root() / "plans" / f"{suite}.json"
    if Path(path).resolve() != expected.resolve():
        raise ValueError("plan must be the shared, immutable prepared artifact")
    if plan["code"] != code_manifest() or digest(plan["source_generator"]) != digest(
        generator_contract()
    ):
        raise ValueError("decision pipeline changed; previous suite cannot certify it")
    if type(plan["master_seed"]) is not int or not 0 <= plan["master_seed"] < 2**63:
        raise ValueError("invalid master seed")
    n = plan["paths_per_scenario"]
    if (
        type(n) is not int
        or (plan["mode"] == "audit" and (suite != "v12.0-reserved-audit-1" or n != 500))
        or (
            plan["mode"] == "development"
            and (not suite.startswith("development-") or not 1 <= n <= 8)
        )
    ):
        raise ValueError("suite/path budget mismatch")
    return plan, ResetSpec.from_dict(plan["spec"]), envelope["sha256"]


class Recorder:
    def __init__(self, registry, directory, panel, plan_hash, spec, seed, path_id):
        self.registry, self.directory, self.spec, self.seed = registry, directory, spec, seed
        self.dates = panel.dates
        self.snapshot = panel.fingerprint()
        self.events = []
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest(
                {"generated_source": self.snapshot, "plan": plan_hash}
            )
        )
        self.eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "V12 synthetic path",
                "generated source only; not empirical Alpha",
                sid,
                digest(code_manifest()),
                canonical(spec.payload()),
                "synthetic",
            ),
            digest({"path_id": path_id, "source": self.snapshot, "plan": plan_hash}),
        )
        self.path_id = path_id
        self.ids = []
        self.policy_ids = set()
        self.counts = {
            "label_structures": 0,
            "account_runs": 0,
            "oracle_account_runs": 0,
            "fits": 0,
        }

    def __call__(self, event, candidate, value):
        if event in ("before_label_read", "before_account", "before_oracle_account"):
            if event == "before_label_read":
                role, cost, stage = "risk_signal", 82, "training_proxy"
                self.counts["label_structures"] += 1
            else:
                role, cost, stage = value["role"], value["cost"], "native_evaluation"
                if event == "before_oracle_account":
                    stage = "oracle_diagnostic"
                    self.counts["oracle_account_runs"] += 1
                else:
                    self.counts["account_runs"] += 1
            policy_id = candidate.identity(cost, role)
            self.policy_ids.add(policy_id)
            identity = digest(
                {"policy": policy_id, "stage": stage, "source": self.snapshot, "path": self.path_id}
            )
            params = {
                "candidate": asdict(candidate),
                "policy_id": policy_id,
                "stage": stage,
                "role": role,
                "cost": cost,
                "source_sha256": self.snapshot,
                "synthetic_only": True,
                "empirical_trial_delta": 0,
            }
            tid, _ = self.registry.create_trial_deterministic(
                TrialSpec(
                    self.eid,
                    "v12-reset-synthetic",
                    candidate.expression,
                    canonical(params),
                    self.seed,
                    self.dates[1],
                    self.dates[self.spec.train_end],
                    self.dates[self.spec.evaluation_start],
                    self.dates[-1],
                    "",
                    "",
                ),
                identity,
            )
            self.ids.append(tid)
        item = {
            "event": event,
            "candidate": asdict(candidate),
            "structure_id": candidate.structure_id,
            "value": value,
        }
        self.events.append(item)
        # Preserve reservations and failures even if source/search/account work crashes.
        with (self.directory / "ledger.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(canonical(item) + "\n")


def run_path(seed, scenario, spec, output, plan_hash, registry):
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    panel, oracle = generate(seed, scenario, spec)
    snapshot = panel.fingerprint()
    write_new(
        output / "SOURCE.json",
        {
            "seed": seed,
            "generator": generator_contract(),
            "snapshot_sha256": snapshot,
            "source_kind": panel.source_kind,
        },
    )
    recorder = Recorder(registry, output, panel, plan_hash, spec, seed, output.name)
    winner, ranks, support, ranked = discover(panel, spec, recorder)
    result = execute_four_accounts(panel, winner, ranks, support, spec, recorder)
    if panel.fingerprint() != snapshot:
        raise ValueError("source mutation during experiment")
    # Oracle access occurs only after selection and account decisions have completed.
    result["oracle_reference"] = oracle_reference(
        panel, oracle, winner, ranks, support, spec, result, recorder
    )
    exact = winner.expression == oracle.expression and winner.direction == oracle.direction
    from .search import scores

    predicted = scores(winner, ranks)[spec.evaluation_start - 1 : -1].ravel()
    truth = oracle.signal[spec.evaluation_start - 1 : -1].ravel()
    correlation = float(np.corrcoef(predicted, truth)[0, 1]) if oracle.expression else None
    semantic = bool(exact or (correlation is not None and correlation >= 0.60))
    result.update(
        {
            "scenario": scenario,
            "seed": seed,
            "snapshot_sha256": snapshot,
            "winner": asdict(winner),
            "winner_structure_id": winner.structure_id,
            "winner_expression": winner.expression,
            "recovery": {
                "exact_expression_direction": exact,
                "semantic": semantic,
                "oracle_rank_proxy_correlation": correlation,
                "horizon_recovery": "NOT_APPLICABLE_PERSISTENT_DAILY_MECHANISM",
                "top3_expression": any(
                    c.expression == oracle.expression and c.direction == oracle.direction
                    for c, _ in ranked[:3]
                ),
            },
            "counts": recorder.counts
            | {
                "native_trial_records": len(recorder.ids),
                "unique_policy_identities": len(recorder.policy_ids),
                "physical_path_runs": 1,
                "empirical_trials": 0,
            },
            "native_trial_ids": recorder.ids,
            "ledger_sha256": digest(recorder.events),
        }
    )
    # Counts, account daily data and candidate outcome are immutable numerical evidence.
    result_hash = write_new(output / "RESULT.json", result)
    write_new(output / "RESOURCE.json", {"elapsed_seconds": time.monotonic() - started})
    return result, result_hash


def run_plan(plan_path, output, *, progress=None):
    plan, spec, plan_hash = verify_plan(plan_path)
    output = Path(output).resolve()
    allowed = (workspace_root() / "artifacts").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        raise ValueError("new result directory must be within this workspace's artifacts")
    if output.exists():
        raise FileExistsError("output exists; no overwrite or replay")
    claim = control_root() / "claims" / (plan["suite_id"] + ".json")
    write_new(
        claim,
        {
            "plan_sha256": plan_hash,
            "consumed_at": now(),
            "output": str(output),
            "state": "CONSUMED",
            "empirical_trial_delta": 0,
        },
    )
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "PLAN.json", {"plan": plan, "sha256": plan_hash})
    registry = ExperimentRegistry(output / "registry.sqlite3")
    registry.initialize()
    scenes, totals, completed, status = {}, {}, [], "NOT_TESTED"
    try:
        for scenario in spec.scenarios:
            count, observations, receipt = 0, 0, None
            for i in range(plan["paths_per_scenario"]):
                if time.monotonic() - started > spec.max_seconds:
                    status = "INCONCLUSIVE"
                    break
                if code_manifest() != plan["code"]:
                    raise ValueError("pipeline changed during reserved audit")
                seed = int(
                    digest({"master": plan["master_seed"], "scenario": scenario, "index": i})[:15],
                    16,
                )
                path_id = f"{scenario}-{i:04d}"
                result, h = run_path(
                    seed, scenario, spec, output / "paths" / path_id, plan_hash, registry
                )
                for key, value in result["counts"].items():
                    totals[key] = totals.get(key, 0) + value
                event = bool(result["promoted"])
                if not scenario.endswith("null"):
                    event = event and result["recovery"]["semantic"]
                count += event
                observations += 1
                completed.append({"path": path_id, "result_sha256": h})
                if progress:
                    progress(
                        {
                            "scenario": scenario,
                            "n": observations,
                            "events": count,
                            "elapsed_seconds": round(time.monotonic() - started, 1),
                        }
                    )
                if plan["mode"] == "audit" and observations in spec.looks:
                    receipt = calibration_decision(
                        count,
                        observations,
                        kind="fwer" if scenario.endswith("null") else "power",
                        spec=spec,
                    )
                    write_new(output / "looks" / f"{scenario}-{observations}.json", receipt)
                    if receipt["status"] != "CONTINUE":
                        break
            if plan["mode"] == "development":
                receipt = {
                    "status": "NOT_TESTED",
                    "n": observations,
                    "count": count,
                    "reason": "development cases are not reserved readiness evidence",
                }
            elif receipt is None or receipt["status"] == "CONTINUE":
                receipt = {
                    "status": "INCONCLUSIVE",
                    "n": observations,
                    "count": count,
                    "reason": "resource limit before a conclusive frozen look",
                }
            scenes[scenario] = receipt
            if status == "INCONCLUSIVE":
                break
        if plan["mode"] == "audit" and status != "INCONCLUSIVE":
            states = [s["status"] for s in scenes.values()]
            status = (
                "PASS"
                if all(s == "PASS" for s in states) and len(states) == 4
                else ("FAIL" if "FAIL" in states else "INCONCLUSIVE")
            )
        if registry.counts()["trials"] != totals.get("native_trial_records", 0):
            raise ValueError("native trial ledger does not reconcile with all completed paths")
    except BaseException as exc:
        terminal = evidence_state("ENGINEERING_FAIL") | {
            "plan_sha256": plan_hash,
            "completed_paths": completed,
            "counts": totals,
            "native_counts_including_incomplete_paths": registry.counts(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "ended_at": now(),
            "warning": "incomplete paths are not negative controls; no automatic retry",
        }
        write_new(output / "TERMINAL.json", terminal)
        raise
    result = evidence_state(status) | {
        "plan_sha256": plan_hash,
        "pipeline_sha256": digest(plan["code"]),
        "mode": plan["mode"],
        "scenarios": scenes,
        "counts": totals,
        "completed_paths": completed,
        "native_counts": registry.counts(),
        "scope_claim": "finite typed search and native economic gate under named synthetic distributions",
        "statistical_certification": "not market Alpha and not the full historical Court",
    }
    result_hash = write_new(output / "RESULT.json", result)
    write_new(
        output / "TERMINAL.json",
        {
            "status": "COMPLETE",
            "result_sha256": result_hash,
            "ended_at": now(),
            "elapsed_seconds": time.monotonic() - started,
        },
    )
    write_reports(output, result)
    return result


def write_reports(output, result):
    for language in ("zh", "en"):
        zh = language == "zh"
        lines = [
            "# V12.0 合成校准结果" if zh else "# V12.0 Synthetic Calibration Results",
            "",
            ("## 结论" if zh else "## Conclusion"),
            "",
            (
                f"校准状态：**{result['calibration']}**；运行模式：{result['mode']}。"
                if zh
                else f"Calibration: **{result['calibration']}**. Mode: {result['mode']}."
            ),
            "",
            (
                "这是合成数据上的有限搜索校准，不是市场收益，不代表发现 Alpha。"
                if zh
                else "This is a bounded synthetic search calibration, not market returns or Alpha."
            ),
            "",
            "## 范围" if zh else "## Scope",
            "",
            (
                "全部来源为程序生成：24 只虚构股票、220 个交易日；训练至第 95 日，评估为第 100–219 日（从 0 编号）。"
                if zh
                else "Generated sources only; 24 fictional assets; 220 sessions; training <=95, evaluation100..219 (zero-based)."
            ),
            (
                "资金 300 万元；往返成本 0/82/164 基点；六个风险分组；5/10 日维护。"
                if zh
                else "CNY3m, 0/82/164 roundtrip bps; six risk groups; 5/10-session maintenance."
            ),
            "",
            "## 结果" if zh else "## Results",
            "",
        ]
        for name, scene in result["scenarios"].items():
            lines.append(
                f"- {name}: {scene['status']}; {scene['count']}/{scene['n']} "
                + ("条路径。" if zh else "paths.")
            )
            if "lower" in scene:
                lines.append(
                    ("  同时覆盖校正区间 " if zh else "  Simultaneous-adjusted interval ")
                    + f"[{scene['lower']:.6f}, {scene['upper']:.6f}]."
                )
        lines += [
            "",
            "## 计数" if zh else "## Accounting",
            "",
            canonical(result["counts"]),
            "",
            (
                "历史 raw attempt 仍为 3,733；本轮新增真实市场试验 0。此处原生 Trial 全部标记为合成试验，不冒充独立推断次数。"
                if zh
                else "Historical raw attempts remain3733; new empirical attempts0. Native records here are SYNTHETIC, not independent inferential trials."
            ),
            "",
            "## 方法与限制" if zh else "## Method and limits",
            "",
            (
                "四场景 × 三检查点 × 双尾：精确二项边界，总校准覆盖错误预算 0.05。"
                if zh
                else "Four scenes × three looks × two tails: exact binomial bounds with total coverage error0.05."
            ),
            (
                "检出率要求机制恢复且经济门槛通过；空信号误报率统计整条路径的任何晋级。"
                if zh
                else "Power counts promotion AND semantic recovery; null counts any promotion by the full path."
            ),
            (
                "已知表达式对照仅供事后诊断，不能筛除失败案例、影响搜索或缩小功效分母。"
                if zh
                else "Known-expression reference is diagnostic only; never filters failed cases or the power denominator."
            ),
            (
                "这是已知合成分布上的保留随机种子测试，不是未知市场机制的盲测。"
                if zh
                else "Known benchmark distributions/held-out RNG, not blind discovery of unknown market mechanisms."
            ),
            (
                "HAC 区间仅供描述。历史 Court 为 NOT_IDENTIFIABLE；没有填造 DSR/PBO/p 值。"
                if zh
                else "HAC account intervals are descriptive. Historical Court NOT_IDENTIFIABLE; no fake DSR/PBO/p-values."
            ),
            "",
            "## 下一步" if zh else "## Next",
            "",
            (
                "真实标签搜索继续暂停；需要独立冻结且明确批准的新 epoch。"
                if zh
                else "Real-label search remains PAUSED and needs a separately frozen, explicitly approved epoch."
            ),
            (
                "V11.2 的时钟、候选与成本不变；缺少某个新数据域不构成所有研究的前置阻断。"
                if zh
                else "V11.2 clock/candidates/costs unchanged. Unavailable new data is not a global research blocker."
            ),
            "",
            "## 待验证" if zh else "## Open questions",
            "",
            (
                "真实来源、更广泛机制族与券商级执行细节的有效性仍未得到验证。"
                if zh
                else "Generalization to real sources, broader mechanism families and executable broker economics is not established."
            ),
            "",
        ]
        with (output / f"report.{language}.md").open("x", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
