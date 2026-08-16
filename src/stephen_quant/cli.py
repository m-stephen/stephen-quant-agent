from __future__ import annotations

import argparse
import json
import subprocess

from .baseline import BaselineConfig
from .integrity.audit import audit_registry
from .integrity.models import ExperimentSpec, TrialSpec
from .integrity.registry import ExperimentRegistry
from .integrity.snapshot import build_snapshot_manifest
from .qmt import XtquantExportConfig, XtquantExportError, export_qmt_daily_csv, read_stock_file
from .workflows import QmtBacktestRunConfig, run_qmt_backtest_workflow


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

    qmt = sub.add_parser("qmt-backtest")
    qmt.add_argument("--csv", required=True)
    qmt.add_argument("--output", default="reports/qmt")
    qmt.add_argument("--experiment-id")
    qmt.add_argument("--adjustment", required=True)
    qmt.add_argument("--factor", default="ret_60")
    qmt.add_argument("--factor-version", default="1.0.0")
    qmt.add_argument("--train-start", required=True)
    qmt.add_argument("--train-end", required=True)
    qmt.add_argument("--validation-start", required=True)
    qmt.add_argument("--validation-end", required=True)
    qmt.add_argument("--test-start", required=True)
    qmt.add_argument("--test-end", required=True)
    qmt.add_argument("--adv-lookback", type=int, default=20)
    qmt.add_argument("--top-k", type=int, default=10)
    qmt.add_argument("--rebalance-every", type=int, default=5)
    qmt.add_argument("--cash-reserve", type=float, default=0.02)
    qmt.add_argument("--max-position-weight", type=float, default=0.1)
    qmt.add_argument("--commission-bps", type=float, default=3.0)
    qmt.add_argument("--sell-tax-bps", type=float, default=0.0)
    qmt.add_argument("--slippage-bps", type=float, default=5.0)
    qmt.add_argument("--impact-bps", type=float, default=10.0)
    qmt.add_argument("--max-participation-rate", type=float, default=0.05)
    qmt.add_argument("--initial-nav", type=float, default=1_000_000.0)
    qmt.add_argument("--seed", type=int, default=42)

    export = sub.add_parser("qmt-export")
    export.add_argument("--qmt-home", required=True)
    export.add_argument("--output-csv", required=True)
    export.add_argument("--start", required=True)
    export.add_argument("--end", required=True)
    export.add_argument("--adjustment", required=True)
    universe = export.add_mutually_exclusive_group(required=True)
    universe.add_argument("--stocks")
    universe.add_argument("--stock-file")
    universe.add_argument("--sector")
    export.add_argument("--overwrite", action="store_true")
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

    if args.command == "qmt-backtest":
        run = run_qmt_backtest_workflow(
            args.csv,
            registry=registry,
            output_dir=args.output,
            experiment_id=args.experiment_id,
            code_version=_git_head(),
            config=QmtBacktestRunConfig(
                factor_id=args.factor,
                factor_version=args.factor_version,
                adjustment=args.adjustment,
                train_start=args.train_start,
                train_end=args.train_end,
                validation_start=args.validation_start,
                validation_end=args.validation_end,
                test_start=args.test_start,
                test_end=args.test_end,
                adv_lookback=args.adv_lookback,
                initial_nav=args.initial_nav,
                seed=args.seed,
                portfolio=BaselineConfig(
                    top_k=args.top_k,
                    rebalance_every=args.rebalance_every,
                    cash_reserve=args.cash_reserve,
                    max_position_weight=args.max_position_weight,
                    commission_bps=args.commission_bps,
                    sell_tax_bps=args.sell_tax_bps,
                    slippage_bps=args.slippage_bps,
                    impact_coefficient_bps=args.impact_bps,
                    max_participation_rate=args.max_participation_rate,
                ),
            ),
        )
        print(json.dumps(run.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "qmt-export":
        stocks: tuple[str, ...] = ()
        if args.stocks:
            stocks = tuple(item.strip() for item in args.stocks.split(",") if item.strip())
        elif args.stock_file:
            stocks = read_stock_file(args.stock_file)
        try:
            result = export_qmt_daily_csv(
                XtquantExportConfig(
                    qmt_home=args.qmt_home,
                    output_csv=args.output_csv,
                    start_time=args.start,
                    end_time=args.end,
                    adjustment=args.adjustment,
                    stocks=stocks,
                    sector=args.sector,
                    overwrite=args.overwrite,
                )
            )
        except XtquantExportError as exc:
            raise SystemExit(f"qmt-export failed: {exc}") from exc
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return


if __name__ == "__main__":
    main()
