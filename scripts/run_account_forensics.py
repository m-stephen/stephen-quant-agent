"""Prepare a fixed read-only forensic plan; launch only after exact review."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.account_forensics_launch import launch, run_worker
from stephen_quant.discovery.account_forensics_plan import prepare_plan
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.search_power_dsl import sha256_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare").add_argument("--output", required=True)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--preregistration-comment", type=int, required=True)
    commands.add_parser("worker", help=argparse.SUPPRESS).add_argument("--operation", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        output = Path(args.output).resolve()
        if not output.is_relative_to((ROOT / "artifacts/account-forensics").resolve()):
            raise ValueError("prepare output must remain in ignored forensic artifacts")
        plan = prepare_plan(ROOT)
        write(output, plan)
        print(json.dumps({"plan_sha256": sha256_json(plan), "new_accounts": 0, "validated_alpha": False}))
    elif args.command == "run":
        result = launch(args.plan, comment_id=args.preregistration_comment, worktree=ROOT)
        print(json.dumps({"outcome": result["outcome"], "validated_alpha": False}))
    else:
        run_worker(args.operation, ROOT)


if __name__ == "__main__":
    main()
