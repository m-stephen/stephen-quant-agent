from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

from .baseline import BaselineConfig
from .factors import build_factor_catalog, write_factor_catalog
from .integrity.audit import audit_registry
from .integrity.models import ExperimentSpec, TrialSpec
from .integrity.registry import ExperimentRegistry
from .integrity.snapshot import build_snapshot_manifest
from .path_config import PathConfigError, load_local_path_config
from .qmt import (
    DatExportConfig,
    DynamicUniverseConfig,
    MarketWideUniverseConfig,
    QmtDataError,
    QmtDatError,
    XtquantExportConfig,
    XtquantExportError,
    build_dynamic_universe,
    build_market_wide_universe,
    create_local_unlock,
    data_search_ledger_record,
    export_qmt_daily_csv,
    export_qmt_dat_daily_csv,
    inventory_local_data,
    load_qd_daily_directory,
    maintain_local_data,
    read_stock_file,
    run_qd_data_audit,
    screen_factor_redundancy,
    select_qd_training_universe,
    validate_research_environment,
    write_dynamic_universe,
    write_factor_redundancy_screen,
    write_industry_proxy_audit,
    write_market_wide_universe,
    write_qd_universe,
)
from .v2 import (
    ShadowBudgetError,
    ShadowLoopStopped,
    load_shadow_loop_config,
    load_v21_real_research_config,
    resolve_discovery_config,
    run_shadow_validation,
    run_v21_readiness,
    verify_shadow_replay,
)
from .workflows import (
    CompositeCpcvConfig,
    ConversionConfig,
    DynamicBacktestConfig,
    PriceDiscoveryConfig,
    QmtBacktestRunConfig,
    QmtDatValidationConfig,
    V4Config,
    V41Config,
    V42Config,
    V44Config,
    V45Config,
    V46Config,
    V47Config,
    V48Config,
    V48HistoricalConfig,
    V48PortfolioReportConfig,
    V50Config,
    build_factor_family_validation_report,
    build_v26_validation_panel,
    load_automated_discovery_config,
    load_label_free_config,
    load_pit_lite_config,
    load_v22_portfolio_breadth_config,
    load_v23_style_residualization_config,
    load_v24_temporal_stability_config,
    load_v25_regime_portfolio_config,
    load_v26_validation_config,
    load_v27_m0_config,
    load_v27_m1_config,
    load_v27_m2_config,
    run_automated_discovery,
    run_automated_discovery_suite,
    run_composite_cpcv_research,
    run_dynamic_cpcv_research,
    run_dynamic_stateful_backtest,
    run_fundamental_cpcv_research,
    run_label_free_benchmark,
    run_pit_lite_research,
    run_price_discovery_lab,
    run_qmt_backtest_workflow,
    run_qmt_dat_backtest_validation,
    run_v4_platform,
    run_v21_real_research,
    run_v22_portfolio_breadth,
    run_v23_style_residualization,
    run_v24_temporal_stability,
    run_v25_regime_portfolio,
    run_v26_validation,
    run_v27_m0_governance,
    run_v27_m1_pit_readiness,
    run_v27_m2_engineering_audit,
    run_v41_semantic_alpha,
    run_v42_stable_conversion,
    run_v43_breadth_audit,
    run_v43_conversion,
    run_v44_path_robust_alpha,
    run_v45_candidate_validation,
    run_v46_orthogonal_search,
    run_v47_low_turnover_alpha,
    run_v48_historical_falsification,
    run_v48_portfolio_report,
    run_v48_sealed_alpha_court,
    run_v49_forward_readiness,
    run_v50_market_wide_search,
    verify_label_free_replay,
    verify_v21_replay,
    verify_v22_portfolio_breadth_replay,
    verify_v23_style_residualization_replay,
    verify_v24_temporal_stability_replay,
    verify_v25_regime_portfolio_replay,
    verify_v26_validation_replay,
    verify_v27_m0_replay,
    verify_v27_m1_replay,
    verify_v27_m2_replay,
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

    qd_data_audit = sub.add_parser("qd-data-audit")
    qd_data_audit.add_argument("--snapshot-root")
    qd_data_audit.add_argument("--allowlist-manifest")
    qd_data_audit.add_argument("--paths-config")
    qd_data_audit.add_argument("--output-dir")

    industry_proxy = sub.add_parser("qd-industry-proxy-audit")
    industry_proxy.add_argument("--paths-config")
    industry_proxy.add_argument("--daily-dir")
    industry_proxy.add_argument("--output", default="artifacts/qd-industry-proxy-audit")

    data_inventory = sub.add_parser("data-inventory")
    data_inventory.add_argument("--paths-config", required=True)
    data_inventory.add_argument("--year", type=int, required=True)
    data_inventory.add_argument("--source-type", default="local")

    data_unlock = sub.add_parser("data-unlock")
    data_unlock.add_argument("--paths-config", required=True)
    data_unlock.add_argument("--manifest", required=True)
    data_unlock.add_argument("--year", type=int, required=True)
    data_unlock.add_argument("--purpose", required=True)
    data_unlock.add_argument("--expires-seconds", type=int, default=7200)
    data_unlock.add_argument("--allow-sealed-2026", action="store_true")

    data_maintain = sub.add_parser("data-maintain")
    data_maintain.add_argument("--paths-config", required=True)
    data_maintain.add_argument("--manifest", required=True)
    data_maintain.add_argument("--operation-id", required=True)

    factor_screen = sub.add_parser("qd-factor-screen")
    factor_screen.add_argument("--daily-dir", required=True)
    factor_screen.add_argument("--stock-file", required=True)
    factor_screen.add_argument("--data-start", required=True)
    factor_screen.add_argument("--screen-start", required=True)
    factor_screen.add_argument("--screen-end", required=True)
    factor_screen.add_argument("--adjustment", default="back_ratio")
    factor_screen.add_argument("--threshold", type=float, default=0.8)
    factor_screen.add_argument("--output", default="artifacts/qd-factor-screen")

    composite = sub.add_parser("qd-composite-cpcv")
    composite.add_argument("--daily-dir", required=True)
    composite.add_argument("--stock-file", required=True)
    composite.add_argument("--data-start", required=True)
    composite.add_argument("--research-start", required=True)
    composite.add_argument("--research-end", required=True)
    composite.add_argument("--validation-start", required=True)
    composite.add_argument("--validation-end", required=True)
    composite.add_argument("--test-start", required=True)
    composite.add_argument("--test-end", required=True)
    composite.add_argument("--adjustment", default="back_ratio")
    composite.add_argument("--groups", type=int, default=6)
    composite.add_argument("--test-groups", type=int, default=3)
    composite.add_argument("--embargo-days", type=int, default=5)
    composite.add_argument("--seed", type=int, default=42)
    composite.add_argument("--output", default="reports/qd-composite-cpcv")

    dynamic_universe = sub.add_parser("qd-dynamic-universe")
    dynamic_universe.add_argument("--daily-dir", required=True)
    dynamic_universe.add_argument("--fundamental-dir", required=True)
    dynamic_universe.add_argument("--research-start", required=True)
    dynamic_universe.add_argument("--research-end", required=True)
    dynamic_universe.add_argument("--top-n", type=int, default=300)
    dynamic_universe.add_argument("--minimum-history-sessions", type=int, default=120)
    dynamic_universe.add_argument("--liquidity-lookback", type=int, default=20)
    dynamic_universe.add_argument("--minimum-mean-amount", type=float, default=20_000_000)
    dynamic_universe.add_argument("--output", default="artifacts/qd-dynamic-universe")

    market_wide = sub.add_parser("qd-market-wide-universe")
    market_wide.add_argument("--paths-config")
    market_wide.add_argument("--daily-dir")
    market_wide.add_argument("--fundamental-dir")
    market_wide.add_argument("--research-start", required=True)
    market_wide.add_argument("--research-end", required=True)
    market_wide.add_argument("--minimum-history-sessions", type=int, default=120)
    market_wide.add_argument("--liquidity-lookback", type=int, default=20)
    market_wide.add_argument("--minimum-mean-amount", type=float, default=10_000_000)
    market_wide.add_argument(
        "--allow-missing-fundamental-date", action="append", default=[]
    )
    market_wide.add_argument("--output", default="artifacts/qd-market-wide-universe")

    dynamic_backtest = sub.add_parser("qd-dynamic-backtest")
    dynamic_backtest.add_argument("--paths-config")
    dynamic_backtest.add_argument("--daily-dir")
    dynamic_backtest.add_argument("--membership-jsonl")
    dynamic_backtest.add_argument("--benchmark-csv")
    dynamic_backtest.add_argument("--data-start", required=True)
    dynamic_backtest.add_argument("--research-start", required=True)
    dynamic_backtest.add_argument("--research-end", required=True)
    dynamic_backtest.add_argument("--validation-start", required=True)
    dynamic_backtest.add_argument("--validation-end", required=True)
    dynamic_backtest.add_argument("--test-start", required=True)
    dynamic_backtest.add_argument("--test-end", required=True)
    dynamic_backtest.add_argument("--factor", default="mom_120_skip_20")
    dynamic_backtest.add_argument("--factor-version", default="1.0.0")
    dynamic_backtest.add_argument("--top-k", type=int, default=20)
    dynamic_backtest.add_argument("--rebalance-every", type=int, default=5)
    dynamic_backtest.add_argument("--cash-reserve", type=float, default=0.02)
    dynamic_backtest.add_argument("--max-position-weight", type=float, default=0.05)
    dynamic_backtest.add_argument("--adv-lookback", type=int, default=20)
    dynamic_backtest.add_argument("--max-participation-rate", type=float, default=0.05)
    dynamic_backtest.add_argument("--commission-bps", type=float, default=3.0)
    dynamic_backtest.add_argument("--sell-tax-bps", type=float, default=5.0)
    dynamic_backtest.add_argument("--slippage-bps", type=float, default=5.0)
    dynamic_backtest.add_argument("--stale-writeoff-sessions", type=int, default=20)
    dynamic_backtest.add_argument("--initial-nav", type=float, default=1_000_000.0)
    dynamic_backtest.add_argument("--seed", type=int, default=42)
    dynamic_backtest.add_argument("--output", default="reports/qd-dynamic-backtest")

    dynamic_cpcv = sub.add_parser("qd-dynamic-cpcv")
    dynamic_cpcv.add_argument("--paths-config")
    dynamic_cpcv.add_argument("--daily-dir")
    dynamic_cpcv.add_argument("--membership-jsonl")
    dynamic_cpcv.add_argument("--candidate-manifest", default="configs/v1.8.14-candidates.json")
    dynamic_cpcv.add_argument("--output", default="reports/qd-v1.8.14-cpcv")

    fundamental_cpcv = sub.add_parser("qd-fundamental-cpcv")
    fundamental_cpcv.add_argument("--paths-config")
    fundamental_cpcv.add_argument("--daily-dir")
    fundamental_cpcv.add_argument("--fundamental-dir")
    fundamental_cpcv.add_argument("--membership-jsonl")
    fundamental_cpcv.add_argument("--candidate-manifest", default="configs/v1.8.15-candidates.json")
    fundamental_cpcv.add_argument("--output", default="reports/qd-v1.8.15-cpcv")

    auto_discovery = sub.add_parser("qd-auto-discover")
    auto_discovery.add_argument("--paths-config", required=True)
    auto_discovery.add_argument("--manifest", default="configs/v1.8.16-search.json")
    auto_discovery.add_argument("--ingested-at", required=True)
    auto_discovery.add_argument("--output", default="reports/qd-v1.8.16-auto")

    auto_suite = sub.add_parser("qd-auto-discover-suite")
    auto_suite.add_argument("--paths-config", required=True)
    auto_suite.add_argument("--suite-manifest", default="configs/v1.8.16-suite.json")
    auto_suite.add_argument("--ingested-at", required=True)
    auto_suite.add_argument("--output", default="reports/qd-v1.8.16-suite")

    price_discovery = sub.add_parser("v3-price-discovery")
    price_discovery.add_argument("--paths-config", required=True)
    price_discovery.add_argument("--output", default="reports/v3.1-price-discovery")

    v4_platform = sub.add_parser("v4-ohlcv-platform")
    v4_platform.add_argument("--paths-config", required=True)
    v4_platform.add_argument("--output", default="reports/v4.0-ohlcv-platform")

    v41_search = sub.add_parser("v4.1-alpha-search")
    v41_search.add_argument("--paths-config", required=True)
    v41_search.add_argument("--output", default="reports/v4.1-semantic-alpha")

    v42_conversion = sub.add_parser("v4.2-stable-conversion")
    v42_conversion.add_argument("--paths-config", required=True)
    v42_conversion.add_argument("--output", default="reports/v4.2-stable-conversion")

    v43_breadth = sub.add_parser("v4.3-domain-breadth")
    v43_breadth.add_argument("--paths-config", required=True)
    v43_breadth.add_argument("--output", default="reports/v4.3-domain-breadth")

    v43_conversion = sub.add_parser("v4.3-conversion")
    v43_conversion.add_argument("--paths-config", required=True)
    v43_conversion.add_argument("--output", default="reports/v4.3-conversion")

    v44_alpha = sub.add_parser("v4.4-path-alpha")
    v44_alpha.add_argument("--paths-config", required=True)
    v44_alpha.add_argument("--output", default="reports/v4.4-path-robust-alpha")

    v45_validation = sub.add_parser("v4.5-candidate-validate")
    v45_validation.add_argument("--paths-config", required=True)
    v45_validation.add_argument("--output", default="reports/v4.5-candidate-validation")

    v46_search = sub.add_parser("v4.6-orthogonal-search")
    v46_search.add_argument("--paths-config", required=True)
    v46_search.add_argument("--output", default="reports/v4.6-orthogonal-search")

    v47_search = sub.add_parser("v4.7-low-turnover-alpha")
    v47_search.add_argument("--paths-config", required=True)
    v47_search.add_argument("--prior-registry", required=True)
    v47_search.add_argument("--output", default="reports/v4.7-low-turnover-alpha")

    v48_court = sub.add_parser("v4.8-sealed-alpha-court")
    v48_court.add_argument("--paths-config", required=True)
    v48_court.add_argument("--v46-registry", required=True)
    v48_court.add_argument("--v47-registry", required=True)
    v48_court.add_argument("--output", default="reports/v4.8-sealed-alpha-court")

    v48_portfolio = sub.add_parser("v4.8-portfolio-report")
    v48_portfolio.add_argument("--paths-config", required=True)
    v48_portfolio.add_argument("--output", default="reports/v4.8-portfolio-report")

    v48_history = sub.add_parser("v4.8-historical-falsification")
    v48_history.add_argument("--paths-config", required=True)
    v48_history.add_argument("--v46-registry", required=True)
    v48_history.add_argument("--v47-registry", required=True)
    v48_history.add_argument("--output", default="reports/v4.8-historical-falsification")

    v49_ready = sub.add_parser("v4.9-forward-readiness")
    v49_ready.add_argument("--paths-config", required=True)
    v49_ready.add_argument("--as-of")
    v49_ready.add_argument("--output", default="reports/v4.9-forward-readiness")

    v50_search = sub.add_parser("v5.0-market-wide-search")
    v50_search.add_argument("--paths-config", required=True)
    v50_search.add_argument("--screening-membership-jsonl", required=True)
    v50_search.add_argument("--membership-jsonl", required=True)
    v50_search.add_argument("--tiers-jsonl", required=True)
    v50_search.add_argument("--prior-inferential-trials", type=int, default=1114)
    v50_search.add_argument("--output", default="reports/v5.0-market-wide-search")

    v2_shadow = sub.add_parser("v2-shadow-validate")
    v2_shadow.add_argument("--config", default="configs/v2.0-m5-shadow.json")
    v2_shadow.add_argument("--output", default="reports/v2.0-shadow")
    v2_shadow.add_argument("--dry-run", action="store_true")
    v2_shadow.add_argument("--kill-switch", action="store_true")
    v2_shadow.add_argument("--replay-manifest")

    v21_real = sub.add_parser("v2-real-research")
    v21_real.add_argument("--paths-config")
    v21_real.add_argument("--config", default="configs/v2.1-real-research.json")
    v21_real.add_argument(
        "--mode", choices=("dry-run", "readiness", "research", "replay", "kill"), default="research"
    )
    v21_real.add_argument("--ingested-at")
    v21_real.add_argument("--output", default="reports/v2.1-real-research")
    v21_real.add_argument("--replay-manifest")

    v22_breadth = sub.add_parser("v2-portfolio-breadth")
    v22_breadth.add_argument("--paths-config")
    v22_breadth.add_argument("--config", default="configs/v2.2-portfolio-breadth.json")
    v22_breadth.add_argument(
        "--mode", choices=("dry-run", "research", "replay", "kill"), default="research"
    )
    v22_breadth.add_argument("--ingested-at")
    v22_breadth.add_argument("--output", default="reports/v2.2-portfolio-breadth")
    v22_breadth.add_argument("--replay-manifest")

    v23_style = sub.add_parser("v2-style-residualization")
    v23_style.add_argument("--paths-config")
    v23_style.add_argument("--config", default="configs/v2.3-style-residualization.json")
    v23_style.add_argument(
        "--mode", choices=("dry-run", "research", "replay", "kill"), default="research"
    )
    v23_style.add_argument("--ingested-at")
    v23_style.add_argument("--output", default="reports/v2.3-style-residualization")
    v23_style.add_argument("--replay-manifest")

    v24_temporal = sub.add_parser("v2-temporal-stability")
    v24_temporal.add_argument("--paths-config")
    v24_temporal.add_argument("--config", default="configs/v2.4-temporal-stability.json")
    v24_temporal.add_argument(
        "--mode", choices=("dry-run", "research", "replay", "kill"), default="research"
    )
    v24_temporal.add_argument("--ingested-at")
    v24_temporal.add_argument("--output", default="reports/v2.4-temporal-stability")
    v24_temporal.add_argument("--replay-manifest")

    v25_regime = sub.add_parser("v2-regime-portfolio")
    v25_regime.add_argument("--paths-config")
    v25_regime.add_argument("--config", default="configs/v2.5-regime-portfolio.json")
    v25_regime.add_argument(
        "--mode", choices=("dry-run", "research", "replay", "kill"), default="research"
    )
    v25_regime.add_argument("--ingested-at")
    v25_regime.add_argument("--output", default="reports/v2.5-regime-portfolio")
    v25_regime.add_argument("--replay-manifest")

    v26_validation = sub.add_parser("v2-validate-2025")
    v26_validation.add_argument("--paths-config")
    v26_validation.add_argument("--config", default="configs/v2.6-validation-2025.json")
    v26_validation.add_argument(
        "--mode", choices=("readiness", "validate", "replay", "kill"), default="validate"
    )
    v26_validation.add_argument("--ingested-at")
    v26_validation.add_argument("--output", default="reports/v2.6-validation-2025")
    v26_validation.add_argument("--replay-manifest")

    v27_governance = sub.add_parser("v2-governance-reset")
    v27_governance.add_argument("--config", default="configs/v2.7-m0-governance.json")
    v27_governance.add_argument(
        "--mode", choices=("run", "replay", "kill"), default="run"
    )
    v27_governance.add_argument("--failure-store", default="reports/v2.7-m0/failures.sqlite3")
    v27_governance.add_argument("--output", default="reports/v2.7-m0")
    v27_governance.add_argument("--replay-manifest")

    v27_readiness = sub.add_parser("v2-pit-readiness")
    v27_readiness.add_argument("--config", default="configs/v2.7-m1-pit-readiness.json")
    v27_readiness.add_argument("--mode", choices=("audit", "replay", "kill"), default="audit")
    v27_readiness.add_argument("--output", default="reports/v2.7-m1")
    v27_readiness.add_argument("--replay-manifest")

    v27_risk = sub.add_parser("v2-risk-controls")
    v27_risk.add_argument("--config", default="configs/v2.7-m2-price-risk.json")
    v27_risk.add_argument("--mode", choices=("audit", "replay", "kill"), default="audit")
    v27_risk.add_argument("--output", default="reports/v2.7-m2")
    v27_risk.add_argument("--replay-manifest")

    pit_lite = sub.add_parser("pit-lite-research")
    pit_lite.add_argument("--paths-config", required=True)
    pit_lite.add_argument("--config", default="configs/v2.9-pit-lite-research.json")
    pit_lite.add_argument("--ingested-at", required=True)
    pit_lite.add_argument("--output", default="reports/v2.9-pit-lite")

    label_free = sub.add_parser("v2-label-free-search")
    label_free.add_argument(
        "--config", default="configs/v2.8-label-free-semantic-search.json"
    )
    label_free.add_argument("--mode", choices=("run", "replay", "kill"), default="run")
    label_free.add_argument("--output", default="reports/v2.8-label-free-semantic-search")
    label_free.add_argument("--replay-manifest")

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

    if args.command == "v2-shadow-validate":
        try:
            if args.replay_manifest:
                verification = verify_shadow_replay(args.replay_manifest)
                print(json.dumps(asdict(verification), indent=2, sort_keys=True))
                return
            config = load_shadow_loop_config(args.config)
            config = replace(
                config,
                dry_run=config.dry_run or args.dry_run,
                kill_switch=config.kill_switch or args.kill_switch,
            )
            report, artifacts = run_shadow_validation(
                registry, args.output, code_version=_git_head(), config=config
            )
        except (ValueError, ShadowBudgetError, ShadowLoopStopped) as exc:
            raise SystemExit(f"v2-shadow-validate failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "zh_markdown_path": str(artifacts.zh_markdown_path),
                    "en_markdown_path": str(artifacts.en_markdown_path),
                    "replay_manifest_path": (
                        None
                        if artifacts.replay_manifest_path is None
                        else str(artifacts.replay_manifest_path)
                    ),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-real-research":
        if args.mode == "kill":
            raise SystemExit(
                "v2-real-research stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(json.dumps(asdict(verify_v21_replay(args.replay_manifest)), indent=2))
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v21_real_research_config(args.config)
            resolve_discovery_config(config, args.config)
            if args.mode == "dry-run":
                required = {"qd_daily_dir", "qd_fundamental_dir", *config.required_sources}
                missing = sorted(required - set(local_paths.paths))
                if missing:
                    raise ValueError(f"missing required local data sources: {missing}")
                print(json.dumps({"decision": "DRY_RUN_PASS", "registry_mutated": False}))
                return
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            if args.mode == "readiness":
                report, artifacts = run_v21_readiness(
                    local_paths, config, args.output, ingested_at=args.ingested_at
                )
                if report.decision != "READY":
                    raise ValueError("V2.1 readiness gate is blocked")
                print(
                    json.dumps(
                        {
                            "decision": report.decision,
                            "snapshot_sha256": report.source_snapshot_sha256,
                            "json_path": str(artifacts.json_path),
                            "en_markdown_path": str(artifacts.markdown_en_path),
                            "zh_markdown_path": str(artifacts.markdown_zh_path),
                            "membership_jsonl_path": str(artifacts.membership_jsonl_path),
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return
            run = run_v21_real_research(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-real-research failed: {exc}") from exc
        print(run.manifest.to_json())
        return

    if args.command == "v2-portfolio-breadth":
        if args.mode == "kill":
            raise SystemExit(
                "v2-portfolio-breadth stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v22_portfolio_breadth_replay(args.replay_manifest)),
                        indent=2,
                    )
                )
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v22_portfolio_breadth_config(args.config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            if args.mode == "dry-run":
                print(
                    json.dumps(
                        {
                            "decision": "DRY_RUN_PASS",
                            "registry_mutated": False,
                            "prior_evidence_sha256": config.prior_evidence_sha256,
                        }
                    )
                )
                return
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            report, artifacts = run_v22_portfolio_breadth(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-portfolio-breadth failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-style-residualization":
        if args.mode == "kill":
            raise SystemExit(
                "v2-style-residualization stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v23_style_residualization_replay(args.replay_manifest)),
                        indent=2,
                    )
                )
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v23_style_residualization_config(args.config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            if args.mode == "dry-run":
                print(
                    json.dumps(
                        {
                            "decision": "DRY_RUN_PASS",
                            "registry_mutated": False,
                            "prior_evidence_sha256": config.prior_evidence_sha256,
                            "industry_neutralization": "BLOCKED_NO_PIT_STOCK_INDUSTRY_MAPPING",
                        }
                    )
                )
                return
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            report, artifacts = run_v23_style_residualization(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-style-residualization failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-temporal-stability":
        if args.mode == "kill":
            raise SystemExit(
                "v2-temporal-stability stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v24_temporal_stability_replay(args.replay_manifest)),
                        indent=2,
                    )
                )
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v24_temporal_stability_config(args.config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            if args.mode == "dry-run":
                print(
                    json.dumps(
                        {
                            "decision": "DRY_RUN_PASS",
                            "registry_mutated": False,
                            "prior_evidence_sha256": config.prior_evidence_sha256,
                            "release_scope": "RESEARCH_PREVIEW_ONLY",
                        }
                    )
                )
                return
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            report, artifacts = run_v24_temporal_stability(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-temporal-stability failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-regime-portfolio":
        if args.mode == "kill":
            raise SystemExit(
                "v2-regime-portfolio stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v25_regime_portfolio_replay(args.replay_manifest)),
                        indent=2,
                    )
                )
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v25_regime_portfolio_config(args.config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            if args.mode == "dry-run":
                print(
                    json.dumps(
                        {
                            "decision": "DRY_RUN_PASS",
                            "registry_mutated": False,
                            "prior_evidence_sha256": config.prior_evidence_sha256,
                            "preregistered_policies": [
                                "risk_off_cash",
                                "risk_off_momentum_fallback",
                            ],
                            "release_scope": "RESEARCH_PREVIEW_ONLY",
                        }
                    )
                )
                return
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            report, artifacts = run_v25_regime_portfolio(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-regime-portfolio failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-validate-2025":
        if args.mode == "kill":
            raise SystemExit(
                "v2-validate-2025 stopped by kill switch before data or registry access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v26_validation_replay(args.replay_manifest)),
                        indent=2,
                    )
                )
                return
            if not args.paths_config:
                raise ValueError("--paths-config is required outside replay and kill modes")
            if not args.ingested_at:
                raise ValueError("--ingested-at with timezone is required")
            local_paths = load_local_path_config(args.paths_config)
            config = load_v26_validation_config(args.config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            if args.mode == "readiness":
                panel = build_v26_validation_panel(
                    local_paths,
                    args.config,
                    output_dir=args.output,
                    ingested_at=args.ingested_at,
                )
                print(json.dumps(panel.readiness.to_dict(), indent=2, sort_keys=True))
                return
            report, artifacts = run_v26_validation(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v2-validate-2025 failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "readiness_json_path": str(artifacts.readiness_json_path),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-governance-reset":
        if args.mode == "kill":
            raise SystemExit(
                "v2-governance-reset stopped before failure-store or artifact access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_v27_m0_replay(args.replay_manifest)),
                        indent=2,
                        sort_keys=True,
                    )
                )
                return
            load_v27_m0_config(args.config)
            report, artifacts = run_v27_m0_governance(
                args.config,
                failure_store_path=args.failure_store,
                output_dir=args.output,
            )
        except ValueError as exc:
            raise SystemExit(f"v2-governance-reset failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-pit-readiness":
        if args.mode == "kill":
            raise SystemExit("v2-pit-readiness stopped before config or artifact access")
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(json.dumps(asdict(verify_v27_m1_replay(args.replay_manifest)), indent=2, sort_keys=True))
                return
            load_v27_m1_config(args.config)
            report, artifacts = run_v27_m1_pit_readiness(args.config, args.output)
        except ValueError as exc:
            raise SystemExit(f"v2-pit-readiness failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-risk-controls":
        if args.mode == "kill":
            raise SystemExit("v2-risk-controls stopped before config or artifact access")
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(json.dumps(asdict(verify_v27_m2_replay(args.replay_manifest)), indent=2, sort_keys=True))
                return
            load_v27_m2_config(args.config)
            report, artifacts = run_v27_m2_engineering_audit(args.config, args.output)
        except ValueError as exc:
            raise SystemExit(f"v2-risk-controls failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v2-label-free-search":
        if args.mode == "kill":
            raise SystemExit(
                "v2-label-free-search stopped before config, fixture or artifact access"
            )
        try:
            if args.mode == "replay":
                if not args.replay_manifest:
                    raise ValueError("--replay-manifest is required in replay mode")
                print(
                    json.dumps(
                        asdict(verify_label_free_replay(args.config, args.replay_manifest)),
                        indent=2,
                        sort_keys=True,
                    )
                )
                return
            load_label_free_config(args.config)
            report, artifacts = run_label_free_benchmark(args.config, args.output)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"v2-label-free-search failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_manifest_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "pit-lite-research":
        try:
            local_paths = load_local_path_config(args.paths_config)
            required = {"qd_daily_dir", "qd_fundamental_dir", "qd_fund_flow_dir"}
            missing = sorted(required - set(local_paths.paths))
            if missing:
                raise ValueError(f"missing required local data sources: {missing}")
            load_pit_lite_config(args.config)
            report, artifacts = run_pit_lite_research(
                local_paths,
                args.config,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                ingested_at=args.ingested_at,
            )
        except (PathConfigError, TypeError, ValueError) as exc:
            raise SystemExit(f"pit-lite-research failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "report": report.to_dict(),
                    "json_path": str(artifacts.json_path),
                    "markdown_en_path": str(artifacts.markdown_en_path),
                    "markdown_zh_path": str(artifacts.markdown_zh_path),
                    "replay_manifest_path": str(artifacts.replay_path),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return

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

    if args.command == "qd-data-audit":
        snapshot_root = args.snapshot_root
        allowlist_manifest = args.allowlist_manifest
        output_dir = args.output_dir
        if args.paths_config:
            local_paths = load_local_path_config(args.paths_config)
            if not snapshot_root and "qd_audit_snapshot_root" in local_paths.paths:
                snapshot_root = str(local_paths.paths["qd_audit_snapshot_root"])
            if not allowlist_manifest and "qd_audit_allowlist_manifest" in local_paths.paths:
                allowlist_manifest = str(local_paths.paths["qd_audit_allowlist_manifest"])
            if not output_dir and "qd_audit_output_dir" in local_paths.paths:
                output_dir = str(local_paths.paths["qd_audit_output_dir"])
        if not snapshot_root or not allowlist_manifest:
            raise SystemExit(
                "qd-data-audit requires a physically isolated snapshot root and a pre-generated 2022-2024 allowlist manifest"
            )
        validate_research_environment(os.environ)
        report = run_qd_data_audit(
            snapshot_root,
            allowlist_manifest,
            github_token=os.environ.get("GITHUB_TOKEN"),
        )
        if output_dir:
            output = Path(output_dir).expanduser().resolve()
            snapshot = Path(snapshot_root).expanduser().resolve()
            try:
                output.relative_to(snapshot)
                overlaps = True
            except ValueError:
                try:
                    snapshot.relative_to(output)
                    overlaps = True
                except ValueError:
                    overlaps = False
            if overlaps:
                raise SystemExit("qd-data-audit output must be physically disjoint from snapshot root")
            output.mkdir(parents=True, exist_ok=True)
            (output / "qd-data-audit.json").write_text(report.to_json() + "\n", encoding="utf-8", newline="\n")
            (output / "qd-data-audit.zh.md").write_text(report.to_markdown(language="zh"), encoding="utf-8", newline="\n")
            (output / "qd-data-audit.en.md").write_text(report.to_markdown(language="en"), encoding="utf-8", newline="\n")
            ledger = data_search_ledger_record(report)
            ledger_name = f"data-search-ledger-{ledger['event_id']}.json"
            ledger_path = output / ledger_name
            try:
                with ledger_path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(ledger, ensure_ascii=False, sort_keys=True) + "\n")
            except FileExistsError:
                existing = json.loads(ledger_path.read_text(encoding="utf-8"))
                if existing != ledger:
                    raise SystemExit("qd-data-audit immutable ledger event collision") from None
            print(
                json.dumps(
                    {
                        "command": "qd-data-audit",
                        "artifacts": [
                            "qd-data-audit.json",
                            "qd-data-audit.zh.md",
                            "qd-data-audit.en.md",
                            ledger_name,
                        ],
                        "source_snapshot_sha256": report.source_snapshot_sha256,
                        "normalized_report_sha256": report.normalized_report_sha256,
                        "gate_pass": report.gate_pass,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(report.to_json())
        if not report.gate_pass:
            raise SystemExit(2)
        return

    if args.command == "qd-industry-proxy-audit":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", args.daily_dir, "--daily-dir")
            report, artifacts = write_industry_proxy_audit(daily_dir, args.output)
        except (PathConfigError, QmtDataError) as exc:
            raise SystemExit(f"qd-industry-proxy-audit failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "command": "qd-industry-proxy-audit",
                    "classification": report.classification,
                    "research_usage": report.research_usage,
                    "inferential_trial_delta": report.inferential_trial_delta,
                    "manifest_sha256": report.manifest_sha256,
                    "result_sha256": report.result_sha256,
                    "artifacts": [
                        str(artifacts.manifest_path),
                        str(artifacts.json_path),
                        str(artifacts.markdown_zh_path),
                        str(artifacts.markdown_en_path),
                    ],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command in {"data-inventory", "data-unlock", "data-maintain"}:
        local_paths = load_local_path_config(args.paths_config)
        required_keys = {"qd_single_user_ledger_dir"}
        if args.command in {"data-inventory", "data-maintain"}:
            required_keys.add("qd_single_user_data_root")
        if args.command == "data-inventory":
            required_keys.add("qd_single_user_manifest_dir")
        missing = sorted(required_keys - set(local_paths.paths))
        if missing:
            raise SystemExit(f"single-user data config missing keys: {missing}")
        ledger_dir = local_paths.paths["qd_single_user_ledger_dir"]
        try:
            if args.command == "data-inventory":
                result, manifest_path = inventory_local_data(
                    local_paths.paths["qd_single_user_data_root"],
                    local_paths.paths["qd_single_user_manifest_dir"],
                    ledger_dir,
                    year=args.year,
                    source_type=args.source_type,
                    code_commit=_git_head(),
                )
                payload = {**asdict(result), "manifest_file": manifest_path.name}
            elif args.command == "data-unlock":
                result = create_local_unlock(
                    args.manifest,
                    ledger_dir,
                    year=args.year,
                    purpose=args.purpose,
                    expires_in_seconds=args.expires_seconds,
                    code_commit=_git_head(),
                    allow_sealed_2026=args.allow_sealed_2026,
                )
                payload = asdict(result)
            else:
                result = maintain_local_data(
                    local_paths.paths["qd_single_user_data_root"],
                    args.manifest,
                    ledger_dir,
                    operation_id=args.operation_id,
                    code_commit=_git_head(),
                )
                payload = asdict(result)
        except (QmtDataError, PathConfigError) as exc:
            raise SystemExit(f"{args.command} failed: {exc}") from exc
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
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

    if args.command == "qd-composite-cpcv":
        stocks = read_stock_file(args.stock_file)
        run = run_composite_cpcv_research(
            args.daily_dir,
            registry=registry,
            output_dir=args.output,
            code_version=_git_head(),
            config=CompositeCpcvConfig(
                data_start=args.data_start,
                research_start=args.research_start,
                research_end=args.research_end,
                validation_start=args.validation_start,
                validation_end=args.validation_end,
                test_start=args.test_start,
                test_end=args.test_end,
                instruments=stocks,
                adjustment=args.adjustment,
                n_groups=args.groups,
                n_test_groups=args.test_groups,
                embargo_days=args.embargo_days,
                seed=args.seed,
            ),
        )
        print(run.report.to_json())
        return

    if args.command == "qd-dynamic-universe":
        report = build_dynamic_universe(
            args.daily_dir,
            args.fundamental_dir,
            DynamicUniverseConfig(
                research_start=args.research_start,
                research_end=args.research_end,
                top_n=args.top_n,
                minimum_history_sessions=args.minimum_history_sessions,
                liquidity_lookback=args.liquidity_lookback,
                minimum_mean_amount_cny=args.minimum_mean_amount,
            ),
        )
        artifacts = write_dynamic_universe(report, args.output)
        print(
            json.dumps(
                {
                    "method_version": report.method_version,
                    "source_snapshot_sha256": report.source_snapshot_sha256,
                    "sessions": report.sessions,
                    "unique_members": report.unique_members,
                    "mean_selected": report.mean_selected,
                    "mean_eligible": report.mean_eligible,
                    "mean_turnover_rate": report.mean_turnover_rate,
                    "json_path": str(artifacts.json_path),
                    "markdown_path": str(artifacts.markdown_path),
                    "membership_jsonl_path": str(artifacts.membership_jsonl_path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "qd-market-wide-universe":
        daily_dir, fundamental_dir = args.daily_dir, args.fundamental_dir
        if args.paths_config:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", daily_dir, "--daily-dir")
            fundamental_dir = local_paths.choose(
                "qd_fundamental_dir", fundamental_dir, "--fundamental-dir"
            )
        if not daily_dir or not fundamental_dir:
            raise SystemExit(
                "qd-market-wide-universe requires --paths-config or both source directories"
            )
        report = build_market_wide_universe(
            daily_dir,
            fundamental_dir,
            MarketWideUniverseConfig(
                research_start=args.research_start,
                research_end=args.research_end,
                minimum_history_sessions=args.minimum_history_sessions,
                liquidity_lookback=args.liquidity_lookback,
                minimum_mean_amount_cny=args.minimum_mean_amount,
                allowed_missing_fundamental_dates=tuple(
                    args.allow_missing_fundamental_date
                ),
            ),
        )
        artifacts = write_market_wide_universe(report, args.output)
        print(
            json.dumps(
                {
                    "method_version": report.method_version,
                    "source_snapshot_sha256": report.source_snapshot_sha256,
                    "sessions": report.sessions,
                    "unique_members": report.unique_members,
                    "mean_eligible": report.mean_eligible,
                    "minimum_eligible": report.minimum_eligible,
                    "maximum_eligible": report.maximum_eligible,
                    "membership_jsonl_path": str(artifacts.membership_jsonl_path),
                    "membership_jsonl_sha256": artifacts.membership_jsonl_sha256,
                    "research_membership_jsonl_path": str(
                        artifacts.research_membership_jsonl_path
                    ),
                    "research_membership_jsonl_sha256": (
                        artifacts.research_membership_jsonl_sha256
                    ),
                    "research_tiers_jsonl_path": str(
                        artifacts.research_tiers_jsonl_path
                    ),
                    "research_tiers_jsonl_sha256": (
                        artifacts.research_tiers_jsonl_sha256
                    ),
                    "screening_membership_jsonl_path": str(
                        artifacts.screening_membership_jsonl_path
                    ),
                    "screening_membership_jsonl_sha256": (
                        artifacts.screening_membership_jsonl_sha256
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "qd-dynamic-backtest":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", args.daily_dir, "--daily-dir")
            membership_jsonl = local_paths.choose(
                "dynamic_membership_jsonl", args.membership_jsonl, "--membership-jsonl"
            )
            benchmark_csv = local_paths.choose("csi300_csv", args.benchmark_csv, "--benchmark-csv")
        except PathConfigError as exc:
            raise SystemExit(f"qd-dynamic-backtest failed: {exc}") from exc
        run = run_dynamic_stateful_backtest(
            daily_dir,
            membership_jsonl,
            benchmark_csv,
            registry=registry,
            output_dir=args.output,
            code_version=_git_head(),
            config=DynamicBacktestConfig(
                data_start=args.data_start,
                research_start=args.research_start,
                research_end=args.research_end,
                validation_start=args.validation_start,
                validation_end=args.validation_end,
                test_start=args.test_start,
                test_end=args.test_end,
                factor_id=args.factor,
                factor_version=args.factor_version,
                top_k=args.top_k,
                rebalance_every=args.rebalance_every,
                cash_reserve=args.cash_reserve,
                maximum_position_weight=args.max_position_weight,
                adv_lookback=args.adv_lookback,
                max_participation_rate=args.max_participation_rate,
                commission_bps=args.commission_bps,
                sell_tax_bps=args.sell_tax_bps,
                slippage_bps=args.slippage_bps,
                stale_writeoff_sessions=args.stale_writeoff_sessions,
                initial_nav=args.initial_nav,
                seed=args.seed,
            ),
        )
        print(run.report.to_json())
        return

    if args.command == "qd-dynamic-cpcv":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", args.daily_dir, "--daily-dir")
            membership_jsonl = local_paths.choose(
                "dynamic_membership_jsonl", args.membership_jsonl, "--membership-jsonl"
            )
            run = run_dynamic_cpcv_research(
                daily_dir,
                membership_jsonl,
                args.candidate_manifest,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"qd-dynamic-cpcv failed: {exc}") from exc
        print(run.report.to_json())
        return

    if args.command == "qd-fundamental-cpcv":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", args.daily_dir, "--daily-dir")
            fundamental_dir = local_paths.choose(
                "qd_fundamental_dir", args.fundamental_dir, "--fundamental-dir"
            )
            membership_jsonl = local_paths.choose(
                "dynamic_membership_jsonl", args.membership_jsonl, "--membership-jsonl"
            )
            run = run_fundamental_cpcv_research(
                daily_dir,
                fundamental_dir,
                membership_jsonl,
                args.candidate_manifest,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"qd-fundamental-cpcv failed: {exc}") from exc
        print(run.report.to_json())
        return

    if args.command == "v3-price-discovery":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", None, "--daily-dir")
            membership_path = local_paths.choose(
                "dynamic_membership_jsonl", None, "--membership-jsonl"
            )
            report = run_price_discovery_lab(
                daily_dir,
                membership_path,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=PriceDiscoveryConfig(),
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v3-price-discovery failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "experiment_id": report.experiment_id,
                    "snapshot_sha256": report.snapshot_sha256,
                    "generated_candidates": report.generated_candidates,
                    "selected_candidate": report.court.selected_candidate_id,
                    "decision": report.court.decision,
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v4-ohlcv-platform":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", None, "--daily-dir")
            membership_path = local_paths.choose(
                "dynamic_membership_jsonl", None, "--membership-jsonl"
            )
            optional_paths = {
                key: str(path)
                for key, path in local_paths.paths.items()
                if key
                in {
                    "qd_fund_flow_dir",
                    "qd_auction_dir",
                    "qd_margin_dir",
                    "qd_industry_dir",
                    "qd_chip_dir",
                    "qd_limit_event_dir",
                }
            }
            report = run_v4_platform(
                daily_dir,
                membership_path,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                optional_paths=optional_paths,
                config=V4Config(),
            )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v4-ohlcv-platform failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "experiment_id": report.experiment_id,
                    "snapshot_sha256": report.snapshot_sha256,
                    "raw_candidates": report.raw_candidates,
                    "effective_hypotheses": report.effective_hypotheses,
                    "selected_candidate": report.selected_candidate_id,
                    "decision": report.decision,
                    "sealed_state": report.sealed_release.state,
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v4.1-alpha-search":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", None, "--daily-dir")
            membership_path = local_paths.choose(
                "dynamic_membership_jsonl", None, "--membership-jsonl"
            )
            optional_paths = {
                key: str(path)
                for key, path in local_paths.paths.items()
                if key
                in {
                    "qd_fund_flow_dir",
                    "qd_auction_dir",
                    "qd_margin_dir",
                    "qd_limit_event_dir",
                }
            }
            report = run_v41_semantic_alpha(
                daily_dir,
                membership_path,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                optional_paths=optional_paths,
                config=V41Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.1-alpha-search failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "experiment_id": report.experiment_id,
                    "snapshot_sha256": report.snapshot_sha256,
                    "proposed_candidates": report.proposed_candidates,
                    "empirically_evaluated": report.empirically_evaluated_candidates,
                    "effective_hypotheses": report.effective_hypotheses,
                    "selected_candidate": report.selected_candidate_id,
                    "selected_usage": (
                        report.selected_usage.spec.usage if report.selected_usage else None
                    ),
                    "decision": report.decision,
                    "sealed_state": report.sealed_release.state,
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v4.2-stable-conversion":
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", None, "--daily-dir")
            membership_path = local_paths.choose(
                "dynamic_membership_jsonl", None, "--membership-jsonl"
            )
            report = run_v42_stable_conversion(
                daily_dir,
                membership_path,
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V42Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.2-stable-conversion failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "experiment_id": report.experiment_id,
                    "snapshot_sha256": report.snapshot_sha256,
                    "shortlist_sha256": report.shortlist_sha256,
                    "selected_candidate": report.selected_candidate_id,
                    "selected_mapping": report.selected_spec.identity,
                    "stability_eligible": report.selected_was_eligible,
                    "decision": report.decision,
                    "sealed_state": report.sealed_release.state,
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v4.3-domain-breadth":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v43_breadth_audit(local_paths.paths, args.output)
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"v4.3-domain-breadth failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "proposed_candidates": report.proposed_candidates,
                    "unique_candidates": report.unique_candidates,
                    "admitted_candidates": report.admitted_candidates,
                    "semantic_domain_count": report.semantic_domain_count,
                    "decision": report.decision,
                    "forward_shadow_start": report.forward_shadow_start,
                    "output": str(Path(args.output).resolve()),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return

    if args.command == "v4.3-conversion":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v43_conversion(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                chip_dir=local_paths.choose("qd_chip_dir", None, "--chip-dir"),
                limit_event_dir=local_paths.choose(
                    "qd_limit_event_dir", None, "--limit-event-dir"
                ),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=ConversionConfig(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.3-conversion failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.4-path-alpha":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v44_path_robust_alpha(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                chip_dir=local_paths.choose("qd_chip_dir", None, "--chip-dir"),
                limit_event_dir=local_paths.choose(
                    "qd_limit_event_dir", None, "--limit-event-dir"
                ),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V44Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.4-path-alpha failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.5-candidate-validate":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v45_candidate_validation(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                limit_event_dir=local_paths.choose(
                    "qd_limit_event_dir", None, "--limit-event-dir"
                ),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V45Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.5-candidate-validate failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.6-orthogonal-search":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v46_orthogonal_search(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose(
                    "qd_fund_flow_dir", None, "--fund-flow-dir"
                ),
                chip_dir=local_paths.choose("qd_chip_dir", None, "--chip-dir"),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V46Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.6-orthogonal-search failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.7-low-turnover-alpha":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v47_low_turnover_alpha(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose(
                    "qd_fund_flow_dir", None, "--fund-flow-dir"
                ),
                registry=registry,
                prior_registry=ExperimentRegistry(args.prior_registry),
                output_dir=args.output,
                code_version=_git_head(),
                config=V47Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.7-low-turnover-alpha failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.8-sealed-alpha-court":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v48_sealed_alpha_court(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose(
                    "qd_fund_flow_dir", None, "--fund-flow-dir"
                ),
                registry=registry,
                v46_registry=ExperimentRegistry(args.v46_registry),
                v47_registry=ExperimentRegistry(args.v47_registry),
                output_dir=args.output,
                code_version=_git_head(),
                config=V48Config(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.8-sealed-alpha-court failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.8-portfolio-report":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v48_portfolio_report(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("dynamic_membership_jsonl", None, "--membership-jsonl"),
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose("qd_fund_flow_dir", None, "--fund-flow-dir"),
                csi300_csv=local_paths.choose("csi300_csv", None, "--csi300-csv"),
                csi500_csv=local_paths.choose("csi500_csv", None, "--csi500-csv"),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V48PortfolioReportConfig(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.8-portfolio-report failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.8-historical-falsification":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v48_historical_falsification(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("qd_fundamental_dir", None, "--fundamental-dir"),
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose("qd_fund_flow_dir", None, "--fund-flow-dir"),
                csi300_csv=local_paths.choose("csi300_csv", None, "--csi300-csv"),
                csi500_csv=local_paths.choose("csi500_csv", None, "--csi500-csv"),
                registry=registry,
                v46_registry=ExperimentRegistry(args.v46_registry),
                v47_registry=ExperimentRegistry(args.v47_registry),
                output_dir=args.output,
                code_version=_git_head(),
                config=V48HistoricalConfig(),
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.8-historical-falsification failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v4.9-forward-readiness":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v49_forward_readiness(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                local_paths.choose("qd_fund_flow_dir", None, "--fund-flow-dir"),
                local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                output_dir=args.output,
                as_of=args.as_of,
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v4.9-forward-readiness failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command == "v5.0-market-wide-search":
        try:
            local_paths = load_local_path_config(args.paths_config)
            report = run_v50_market_wide_search(
                local_paths.choose("qd_daily_dir", None, "--daily-dir"),
                args.screening_membership_jsonl,
                args.membership_jsonl,
                args.tiers_jsonl,
                auction_dir=local_paths.choose("qd_auction_dir", None, "--auction-dir"),
                fund_flow_dir=local_paths.choose(
                    "qd_fund_flow_dir", None, "--fund-flow-dir"
                ),
                chip_dir=local_paths.choose("qd_chip_dir", None, "--chip-dir"),
                registry=registry,
                output_dir=args.output,
                code_version=_git_head(),
                config=V50Config(),
                prior_inferential_trials=args.prior_inferential_trials,
            )
        except (PathConfigError, QmtDataError, ValueError) as exc:
            raise SystemExit(f"v5.0-market-wide-search failed: {exc}") from exc
        print(report.to_json())
        return

    if args.command in {"qd-auto-discover", "qd-auto-discover-suite"}:
        try:
            local_paths = load_local_path_config(args.paths_config)
            daily_dir = local_paths.choose("qd_daily_dir", None, "--daily-dir")
            membership_path = local_paths.paths.get("dynamic_membership_jsonl")
            stock_file = None
            if membership_path is None:
                stock_file = local_paths.choose("discovery_stock_file", None, "--stock-file")
            alternative_paths = {
                key: str(path)
                for key, path in local_paths.paths.items()
                if key
                in {
                    "qd_fund_flow_dir",
                    "qd_auction_dir",
                    "qd_margin_dir",
                    "qd_industry_dir",
                    "qd_chip_dir",
                    "qd_limit_event_dir",
                }
            }
            common = {
                "registry": registry,
                "output_dir": args.output,
                "code_version": _git_head(),
                "alternative_paths": alternative_paths,
                "ingested_at": args.ingested_at,
                "dynamic_membership_path": membership_path,
            }
            stocks = read_stock_file(stock_file) if stock_file else ()
            if args.command == "qd-auto-discover":
                run = run_automated_discovery(
                    daily_dir,
                    stocks,
                    config=load_automated_discovery_config(args.manifest),
                    **common,
                )
            else:
                run = run_automated_discovery_suite(
                    daily_dir,
                    stocks,
                    suite_manifest=args.suite_manifest,
                    **common,
                )
        except (PathConfigError, ValueError) as exc:
            raise SystemExit(f"{args.command} failed: {exc}") from exc
        print(run.report.to_json())
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
