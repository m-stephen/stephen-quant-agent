"""Small synthetic-only entry point. Intentionally has no real-data path option."""

import argparse
import json

from .contracts import ResetSpec, evidence_state
from .runner import prepare_plan, run_plan


def run_cli(argv=None):
    parser = argparse.ArgumentParser(prog="stephen-quant research-reset")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")
    plan = sub.add_parser("plan")
    plan.add_argument("--mode", choices=("development", "audit"), default="development")
    plan.add_argument("--development-paths", type=int, default=4)
    run = sub.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.action == "status":
        result = evidence_state("NOT_TESTED") | {"spec": ResetSpec().payload()}
    elif args.action == "plan":
        path, envelope = prepare_plan(args.mode, development_paths=args.development_paths)
        result = {"path": str(path), "sha256": envelope["sha256"], "mode": args.mode}
    else:
        result = run_plan(
            args.plan, args.output, progress=lambda value: print(json.dumps(value), flush=True)
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_cli()
