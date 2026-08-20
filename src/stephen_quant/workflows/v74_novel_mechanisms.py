from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from stephen_quant.discovery import generate_v74_epoch_two_plan, generate_v74_mechanism_plan
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig, load_local_path_config

from .automated_discovery import (
    AutomatedDiscoveryConfig,
    AutomatedDiscoveryRun,
    run_automated_discovery,
)

V74_VERSION = "v7.4-novel-mechanism-automatic-alpha-discovery-1.0.0"
V74_PRIOR_INFERENTIAL_TRIALS = 145
V74_EPOCH_TWO_VERSION = "v7.4-cross-source-confirmation-epoch2-1.0.0"
# Two epoch-two engineering runs each registered all 32 training screens before
# failing closed on the same misplaced CPCV path correction. All 64 attempts
# remain inferential and are carried into the corrected rerun instead of erased.
V74_EPOCH_TWO_PRIOR_INFERENTIAL_TRIALS = 298
V74_FAMILY_BUDGETS = (
    ("price_risk", 2),
    ("price_path", 2),
    ("liquidity", 2),
    ("fund_flow_surprise", 3),
    ("fund_flow_composition", 1),
    ("margin_demand", 3),
    ("chip_structure", 4),
    ("flow_price_interaction", 2),
    ("margin_price_interaction", 2),
    ("chip_price_interaction", 3),
)


def run_v74_novel_mechanism_search(
    paths_config: str | Path | LocalPathConfig,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
) -> AutomatedDiscoveryRun:
    local = (
        paths_config
        if isinstance(paths_config, LocalPathConfig)
        else load_local_path_config(paths_config)
    )
    daily = local.paths.get("qd_daily_dir")
    membership = local.paths.get("dynamic_membership_jsonl")
    if daily is None or membership is None:
        raise ValueError("V7.4 requires qd_daily_dir and dynamic_membership_jsonl")
    alternative_paths = {
        key: str(local.paths[key])
        for key in ("qd_fund_flow_dir", "qd_margin_dir", "qd_chip_dir")
        if key in local.paths
    }
    if set(alternative_paths) != {
        "qd_fund_flow_dir",
        "qd_margin_dir",
        "qd_chip_dir",
    }:
        raise ValueError("V7.4 requires fund-flow, margin and chip paths")

    output = Path(output_dir).expanduser().resolve()
    run = run_automated_discovery(
        daily,
        (),
        registry=registry,
        output_dir=output,
        code_version=code_version,
        config=AutomatedDiscoveryConfig(
            data_start="2021-01-01",
            research_start="2022-01-01",
            research_end="2024-12-31",
            validation_start="2025-01-01",
            validation_end="2025-12-31",
            test_start="2026-01-01",
            test_end="2026-12-31",
            horizon="5d",
            windows=(5,),
            schema_budget=48,
            cpcv_budget=24,
            execution_budget=12,
            minimum_coverage=0.80,
            screen_minimum_mean_rank_ic=0.005,
            maximum_peer_rank_correlation=0.90,
            groups=6,
            test_groups=3,
            embargo_days=5,
            minimum_mean_path_rank_ic=0.005,
            minimum_positive_paths=10,
            maximum_pbo=0.05,
            execution_top_k=10,
            initial_nav=3_000_000.0,
            commission_bps=3.0,
            sell_tax_bps=5.0,
            slippage_bps=5.0,
            impact_coefficient_bps=10.0,
            max_participation_rate=0.05,
            placebo_repetitions=199,
            max_placebo_p_value=0.05,
            min_dsr_probability=0.95,
            dynamic_universe_top_n=300,
            search_profile="v7.4",
            family_budgets=V74_FAMILY_BUDGETS,
            minimum_positive_year_fraction=2 / 3,
            maximum_rank_turnover=0.80,
            stability_weight=0.01,
            turnover_penalty=0.01,
            prior_inferential_trials=V74_PRIOR_INFERENTIAL_TRIALS,
            court_minimum_annualized_sharpe=0.50,
            court_maximum_drawdown=0.25,
            all_candidate_court=True,
            doubled_cost_multiplier=2.0,
            minimum_candidate_positive_paths=15,
        ),
        alternative_paths=alternative_paths,
        dynamic_membership_path=membership,
        generation_plan=generate_v74_mechanism_plan(),
    )
    report = replace(run.report, method_version=V74_VERSION)
    json_path = output / "v7.4-report.json"
    zh_path = output / "v7.4-report.zh.md"
    en_path = output / "v7.4-report.en.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8")
    return AutomatedDiscoveryRun(report, json_path, en_path, zh_path, run.schemas_path)


def frozen_v74_epoch_two_config() -> AutomatedDiscoveryConfig:
    return AutomatedDiscoveryConfig(
        data_start="2021-01-01",
        research_start="2022-01-01",
        research_end="2024-12-31",
        validation_start="2025-01-01",
        validation_end="2025-12-31",
        test_start="2026-01-01",
        test_end="2026-12-31",
        horizon="20d",
        windows=(20,),
        schema_budget=32,
        cpcv_budget=16,
        execution_budget=8,
        minimum_coverage=0.80,
        screen_minimum_mean_rank_ic=0.005,
        maximum_peer_rank_correlation=0.90,
        groups=7,
        test_groups=3,
        embargo_days=20,
        minimum_mean_path_rank_ic=0.005,
        minimum_positive_paths=15,
        maximum_pbo=0.05,
        execution_top_k=20,
        initial_nav=3_000_000.0,
        commission_bps=3.0,
        sell_tax_bps=5.0,
        slippage_bps=5.0,
        impact_coefficient_bps=10.0,
        max_participation_rate=0.05,
        placebo_repetitions=199,
        max_placebo_p_value=0.05,
        min_dsr_probability=0.95,
        dynamic_universe_top_n=300,
        search_profile="v7.4-epoch2",
        family_budgets=(
            ("flow_margin_confirmation", 4),
            ("flow_chip_confirmation", 4),
            ("margin_chip_confirmation", 4),
            ("path_confirmation", 4),
        ),
        minimum_positive_year_fraction=2 / 3,
        maximum_rank_turnover=0.80,
        stability_weight=0.01,
        turnover_penalty=0.01,
        prior_inferential_trials=V74_EPOCH_TWO_PRIOR_INFERENTIAL_TRIALS,
        court_minimum_annualized_sharpe=0.50,
        court_maximum_drawdown=0.25,
        all_candidate_court=True,
        doubled_cost_multiplier=2.0,
        minimum_candidate_positive_paths=15,
    )


def run_v74_epoch_two_search(
    paths_config: str | Path | LocalPathConfig,
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
) -> AutomatedDiscoveryRun:
    local = (
        paths_config
        if isinstance(paths_config, LocalPathConfig)
        else load_local_path_config(paths_config)
    )
    daily = local.paths.get("qd_daily_dir")
    membership = local.paths.get("dynamic_membership_jsonl")
    if daily is None or membership is None:
        raise ValueError("V7.4 epoch two requires qd_daily_dir and dynamic_membership_jsonl")
    alternative_paths = {
        key: str(local.paths[key])
        for key in ("qd_fund_flow_dir", "qd_margin_dir", "qd_chip_dir")
        if key in local.paths
    }
    if set(alternative_paths) != {
        "qd_fund_flow_dir",
        "qd_margin_dir",
        "qd_chip_dir",
    }:
        raise ValueError("V7.4 epoch two requires fund-flow, margin and chip paths")

    output = Path(output_dir).expanduser().resolve()
    run = run_automated_discovery(
        daily,
        (),
        registry=registry,
        output_dir=output,
        code_version=code_version,
        config=frozen_v74_epoch_two_config(),
        alternative_paths=alternative_paths,
        dynamic_membership_path=membership,
        generation_plan=generate_v74_epoch_two_plan(),
    )
    report = replace(run.report, method_version=V74_EPOCH_TWO_VERSION)
    json_path = output / "v7.4-epoch2-report.json"
    zh_path = output / "v7.4-epoch2-report.zh.md"
    en_path = output / "v7.4-epoch2-report.en.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8")
    return AutomatedDiscoveryRun(report, json_path, en_path, zh_path, run.schemas_path)
