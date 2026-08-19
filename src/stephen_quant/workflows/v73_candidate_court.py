from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from stephen_quant.discovery import GenerationPlan
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig, load_local_path_config

from .automated_discovery import (
    AutomatedDiscoveryConfig,
    AutomatedDiscoveryRun,
    run_automated_discovery,
)
from .v70_discover_alpha import _direction_complete_plan
from .v72_discover_alpha import V72_SOURCE_PAIR_QUOTAS

V73_VERSION = "v7.3-frozen-survivor-full-alpha-court-1.0.0"
V73_PRIOR_INFERENTIAL_TRIALS = 81
V73_FROZEN_TEMPLATE_IDS = frozenset(
    {
        "v70_01257809448d04bd",
        "v70_02ba5e8e4df63ba3",
        "v70_0b5fcf57103dc1ce",
        "v70_2f10152c8f30a7d5",
        "v70_398bb8ef41eccbfe",
        "v70_3d5edc84f5fbaef3",
        "v70_72eec2f4b4d44628",
        "v70_7e2e516a8d1eed38",
        "v70_972d7e5275aef80a",
        "v70_a479b8ef20c4f890",
        "v70_b49c8f23de2cd7e5",
        "v70_cfca1b0e573504cb",
        "v70_d20a33a17385a0de",
        "v70_e1ca2bfca5287df5",
        "v70_edcc7f0a42224b39",
        "v70_f7b7ce83854b9085",
    }
)


def frozen_v73_generation_plan() -> GenerationPlan:
    v71, _ = _direction_complete_plan(16)
    v72, _ = _direction_complete_plan(
        16,
        source_pair_quotas=V72_SOURCE_PAIR_QUOTAS,
    )
    templates = {
        template.template_id: template
        for template in (*v71.templates, *v72.templates)
        if template.template_id in V73_FROZEN_TEMPLATE_IDS
    }
    if set(templates) != V73_FROZEN_TEMPLATE_IDS:
        missing = sorted(V73_FROZEN_TEMPLATE_IDS - set(templates))
        raise ValueError(f"V7.3 frozen template reconstruction failed: {missing}")
    return GenerationPlan(
        templates=tuple(templates[key] for key in sorted(templates)),
        windows=(5,),
        horizons=("5d",),
    )


def run_v73_candidate_court(
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
        raise ValueError("V7.3 requires qd_daily_dir and dynamic_membership_jsonl")
    required_alternatives = {
        key: str(local.paths[key])
        for key in ("qd_fund_flow_dir", "qd_margin_dir", "qd_chip_dir")
        if key in local.paths
    }
    if set(required_alternatives) != {
        "qd_fund_flow_dir",
        "qd_margin_dir",
        "qd_chip_dir",
    }:
        raise ValueError("V7.3 requires fund-flow, margin and chip paths")
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
            schema_budget=16,
            cpcv_budget=16,
            execution_budget=16,
            minimum_coverage=0.80,
            screen_minimum_mean_rank_ic=0.005,
            maximum_peer_rank_correlation=1.0,
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
            search_profile="v7.3",
            minimum_positive_year_fraction=2 / 3,
            maximum_rank_turnover=0.80,
            stability_weight=0.01,
            turnover_penalty=0.01,
            prior_inferential_trials=V73_PRIOR_INFERENTIAL_TRIALS,
            court_minimum_annualized_sharpe=0.50,
            court_maximum_drawdown=0.25,
            all_candidate_court=True,
            doubled_cost_multiplier=2.0,
            minimum_candidate_positive_paths=15,
        ),
        alternative_paths=required_alternatives,
        dynamic_membership_path=membership,
        generation_plan=frozen_v73_generation_plan(),
    )
    report = replace(run.report, method_version=V73_VERSION)
    json_path = output / "v7.3-report.json"
    zh_path = output / "v7.3-report.zh.md"
    en_path = output / "v7.3-report.en.md"
    json_path.write_text(report.to_json() + "\n", encoding="utf-8")
    zh_path.write_text(report.to_markdown("zh"), encoding="utf-8")
    en_path.write_text(report.to_markdown("en"), encoding="utf-8")
    return AutomatedDiscoveryRun(report, json_path, en_path, zh_path, run.schemas_path)
