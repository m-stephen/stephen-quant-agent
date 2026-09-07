"""Fixed paired synthetic source-power experiment; no market-input arguments.

Each case uses a fresh process, native23 reservations and the full offline audit.
All results, including failed power assertions, are retained. No seed/amplitude,
policy, horizon or cost search is supported by this command.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_flow_response_epoch import synthetic_anchors

from stephen_quant.discovery.flow_response_epoch_audit import audit_complete_epoch
from stephen_quant.discovery.flow_response_protocol import (
    candidate_packet,
    contract,
    plans,
    reserve_trials,
    screen_records,
)
from stephen_quant.discovery.flow_response_synthetic import (
    generator_contract,
    write_synthetic_sources,
)
from stephen_quant.discovery.response_resources import process_memory
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import execute_reserved_epoch
from stephen_quant.workflows.v114_reliable_epoch import write_json


def fixed_plan():
    code = {
        p.relative_to(ROOT).as_posix(): file_sha(p)
        for folder in (
            "src/stephen_quant/discovery",
            "src/stephen_quant/integrity",
            "src/stephen_quant/baseline",
        )
        for p in sorted((ROOT / folder).glob("*.py"))
    }
    for name in (
        "scripts/run_response_source_power.py",
        "src/stephen_quant/workflows/flow_response_epoch.py",
        "src/stephen_quant/qmt/flow_response_inputs.py",
        "src/stephen_quant/qmt/flow_response_panel.py",
        "tests/test_flow_response_epoch.py",
    ):
        code[name] = file_sha(ROOT / name)
    return {
        "generator": generator_contract(),
        "runtime_sources": code,
        "runtime_code_sha256": sha256_json(code),
        "cases": ["planted", "null"],
        "recovery_checks": {
            "interaction_sign": "positive fitted interaction coefficient in both2023/2024",
            "account_increment": "interaction greater total net return than risk and shuffle at82/164bps",
            "null": "neither primary passes the frozen complete exploratory screen after real independent audit",
        },
        "empirical_trial_delta": 0,
        "validated_alpha": False,
    }


def run_case(output, case):
    saved = json.loads((output / "CALIBRATION_PLAN.json").read_bytes())
    if sha256_json(saved) != sha256_json(fixed_plan()):
        raise ValueError("synthetic calibration code/plan changed")
    root = output / case
    root.mkdir(exist_ok=False)
    start, resources = perf_counter(), {}

    def mark(stage):
        resources[stage] = {"seconds": perf_counter() - start, **process_memory()}
        print(json.dumps({"case": case, "stage": stage, **resources[stage]}), flush=True)

    mark("start")
    try:
        calendar, manifest, oracle = write_synthetic_sources(root / "inputs", case=case)
        anchor = synthetic_anchors(root / "original", [d for d in calendar if d >= "2023-01-01"])
        spec = {
            "calendar": calendar,
            "contract": contract(),
            "plans": plans(),
            "packet": candidate_packet(),
            "manifest_sha256": manifest,
            "anchor_card_sha256": anchor,
            "runtime_code_sha256": saved["runtime_code_sha256"],
        }
        operation = root / "operation"
        operation.mkdir()
        registry, tids = reserve_trials(operation, spec)
        mark("native_reservations")
        result = execute_reserved_epoch(
            registry,
            tids,
            spec,
            output=operation,
            input_folder=root / "inputs",
            original_tree=root / "original",
        )
        mark("complete_backend")
        audit = audit_complete_epoch(
            registry,
            operation=operation,
            input_folder=root / "inputs",
            original_tree=root / "original",
        )
        write_json(root / "AUDIT.json", audit)
        mark("complete_independent_audit")
        models = {
            str(y): json.loads((operation / f"models/response_interaction-{y}.json").read_bytes())
            for y in (2023, 2024)
        }
        increments = {
            str(cost): {
                control: result["records"][f"response_interaction-{cost}"]["metrics"][
                    "net_total_return"
                ]
                - result["records"][f"{control}-{cost}"]["metrics"]["net_total_return"]
                for control in ("risk", "shuffle")
            }
            for cost in (82, 164)
        }
        screen = screen_records(
            result["records"],
            result["diagnostics"],
            independent_audit_pass=audit["pipeline_audit_pass"],
        )
        checks = (
            {
                "positive_interaction_both_years": all(
                    m["weights"][-1] > 0 for m in models.values()
                ),
                "positive_net_increment_both_costs": all(
                    v > 0 for c in increments.values() for v in c.values()
                ),
            }
            if case == "planted"
            else {"no_null_exploratory_survivor": not any(screen["screen_survived"].values())}
        )
        assessment = {
            "case": case,
            "synthetic_only": True,
            "empirical_trial_delta": 0,
            "validated_alpha": False,
            "checks": checks,
            "source_power_checks_pass": all(checks.values()),
            "interaction_weights": {y: m["weights"] for y, m in models.items()},
            "net_increments": increments,
            "screen": screen,
            "oracle_sha256": oracle,
            "RESULT_sha256": file_sha(operation / "RESULT.json"),
            "AUDIT_sha256": file_sha(root / "AUDIT.json"),
            "resources": resources,
            "interpretation": "fixed-seed strong-signal recoverability;not marketAlpha or calibrated statistical power/FPR",
        }
        write_json(root / "ASSESSMENT.json", assessment)
        print(
            json.dumps({"case": case, "checks": checks, "net_increments": increments}), flush=True
        )
        return assessment
    except Exception as exc:
        write_json(
            root / "CALIBRATION_ABORTED.json",
            {
                "exception_type": type(exc).__name__,
                "resources": resources,
                "empirical_trial_delta": 0,
                "validated_alpha": False,
            },
        )
        raise


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "CALIBRATION_PLAN.json", fixed_plan())
    children = []
    for case in ("planted", "null"):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL")
        }
        code = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--output",
                str(output),
                "--case",
                case,
            ],
            env=env,
            check=False,
        ).returncode
        children.append({"case": case, "exit_code": code})
        if code:
            write_json(
                output / "CALIBRATION_ABORTED.json",
                {"children": children, "empirical_trial_delta": 0},
            )
            raise RuntimeError("synthetic calibration child failed; preserve all artifacts")
    results = {
        case: json.loads((output / case / "ASSESSMENT.json").read_bytes())
        for case in ("planted", "null")
    }
    write_json(
        output / "CALIBRATION_RESULT.json",
        {
            "children": children,
            "cases": results,
            "all_source_power_checks_pass": all(
                r["source_power_checks_pass"] for r in results.values()
            ),
            "synthetic_native_reservations": 46,
            "empirical_trial_delta": 0,
            "validated_alpha": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--case", choices=("planted", "null"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    path = Path(args.output).resolve()
    allowed = (ROOT / "artifacts/flow-response/source-power").resolve()
    if allowed not in path.parents:
        raise ValueError("synthetic output must be a dedicated source-power subdirectory")
    if args.case:
        run_case(path, args.case)
    else:
        run(path)
