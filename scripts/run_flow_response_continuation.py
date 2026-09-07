"""Prepare a fixed no-refit continuation, preregister it, then launch it once."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.flow_response_continuation_launch import (
    launch,
    prepare_plan,
    run_stage,
)
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.search_power_dsl import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("--output", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--preregistration-comment", required=True, type=int)
    for stage in ("backend", "audit"):
        commands.add_parser(stage).add_argument("--operation", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        destination = Path(args.output).resolve()
        if (ROOT / "artifacts/flow-response").resolve() not in destination.parents:
            raise ValueError("prepare output must stay in this worktree's ignored artifacts")
        plan = prepare_plan(ROOT)
        write(destination, plan)
        print(json.dumps({"plan_sha256": sha256_json(plan), "empirical_trial_delta": 0}))
    elif args.command == "run":
        print(json.dumps(launch(args.plan, comment_id=args.preregistration_comment, worktree=ROOT)))
    else:
        run_stage(args.command, operation=args.operation, worktree=ROOT)


if __name__ == "__main__":
    main()
