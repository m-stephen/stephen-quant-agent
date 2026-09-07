"""Prepare, preregister and run a single frozen account diagnostic."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.flow_response_diagnostic import (
    launch_diagnostic,
    prepare_diagnostic,
    run_diagnostic_child,
)
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.search_power_dsl import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("--output", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--preregistration-comment", type=int, required=True)
    commands.add_parser("child").add_argument("--operation", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        destination = Path(args.output).resolve()
        if (ROOT / "artifacts/flow-response").resolve() not in destination.parents:
            raise ValueError("diagnostic plan must use ignored local artifacts")
        plan = prepare_diagnostic(ROOT)
        write(destination, plan)
        print(json.dumps({"plan_sha256": sha256_json(plan), "new_empirical_trials": 0}))
    elif args.command == "run":
        print(
            json.dumps(
                launch_diagnostic(args.plan, comment_id=args.preregistration_comment, worktree=ROOT)
            )
        )
    else:
        run_diagnostic_child(args.operation, ROOT)


if __name__ == "__main__":
    main()
