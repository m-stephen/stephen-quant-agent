"""Reviewed bounded development and at most one conditional reserved audit."""

import argparse
import json
import secrets
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from stephen_quant.baseline.stateful import run_stateful_execution
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest

from ..research_reset.accounts import (
    audit_account,
    economic_gate,
    execute_four_accounts,
    execution_config,
    oracle_reference,
    sessions_for,
    targets_for,
)
from ..research_reset.contracts import SCENARIOS, canonical, digest, runtime_manifest
from ..research_reset.runner import control_root, now, read_json, workspace_root, write_new
from ..research_reset.search import discover, scores
from ..research_reset.statistics import calibration_decision, paired_metrics
from .contracts import DEVELOPMENT_SEED, LENGTHS, PowerSpec, pipeline_manifest, seed_for
from .measurement import measurement_suite
from .sources import generate, generator_contract


class Recorder:
    """Native trials reserved before labels; training/evaluation stages are distinct."""

    def __init__(self, registry, directory, panel, plan_hash, spec, seed):
        self.registry, self.directory, self.spec, self.seed = registry, directory, spec, seed
        self.snapshot, self.dates = panel.fingerprint(), panel.dates
        self.events, self.ids = [], []
        self.phase = "primary"
        self.counts = {"structures": 0, "account_runs": 0, "fits": 0, "empirical_trials": 0}
        snapshot = registry.register_snapshot(
            build_composite_snapshot_manifest(
                {
                    "generated_source": self.snapshot,
                    "plan": plan_hash,
                }
            )
        )
        self.eid = registry.create_experiment_deterministic(
            ExperimentSpec(
                "V12.1 synthetic path",
                "NOT market Alpha",
                snapshot,
                digest(pipeline_manifest()),
                canonical(spec.payload()),
                "synthetic",
            ),
            digest({"path": directory.name, "source": self.snapshot, "plan": plan_hash}),
        )

    def __call__(self, event, candidate, value):
        trial_id = None
        if event in ("before_label_read", "before_account", "before_oracle_account"):
            cost, role = (
                (82, "risk_signal")
                if event == "before_label_read"
                else (value["cost"], value["role"])
            )
            stage = self.phase + ":" + event
            identity = digest(
                {
                    "policy": candidate.identity(cost, role),
                    "stage": stage,
                    "source": self.snapshot,
                    "path": self.directory.name,
                }
            )
            params = {
                "candidate": asdict(candidate),
                "cost": cost,
                "role": role,
                "stage": stage,
                "source_sha256": self.snapshot,
                "synthetic_only": True,
                "empirical_trial_delta": 0,
            }
            trial_id, trial_number = self.registry.create_trial_deterministic(
                TrialSpec(
                    self.eid,
                    "v12.1-synthetic",
                    candidate.expression,
                    canonical(params),
                    self.seed,
                    self.dates[1],
                    self.dates[95],
                    self.dates[100],
                    self.dates[-1],
                    "",
                    "",
                ),
                identity,
            )
            if trial_id in self.ids or trial_number != len(self.ids) + 1:
                raise ValueError("duplicate stage reservation; cannot silently reuse trial")
            self.ids.append(trial_id)
            self.counts["structures" if event == "before_label_read" else "account_runs"] += 1
        item = {
            "event": event,
            "phase": self.phase,
            "candidate": asdict(candidate),
            "value": value,
            "trial_id": trial_id,
        }
        self.events.append(item)
        with (self.directory / "ledger.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(canonical(item) + "\n")


def two_accounts(panel, candidate, ranks, support, spec, record):
    sessions = sessions_for(panel, spec)
    result = {}
    for cost in (82, 164):
        daily, evidence = {}, {}
        for role in ("risk_signal", "risk_only"):
            record("before_account", candidate, {"cost": cost, "role": role})
            target, _ = targets_for(panel, candidate, ranks, support, spec, role)
            report = run_stateful_execution(
                sessions,
                target,
                execution_config(cost),
                initial_nav=spec.capital_cny,
                retain_details=True,
            )
            daily[role] = [(p.trade_date, p.net_return) for p in report.periods]
            evidence[role] = {
                "daily": daily[role],
                "audit": audit_account(report),
                "metrics": asdict(report.metrics),
            }
            record(
                "account_complete",
                candidate,
                {"cost": cost, "role": role, "final_nav": report.metrics.final_nav},
            )
        result[str(cost)] = {
            "paired": paired_metrics(
                daily["risk_signal"], daily["risk_only"], capital_cny=spec.capital_cny, lag=10
            ),
            "accounts": evidence,
        }
    return result


def net_training_rank(panel, ranked, ranks, support, spec, record):
    # Explicit mature training slice. Never reuse evaluation_start=100 here.
    train = SimpleNamespace(**(asdict(spec) | {"sessions": 96, "evaluation_start": 1}))
    results = []
    for candidate, gross in ranked[:3]:
        pairs = two_accounts(panel, candidate, ranks, support, train, record)
        net = min(value["paired"]["paired"]["mean"] for value in pairs.values())
        results.append((candidate, net, {"gross_score": gross, "accounts": pairs}))
    return sorted(results, key=lambda item: (-item[1], item[0].structure_id))


def run_path(seed, scenario, spec, output, plan_hash, registry, *, net_diagnostic=False):
    output.mkdir(parents=True, exist_ok=False)
    panel, oracle = generate(seed, scenario, spec)
    fingerprint = panel.fingerprint()
    write_new(
        output / "SOURCE.json",
        {
            "generator": generator_contract(),
            "seed": seed,
            "scenario": scenario,
            "spec": spec.payload(),
            "snapshot_sha256": fingerprint,
        },
    )
    record = Recorder(registry, output, panel, plan_hash, spec, seed)
    winner, ranks, support, ranked = discover(panel, spec, record)
    result = execute_four_accounts(panel, winner, ranks, support, spec, record)
    if net_diagnostic:
        record.phase = "net_training_diagnostic"
        net_ranked = net_training_rank(panel, ranked, ranks, support, spec, record)
        net_winner = net_ranked[0][0]
        record.phase = "net_evaluation_diagnostic"
        pairs = two_accounts(panel, net_winner, ranks, support, spec, record)
        result["net_diagnostic"] = {
            "winner": asdict(net_winner),
            "same_as_primary": net_winner == winner,
            "train": [
                {"candidate": asdict(c), "net_score": s, "evidence": v} for c, s, v in net_ranked
            ],
            "evaluation": pairs,
            "promoted": economic_gate([p["paired"] for p in pairs.values()], spec),
            "used_for_audit_policy_selection": False,
        }
    record.phase = "oracle_evaluator"
    result["oracle_reference"] = oracle_reference(
        panel, oracle, winner, ranks, support, spec, result, record
    )
    exact = winner.expression == oracle.expression and winner.direction == oracle.direction
    correlation = None
    if oracle.expression:
        predicted = scores(winner, ranks)[spec.evaluation_start - 1 : -1].ravel()
        correlation = float(
            np.corrcoef(predicted, oracle.signal[spec.evaluation_start - 1 : -1].ravel())[0, 1]
        )
    result.update(
        {
            "scenario": scenario,
            "seed": seed,
            "spec": spec.payload(),
            "snapshot_sha256": fingerprint,
            "winner": asdict(winner),
            "recovery": {
                "exact": exact,
                "semantic": bool(exact or (correlation is not None and correlation >= 0.60)),
                "correlation": correlation,
            },
            "counts": record.counts | {"native_trials": len(record.ids)},
            "native_trial_ids": record.ids,
            "ledger_sha256": digest(record.events),
        }
    )
    if panel.fingerprint() != fingerprint:
        raise ValueError("generated source changed")
    return result, write_new(output / "RESULT.json", result)


def summarize_development(results):
    cells = []
    for length in LENGTHS:
        for multiplier in (1.0, 0.5):
            for scene in SCENARIOS if multiplier == 1.0 else SCENARIOS[:2]:
                selected = [
                    r
                    for r in results
                    if r["scenario"] == scene
                    and r["spec"]["sessions"] == length + 100
                    and r["spec"]["strength_multiplier"] == multiplier
                ]
                if len(selected) != 8 or len({r["seed"] for r in selected}) != 8:
                    raise ValueError("all eight predeclared paths per development cell required")
                cells.append(
                    {
                        "length": length,
                        "strength_multiplier": multiplier,
                        "scenario": scene,
                        "n": 8,
                        "promoted": sum(r["promoted"] for r in selected),
                        "semantic_promoted": sum(
                            r["promoted"] and r["recovery"]["semantic"] for r in selected
                        ),
                        "oracle_promoted": sum(
                            r["oracle_reference"].get("passes_same_economic_gate", False)
                            for r in selected
                        ),
                        "net_promoted": sum(r["net_diagnostic"]["promoted"] for r in selected),
                        "mean_net_bps_164": float(
                            np.mean(
                                [
                                    r["paired"]["164:risk_only"]["paired"]["mean"] * 10000
                                    for r in selected
                                ]
                            )
                        ),
                    }
                )
    eligible = []
    for length in LENGTHS:
        relevant = [c for c in cells if c["length"] == length and c["strength_multiplier"] == 1.0]
        if all(
            (
                c["promoted"] == 0
                if c["scenario"].endswith("null")
                else c["semantic_promoted"] >= 7 and c["oracle_promoted"] >= 7
            )
            for c in relevant
        ):
            eligible.append(length)
    return {
        "cells": cells,
        "selected_length": min(eligible) if eligible else None,
        "criterion": "coarse 7/8 development screen; not 80% power evidence",
        "cross_cell_independence": False,
        "primary_policy": "unchanged_gross_search",
    }


def root_control():
    return control_root().parent / "v12.1-power-control"


def prepare(mode, *, development_output=None):
    if mode not in ("development", "audit"):
        raise ValueError("synthetic development/audit only")
    suite = "v12.1-" + mode + "-1"
    path = root_control() / "plans" / (suite + ".json")
    if path.exists():
        raise FileExistsError("prepared suite already exists; no replacement")
    length, development_binding = None, None
    if mode == "audit":
        if development_output is None:
            raise ValueError("complete frozen development evidence required")
        development = verify_development(development_output)
        length = development["design"]["selected_length"]
        if length is None or development["measurement"]["numerical_status"] != "PASS":
            raise ValueError("no qualified length or numerical measurement failed; no audit")
        development_binding = {
            "path": str(Path(development_output).resolve()),
            "sha256": digest(development),
        }
    plan = {
        "schema": "v12.1-power-plan-1",
        "suite": suite,
        "mode": mode,
        "created_at": now(),
        "code": pipeline_manifest(),
        "runtime": runtime_manifest(),
        "generator": generator_contract(),
        "review": "v12_review_APPROVE_2026-09-08",
        "issue": 202,
        "master_seed": DEVELOPMENT_SEED if mode == "development" else secrets.randbits(62),
        "selected_length": length,
        "development": development_binding,
        "spec": PowerSpec(sessions=100 + (length or 120)).payload(),
        "real_labels": False,
        "historical_raw_attempts": 3733,
        "development_paths": 144,
        "audit_max_paths": 2000,
        "max_seconds": 14400,
    }
    write_new(path, {"plan": plan, "sha256": digest(plan)})
    return path


def verify_development(output):
    output = Path(output).resolve()
    result = read_json(output / "RESULT.json")
    terminal = read_json(output / "TERMINAL.json")
    if terminal["status"] != "COMPLETE" or terminal["result_sha256"] != digest(result):
        raise ValueError("development terminal/result mismatch")
    if result["mode"] != "development" or result["code"] != pipeline_manifest():
        raise ValueError("development mode/pipeline mismatch")
    values = []
    for item in result["paths"]:
        if not isinstance(item["path"], str) or Path(item["path"]).name != item["path"]:
            raise ValueError("unsafe development evidence path")
        value = read_json(output / "paths" / item["path"] / "RESULT.json")
        if digest(value) != item["sha256"]:
            raise ValueError("development path hash mismatch")
        values.append(value)
    if len(values) != 144 or summarize_development(values) != result["design"]:
        raise ValueError("development design/count mismatch")
    return result


def run(plan_path, output, *, progress=None):
    envelope = read_json(plan_path)
    plan = envelope["plan"]
    if digest(plan) != envelope["sha256"] or plan["code"] != pipeline_manifest():
        raise ValueError("immutable plan/code mismatch")
    if plan["runtime"] != runtime_manifest() or plan["generator"] != generator_contract():
        raise ValueError("runtime/generator mismatch")
    mode = plan["mode"]
    if (
        mode not in ("development", "audit")
        or plan["suite"] != f"v12.1-{mode}-1"
        or plan["real_labels"] is not False
    ):
        raise ValueError("frozen synthetic scope required")
    if (
        Path(plan_path).resolve()
        != (root_control() / "plans" / (plan["suite"] + ".json")).resolve()
    ):
        raise ValueError("shared canonical plan required")
    spec = PowerSpec(
        **{
            k: tuple(v) if k in ("scenarios", "looks", "costs_bps", "horizons") else v
            for k, v in plan["spec"].items()
        }
    ).validate()
    if mode == "audit":
        dev = verify_development(plan["development"]["path"])
        if (
            digest(dev) != plan["development"]["sha256"]
            or dev["design"]["selected_length"] != spec.sessions - 100
        ):
            raise ValueError("audit development binding differs")
        if spec.strength_multiplier != 1.0:
            raise ValueError("audit must retain full-strength population")
    output = Path(output).resolve()
    allowed = (workspace_root() / "artifacts").resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        raise ValueError("new workspace artifact output required")
    write_new(
        root_control() / "claims" / (plan["suite"] + ".json"),
        {"plan_sha256": envelope["sha256"], "consumed_at": now(), "output": str(output)},
    )
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "PLAN.json", envelope)
    registry = ExperimentRegistry(output / "registry.sqlite3")
    registry.initialize()
    started, results, paths, scenes = time.monotonic(), [], [], {}
    totals = {
        "structures": 0,
        "account_runs": 0,
        "fits": 0,
        "empirical_trials": 0,
        "native_trials": 0,
    }
    try:
        measurement = measurement_suite() if mode == "development" else None
        if measurement:
            write_new(output / "MEASUREMENT.json", measurement)
        combinations = (
            [
                (n, m, scene)
                for n in LENGTHS
                for m in (1.0, 0.5)
                for scene in (SCENARIOS if m == 1.0 else SCENARIOS[:2])
            ]
            if mode == "development"
            else [(spec.sessions - 100, 1.0, scene) for scene in SCENARIOS]
        )
        for length, multiplier, scenario in combinations:
            cell_spec = PowerSpec(sessions=100 + length, strength_multiplier=multiplier)
            count, receipt = 0, None
            for index in range(8 if mode == "development" else 500):
                if time.monotonic() - started > 14400:
                    raise TimeoutError("four hour finite resource budget exhausted")
                if pipeline_manifest() != plan["code"]:
                    raise ValueError("pipeline changed during execution")
                seed = seed_for(plan["master_seed"], scenario, index)
                name = f"n{length}-s{int(multiplier * 10)}-{scenario}-{index:04d}"
                value, h = run_path(
                    seed,
                    scenario,
                    cell_spec,
                    output / "paths" / name,
                    envelope["sha256"],
                    registry,
                    net_diagnostic=mode == "development",
                )
                results.append(value)
                paths.append({"path": name, "sha256": h})
                for key in totals:
                    totals[key] += value["counts"][key]
                count += bool(
                    value["promoted"]
                    and (scenario.endswith("null") or value["recovery"]["semantic"])
                )
                if progress:
                    progress(
                        {
                            "mode": mode,
                            "path": name,
                            "completed": len(paths),
                            "elapsed_seconds": round(time.monotonic() - started, 1),
                        }
                    )
                if mode == "audit" and index + 1 in spec.looks:
                    receipt = calibration_decision(
                        count,
                        index + 1,
                        kind="fwer" if scenario.endswith("null") else "power",
                        spec=spec,
                    )
                    write_new(output / "looks" / f"{scenario}-{index + 1}.json", receipt)
                    if receipt["status"] != "CONTINUE":
                        break
            if mode == "audit":
                scenes[scenario] = receipt
        if registry.counts()["trials"] != totals["native_trials"]:
            raise ValueError("native trial count does not reconcile")
        state = "NOT_TESTED_DEVELOPMENT"
        if mode == "audit":
            states = [s["status"] for s in scenes.values()]
            state = (
                "PASS" if states == ["PASS"] * 4 else "FAIL" if "FAIL" in states else "INCONCLUSIVE"
            )
        result = {
            "mode": mode,
            "calibration": state,
            "validated_alpha": False,
            "historical_raw_attempts": 3733,
            "empirical_trial_delta": 0,
            "court": {"status": "NOT_IDENTIFIABLE", "dsr": None, "pbo": None, "placebo": None},
            "paths": paths,
            "counts": totals,
            "code": plan["code"],
            "plan_sha256": envelope["sha256"],
            "measurement": measurement,
            "design": summarize_development(results) if mode == "development" else None,
            "scenarios": scenes,
            "elapsed_seconds": time.monotonic() - started,
        }
        result_hash = write_new(output / "RESULT.json", result)
        write_new(
            output / "TERMINAL.json",
            {"status": "COMPLETE", "result_sha256": result_hash, "ended_at": now()},
        )
        return result
    except BaseException as exc:
        write_new(
            output / "TERMINAL.json",
            {
                "status": "INCONCLUSIVE" if isinstance(exc, TimeoutError) else "ENGINEERING_FAIL",
                "completed_paths": paths,
                "native_counts": registry.counts(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "ended_at": now(),
                "automatic_retry": False,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(description="V12.1 synthetic-only bounded power design")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--mode", choices=("development", "audit"), required=True)
    p.add_argument("--development-output")
    r = sub.add_parser("run")
    r.add_argument("--plan", required=True)
    r.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.action == "plan":
        print(prepare(args.mode, development_output=args.development_output))
    else:
        result = run(args.plan, args.output, progress=lambda x: print(json.dumps(x), flush=True))
        print(
            json.dumps(
                {k: result[k] for k in ("calibration", "counts", "validated_alpha")}, indent=2
            )
        )


if __name__ == "__main__":
    main()
