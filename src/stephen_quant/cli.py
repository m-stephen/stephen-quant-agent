from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .integrity.audit import audit_registry
from .integrity.models import ExperimentSpec, TrialSpec
from .integrity.registry import ExperimentRegistry
from .integrity.snapshot import build_snapshot_manifest


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNVERSIONED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stephen-quant")
    parser.add_argument("--db", default="artifacts/registry.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("root")
    snapshot.add_argument("--vendor-version")
    snapshot.add_argument("--notes")

    exp = sub.add_parser("start-experiment")
    exp.add_argument("--name", required=True)
    exp.add_argument("--hypothesis", required=True)
    exp.add_argument("--snapshot-id", required=True)
    exp.add_argument("--search-space", default="{}")

    trial = sub.add_parser("start-trial")
    trial.add_argument("--experiment-id", required=True)
    trial.add_argument("--model", required=True)
    trial.add_argument("--factor-set", required=True)
    trial.add_argument("--hyperparams", default="{}")
    trial.add_argument("--seed", type=int, default=42)
    trial.add_argument("--train-start", required=True)
    trial.add_argument("--train-end", required=True)
    trial.add_argument("--validation-start", required=True)
    trial.add_argument("--validation-end", required=True)
    trial.add_argument("--test-start", required=True)
    trial.add_argument("--test-end", required=True)

    sub.add_parser("audit")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    registry = ExperimentRegistry(args.db)

    if args.command == "init-db":
        registry.initialize()
        print(f"initialized: {args.db}")
        return

    if args.command == "snapshot":
        manifest = build_snapshot_manifest(args.root)
        snapshot_id = registry.register_snapshot(manifest, args.vendor_version, args.notes)
        print(json.dumps({"snapshot_id": snapshot_id, "sha256": manifest.snapshot_sha256}))
        return

    if args.command == "start-experiment":
        experiment_id = registry.create_experiment(
            ExperimentSpec(
                name=args.name,
                hypothesis=args.hypothesis,
                dataset_snapshot_id=args.snapshot_id,
                code_version=_git_head(),
                search_space=args.search_space,
            )
        )
        print(experiment_id)
        return

    if args.command == "start-trial":
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=args.experiment_id,
                model_name=args.model,
                factor_set=args.factor_set,
                hyperparams=args.hyperparams,
                seed=args.seed,
                train_start=args.train_start,
                train_end=args.train_end,
                validation_start=args.validation_start,
                validation_end=args.validation_end,
                test_start=args.test_start,
                test_end=args.test_end,
            )
        )
        print(json.dumps({"trial_id": trial_id, "trial_number": trial_number}))
        return

    if args.command == "audit":
        findings = audit_registry(args.db)
        for finding in findings:
            flag = "PASS" if finding.passed else "FAIL"
            print(f"[{flag}] {finding.check}: {finding.detail}")
        raise SystemExit(0 if all(x.passed for x in findings) else 1)


if __name__ == "__main__":
    main()
