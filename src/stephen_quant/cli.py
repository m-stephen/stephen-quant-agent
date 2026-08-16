from __future__ import annotations

import argparse
import json
import subprocess

from .baseline import BaselineConfig
from .factors import build_factor_catalog, write_factor_catalog
from .integrity.audit import audit_registry
from .integrity.models import ExperimentSpec, TrialSpec
from .integrity.registry import ExperimentRegistry
from .integrity.snapshot import build_snapshot_manifest
from .qmt import (
    DatExportConfig,
    QmtDatError,
    XtquantExportConfig,
    XtquantExportError,
    export_qmt_daily_csv,
    export_qmt_dat_daily_csv,
    load_qd_daily_directory,
    read_stock_file,
    screen_factor_redundancy,
    select_qd_training_universe,
    write_factor_redundancy_screen,
    write_qd_universe,
)
from .workflows import (
    QmtBacktestRunConfig,
    QmtDatValidationConfig,
    build_factor_family_validation_report,
    run_qmt_backtest_workflow,
    run_qmt_dat_backtest_validation,
    write_factor_family_validation_report,
)


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

    factor_catalog = sub.add_parser("factor-catalog")
    factor_catalog.add_argument("--output", default="artifacts/factor-catalog")

    family_report = sub.add_parser("factor-family-report")
    family_report.add_argument("--experiment-id", required=True)
    family_report.add_argument("--output", default="reports/factor-family")

    qmt = sub.add_parser("qmt-backtest")
    qmt_source = qmt.add_mutually_exclusive_group(required=True)
    qmt_source.add_argument("--csv")
    qmt_source.add_argument("--daily-dir")
    qmt_universe = qmt.add_mutually_exclusive_group()
    qmt_universe.add_argument("--stocks")
    qmt_universe.add_argument("--stock-file")
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
    qmt.add_argument("--benchmark-csv")
    qmt.add_argument("--benchmark-name", default="benchmark")
    qmt.add_argument("--placebo-repetitions", type=int, default=0)
    qmt.add_argument("--evaluation-window", choices=("validation", "test"), default="test")
    qmt.add_argument("--experiment-name")
    qmt.add_argument("--experiment-hypothesis")
    qmt.add_argument("--experiment-search-space", default="{}")

    qd_universe = sub.add_parser("qd-select-universe")
    qd_universe.add_argument("--daily-dir", required=True)
    qd_universe.add_argument("--fundamental-dir", required=True)
    qd_universe.add_argument("--train-start", required=True)
    qd_universe.add_argument("--train-end", required=True)
    qd_universe.add_argument("--top-n", type=int, required=True)
    qd_universe.add_argument("--output", default="artifacts/qd-universe")

    factor_screen = sub.add_parser("qd-factor-screen")
    factor_screen.add_argument("--daily-dir", required=True)
    factor_screen.add_argument("--stock-file", required=True)
    factor_screen.add_argument("--data-start", required=True)
    factor_screen.add_argument("--screen-start", required=True)
    factor_screen.add_argument("--screen-end", required=True)
    factor_screen.add_argument("--adjustment", default="back_ratio")
    factor_screen.add_argument("--threshold", type=float, default=0.8)
    factor_screen.add_argument("--output", default="artifacts/qd-factor-screen")

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

    dat_export = sub.add_parser("qmt-dat-export")
    dat_export.add_argument("--datadir", required=True)
    dat_export.add_argument("--output-csv", required=True)
    dat_export.add_argument("--start", required=True)
    dat_export.add_argument("--end", required=True)
    dat_export.add_argument("--adjustment", default="none")
    dat_universe = dat_export.add_mutually_exclusive_group(required=True)
    dat_universe.add_argument("--stocks")
    dat_universe.add_argument("--stock-file")
    dat_export.add_argument("--overwrite", action="store_true")

    dat_validate = sub.add_parser("qmt-dat-validate")
    dat_validate.add_argument("--datadir", required=True)
    dat_validate.add_argument("--output", default="reports/qmt-dat-validation")
    dat_validate.add_argument("--experiment-id")
    dat_validate.add_argument("--data-start", required=True)
    dat_validate.add_argument("--data-end", required=True)
    dat_validate.add_argument("--adjustment", default="none")
    validation_universe = dat_validate.add_mutually_exclusive_group(required=True)
    validation_universe.add_argument("--stocks")
    validation_universe.add_argument("--stock-file")
    dat_validate.add_argument("--factor", default="ret_60")
    dat_validate.add_argument("--factor-version", default="1.0.0")
    dat_validate.add_argument("--train-start", required=True)
    dat_validate.add_argument("--train-end", required=True)
    dat_validate.add_argument("--validation-start", required=True)
    dat_validate.add_argument("--validation-end", required=True)
    dat_validate.add_argument("--test-start", required=True)
    dat_validate.add_argument("--test-end", required=True)
    dat_validate.add_argument("--adv-lookback", type=int, default=20)
    dat_validate.add_argument("--top-k", type=int, default=10)
    dat_validate.add_argument("--rebalance-every", type=int, default=5)
    dat_validate.add_argument("--cash-reserve", type=float, default=0.02)
    dat_validate.add_argument("--max-position-weight", type=float, default=0.1)
    dat_validate.add_argument("--commission-bps", type=float, default=3.0)
    dat_validate.add_argument("--sell-tax-bps", type=float, default=5.0)
    dat_validate.add_argument("--slippage-bps", type=float, default=5.0)
    dat_validate.add_argument("--impact-bps", type=float, default=10.0)
    dat_validate.add_argument("--max-participation-rate", type=float, default=0.05)
    dat_validate.add_argument("--initial-nav", type=float, default=1_000_000.0)
    dat_validate.add_argument("--seed", type=int, default=42)
    dat_validate.add_argument("--overwrite", action="store_true")
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

    if args.command == "factor-catalog":
        catalog = build_factor_catalog()
        artifacts = write_factor_catalog(catalog, args.output)
        print(
            json.dumps(
                {
                    "definitions": len(catalog.entries),
                    "qd_compatible": sum(entry.qd_compatible for entry in catalog.entries),
                    "json_path": str(artifacts.json_path),
                    "json_sha256": artifacts.json_sha256,
                    "markdown_path": str(artifacts.markdown_path),
                    "markdown_sha256": artifacts.markdown_sha256,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "factor-family-report":
        report = build_factor_family_validation_report(registry, args.experiment_id)
        artifacts = write_factor_family_validation_report(report, args.output)
        if report.selected_trial_id is not None:
            registry.register_artifact(
                trial_id=report.selected_trial_id,
                kind="factor_family_validation_json",
                path=str(artifacts.json_path),
                sha256=artifacts.json_sha256,
            )
            registry.register_artifact(
                trial_id=report.selected_trial_id,
                kind="factor_family_validation_markdown",
                path=str(artifacts.markdown_path),
                sha256=artifacts.markdown_sha256,
            )
        print(
            json.dumps(
                {
                    "decision": report.decision,
                    "recorded_trial_count": report.recorded_trial_count,
                    "selected_factor_set": report.selected_factor_set,
                    "dsr_probability": (
                        report.deflated_sharpe.probability
                        if report.deflated_sharpe is not None
                        else None
                    ),
                    "json_path": str(artifacts.json_path),
                    "markdown_path": str(artifacts.markdown_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "qd-select-universe":
        selection = select_qd_training_universe(
            args.daily_dir,
            args.fundamental_dir,
            train_start=args.train_start,
            train_end=args.train_end,
            top_n=args.top_n,
        )
        artifacts = write_qd_universe(selection, args.output)
        print(
            json.dumps(
                {
                    "selection_sha256": selection.selection_sha256,
                    "source_snapshot_sha256": selection.source_snapshot_sha256,
                    "instruments": selection.instruments,
                    "json_path": str(artifacts.json_path),
                    "markdown_path": str(artifacts.markdown_path),
                    "stock_file_path": str(artifacts.stock_file_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "qd-factor-screen":
        stocks = read_stock_file(args.stock_file)
        dataset = load_qd_daily_directory(
            args.daily_dir,
            start_date=args.data_start,
            end_date=args.screen_end,
            instruments=stocks,
            adjustment=args.adjustment,
            include_next_after_end=True,
        )
        catalog = build_factor_catalog()
        definitions = tuple(
            entry.definition
            for entry in catalog.entries
            if entry.qd_compatible and entry.research_status != "rejected_validation"
        )
        screen = screen_factor_redundancy(
            dataset.bars,
            definitions,
            source_snapshot_sha256=dataset.audit.source_sha256,
            screen_start=args.screen_start,
            screen_end=args.screen_end,
            high_correlation_threshold=args.threshold,
        )
        artifacts = write_factor_redundancy_screen(screen, args.output)
        print(
            json.dumps(
                {
                    "factors": len(screen.factor_keys),
                    "pairs": len(screen.pairs),
                    "high_correlation_pairs": len(screen.high_correlation_pairs),
                    "source_snapshot_sha256": screen.source_snapshot_sha256,
                    "json_path": str(artifacts.json_path),
                    "markdown_path": str(artifacts.markdown_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "qmt-backtest":
        stocks = ()
        if args.stocks:
            stocks = tuple(item.strip() for item in args.stocks.split(",") if item.strip())
        elif args.stock_file:
            stocks = read_stock_file(args.stock_file)
        source = args.csv or args.daily_dir
        if args.daily_dir and not stocks:
            raise SystemExit("qmt-backtest failed: --daily-dir requires --stocks or --stock-file")
        run = run_qmt_backtest_workflow(
            source,
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
                instruments=stocks,
                benchmark_csv=args.benchmark_csv,
                benchmark_name=args.benchmark_name,
                placebo_repetitions=args.placebo_repetitions,
                evaluation_window=args.evaluation_window,
                experiment_name=args.experiment_name,
                experiment_hypothesis=args.experiment_hypothesis,
                experiment_search_space=args.experiment_search_space,
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

    if args.command == "qmt-dat-export":
        stocks = ()
        if args.stocks:
            stocks = tuple(item.strip() for item in args.stocks.split(",") if item.strip())
        elif args.stock_file:
            stocks = read_stock_file(args.stock_file)
        try:
            result = export_qmt_dat_daily_csv(
                DatExportConfig(
                    datadir=args.datadir,
                    output_csv=args.output_csv,
                    start_date=args.start,
                    end_date=args.end,
                    adjustment=args.adjustment,
                    stocks=stocks,
                    overwrite=args.overwrite,
                )
            )
        except QmtDatError as exc:
            raise SystemExit(f"qmt-dat-export failed: {exc}") from exc
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return

    if args.command == "qmt-dat-validate":
        stocks = ()
        if args.stocks:
            stocks = tuple(item.strip() for item in args.stocks.split(",") if item.strip())
        elif args.stock_file:
            stocks = read_stock_file(args.stock_file)
        try:
            result = run_qmt_dat_backtest_validation(
                args.datadir,
                registry=registry,
                output_dir=args.output,
                experiment_id=args.experiment_id,
                code_version=_git_head(),
                config=QmtDatValidationConfig(
                    data_start=args.data_start,
                    data_end=args.data_end,
                    stocks=stocks,
                    overwrite=args.overwrite,
                    backtest=QmtBacktestRunConfig(
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
                ),
            )
        except ValueError as exc:
            raise SystemExit(f"qmt-dat-validate failed: {exc}") from exc
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False))
        return


if __name__ == "__main__":
    main()
