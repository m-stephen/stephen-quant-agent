from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from stephen_quant.baseline import write_baseline_report
from stephen_quant.discovery import (
    CampaignBudget,
    CampaignSpec,
    DiscoveryCpcvConfig,
    DiscoveryCpcvReport,
    DiscoveryExecutionConfig,
    DiscoveryExecutionReport,
    GenerationPlan,
    ScreeningConfig,
    ScreeningReport,
    ScreeningWindow,
    SearchCampaign,
    StabilityDiagnosticsReport,
    authorize_portfolio_signal,
    build_alpha_card,
    build_research_memory,
    flow_stress_generation_plan,
    generate_candidates,
    normalized_generation_plan,
    register_capacity_stress_trials,
    run_discovery_cpcv,
    run_discovery_execution,
    run_stability_diagnostics,
    run_training_screen,
    seed_generation_plan,
)
from stephen_quant.falsification import write_alpha_court_report
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeAudit,
    QdAlternativeConfig,
    QdAlternativeDataset,
    build_alternative_factor_observations,
    build_multisource_factor_observations,
    build_qmt_factor_observations,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    normalize_cross_sectional_observations,
    select_qd_daily_files,
)

AUTOMATED_DISCOVERY_VERSION = "v1.8.16-automated-discovery-1.0.0"
HORIZON_SESSIONS = {"next_open": 1, "1d": 1, "5d": 5, "20d": 20}


@dataclass(frozen=True)
class AutomatedDiscoveryConfig:
    data_start: str
    research_start: str
    research_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    horizon: str
    windows: tuple[int, ...]
    schema_budget: int
    cpcv_budget: int
    execution_budget: int
    minimum_coverage: float = 0.90
    screen_minimum_mean_rank_ic: float = 0.0
    maximum_peer_rank_correlation: float = 0.80
    groups: int = 6
    test_groups: int = 3
    embargo_days: int = 5
    minimum_mean_path_rank_ic: float = 0.02
    minimum_positive_paths: int = 8
    maximum_pbo: float = 0.20
    execution_top_k: int = 5
    initial_nav: float = 1_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_coefficient_bps: float = 10.0
    max_participation_rate: float = 0.05
    placebo_repetitions: int = 199
    max_placebo_p_value: float = 0.05
    min_dsr_probability: float = 0.95
    dynamic_universe_top_n: int = 50
    seed: int = 42
    search_profile: str = "v1.8.16"
    family_budgets: tuple[tuple[str, int], ...] = ()
    minimum_positive_year_fraction: float = 0.0
    maximum_rank_turnover: float = 1.0
    stability_weight: float = 0.0
    turnover_penalty: float = 0.0
    capacity_stress_rates: tuple[float, ...] = ()
    regime_lookback: int = 20

    def validate(self) -> None:
        window = ScreeningWindow(
            self.research_start,
            self.research_end,
            self.validation_start,
            self.validation_end,
            self.test_start,
            self.test_end,
        )
        window.validate()
        if self.data_start > self.research_start:
            raise ValueError("data_start must provide history before research_start")
        if self.horizon not in HORIZON_SESSIONS:
            raise ValueError(f"unsupported automated-discovery horizon: {self.horizon}")
        if not self.windows or any(window < 2 for window in self.windows):
            raise ValueError("automated-discovery windows must contain values >= 2")
        CampaignBudget(
            self.schema_budget, self.cpcv_budget, self.execution_budget
        ).validate()
        if self.execution_budget and self.execution_budget < 2:
            raise ValueError("execution_budget must be zero or at least two for DSR")
        if self.dynamic_universe_top_n < 3:
            raise ValueError("dynamic_universe_top_n must be at least three")
        if self.search_profile not in {"v1.8.16", "v1.8.17", "v1.8.18"}:
            raise ValueError("search_profile must be v1.8.16, v1.8.17 or v1.8.18")
        if len(set(self.capacity_stress_rates)) != len(self.capacity_stress_rates) or any(
            not 0 < rate <= 1 for rate in self.capacity_stress_rates
        ):
            raise ValueError("capacity_stress_rates must be unique values in (0, 1]")
        if self.search_profile == "v1.8.18" and len(self.capacity_stress_rates) != 3:
            raise ValueError("v1.8.18 requires exactly three capacity stress rates")
        if self.regime_lookback < 5:
            raise ValueError("regime_lookback must be at least five")
        ScreeningConfig(
            minimum_coverage=self.minimum_coverage,
            minimum_mean_rank_ic=self.screen_minimum_mean_rank_ic,
            maximum_peer_rank_correlation=self.maximum_peer_rank_correlation,
            family_budgets=self.family_budgets,
            minimum_positive_year_fraction=self.minimum_positive_year_fraction,
            maximum_rank_turnover=self.maximum_rank_turnover,
            stability_weight=self.stability_weight,
            turnover_penalty=self.turnover_penalty,
        ).validate()
        DiscoveryExecutionConfig(
            top_k=self.execution_top_k,
            initial_nav=self.initial_nav,
            commission_bps=self.commission_bps,
            sell_tax_bps=self.sell_tax_bps,
            slippage_bps=self.slippage_bps,
            impact_coefficient_bps=self.impact_coefficient_bps,
            max_participation_rate=self.max_participation_rate,
            placebo_repetitions=self.placebo_repetitions,
            max_placebo_p_value=self.max_placebo_p_value,
            min_dsr_probability=self.min_dsr_probability,
            maximum_pbo=self.maximum_pbo,
        ).validate()


@dataclass(frozen=True)
class AutomatedDiscoveryReport:
    method_version: str
    experiment_id: str
    campaign_id: str
    snapshot_id: str
    source_snapshot_sha256: str
    generated_candidates: int
    unique_candidates: int
    screening: ScreeningReport
    cpcv: DiscoveryCpcvReport | None
    execution: DiscoveryExecutionReport | None
    stability_diagnostics: StabilityDiagnosticsReport | None
    alternative_audits: tuple[QdAlternativeAudit, ...]
    dynamic_universe_sha256: str | None
    dynamic_universe_unique_members: int | None
    dynamic_universe_top_n: int | None
    validation_window_opened: bool
    test_window_opened: bool
    decision: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("report language must be en or zh")
        zh = language == "zh"
        title = (
            "# V1.8.18 资金背离稳定性与容量压力报告"
            if zh and "1.8.18" in self.method_version
            else "# V1.8.18 Flow-divergence Stability and Capacity Stress"
            if "1.8.18" in self.method_version
            else "# V1.8.17 标准化多源因子发现与回测报告"
            if zh and "1.8.17" in self.method_version
            else "# V1.8.17 Normalized Multi-source Factor Discovery and Backtest"
            if "1.8.17" in self.method_version
            else "# V1.8.16 自动因子发现与回测报告"
            if zh
            else "# V1.8.16 Automated Factor Discovery and Backtest"
        )
        decision_label = "结论" if zh else "Decision"
        generated_label = "生成候选" if zh else "Generated candidates"
        shortlist_label = "CPCV 入围" if zh else "CPCV shortlist"
        source_label = "数据快照" if zh else "Data snapshot"
        validation_label = "验证期是否打开" if zh else "Validation window opened"
        test_label = "最终测试期是否打开" if zh else "Final test window opened"
        lines = [
            title,
            "",
            f"**{decision_label}: {self.decision}**",
            "",
            f"- Experiment: `{self.experiment_id}`",
            f"- Campaign: `{self.campaign_id}`",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- {source_label}: `{self.source_snapshot_sha256}`",
            f"- {generated_label}: {self.generated_candidates} ({self.unique_candidates} unique)",
            f"- {shortlist_label}: {len(self.screening.shortlisted_fingerprints)}",
            f"- {validation_label}: {self.validation_window_opened}",
            f"- {test_label}: {self.test_window_opened}",
            f"- Dynamic universe snapshot: `{self.dynamic_universe_sha256 or 'not configured'}`",
            f"- Dynamic universe unique members: {self.dynamic_universe_unique_members or 'N/A'}",
            "",
            "## Screening / 筛选",
            "",
            "| Trial | Family | Schema | Coverage | Mean RankIC | Stable years | Turnover | Objective | Decision |",
            "|---:|---|---|---:|---:|---:|---:|---:|---|",
        ]
        for score in self.screening.scores:
            rank_ic = "N/A" if score.mean_rank_ic is None else f"{score.mean_rank_ic:.6f}"
            stability = (
                "N/A"
                if score.positive_year_fraction is None
                else f"{score.positive_year_fraction:.2%}"
            )
            turnover = "N/A" if score.rank_turnover is None else f"{score.rank_turnover:.4f}"
            objective = "N/A" if score.objective_score is None else f"{score.objective_score:.6f}"
            lines.append(
                f"| {score.trial_number} | `{score.family}` | `{score.schema_id}` | "
                f"{score.coverage:.2%} | {rank_ic} | {stability} | {turnover} | "
                f"{objective} | {score.decision} |"
            )
        if self.cpcv is not None:
            lines.extend(["", self.cpcv.to_markdown(language=language).strip(), ""])
        if self.execution is not None:
            court = self.execution.alpha_court
            lines.extend(
                [
                    "",
                    "## Execution and falsification / 执行与证伪",
                    "",
                    "| Trial | Schema | Periods | Raw Sharpe | Net return | Max drawdown | Cost |",
                    "|---:|---|---:|---:|---:|---:|---:|",
                ]
            )
            lines.extend(
                f"| {score.trial_number} | `{score.schema_id}` | {score.periods} | "
                f"{score.raw_net_sharpe:.6f} | {score.net_total_return:.2%} | "
                f"{score.max_drawdown:.2%} | {score.total_cost:.2f} |"
                for score in self.execution.configurations
            )
            lines.extend(
                [
                    "",
                    f"- Alpha Court: **{self.execution.decision}**",
                    f"- Signal-shuffle p-value: {court.signal_placebo.empirical_p_value:.6f}",
                    f"- Return-permutation p-value: {court.return_placebo.empirical_p_value:.6f}",
                    f"- DSR probability: {court.deflated_sharpe.probability:.6f}",
                    f"- PBO: {court.pbo.probability:.6f}",
                    f"- Recorded trials: {court.recorded_trial_count}",
                    f"- Walk-forward net return: {self.execution.walk_forward.net_total_return:.2%}",
                    f"- Walk-forward annualized Sharpe: {self.execution.walk_forward.annualized_net_sharpe}",
                    f"- Walk-forward max drawdown: {self.execution.walk_forward.max_drawdown:.2%}",
                    f"- Walk-forward gate: {self.execution.walk_forward.passed}",
                ]
            )
        if self.alternative_audits:
            lines.extend(
                [
                    "",
                    "## Alternative data readiness / 替代数据就绪情况",
                    "",
                    "| Source | Files | Rows | Instruments | Snapshot |",
                    "|---|---:|---:|---:|---|",
                ]
            )
            lines.extend(
                f"| {audit.source_kind} | {audit.source_files} | {audit.rows} | "
                f"{audit.instruments} | `{audit.source_sha256}` |"
                for audit in self.alternative_audits
            )
        if self.stability_diagnostics is not None:
            lines.extend(["", self.stability_diagnostics.to_markdown(language).strip(), ""])
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class AutomatedDiscoveryRun:
    report: AutomatedDiscoveryReport
    json_path: Path
    markdown_en_path: Path
    markdown_zh_path: Path
    schemas_path: Path


def load_automated_discovery_config(source: str | Path) -> AutomatedDiscoveryConfig:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"automated-discovery manifest does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("automated-discovery manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.pop("manifest_version", None) != "1.0.0":
        raise ValueError("automated-discovery manifest_version must be 1.0.0")
    if "windows" in payload and isinstance(payload["windows"], list):
        payload["windows"] = tuple(payload["windows"])
    if "family_budgets" in payload and isinstance(payload["family_budgets"], list):
        payload["family_budgets"] = tuple(
            tuple(item) for item in payload["family_budgets"]
        )
    if "capacity_stress_rates" in payload and isinstance(
        payload["capacity_stress_rates"], list
    ):
        payload["capacity_stress_rates"] = tuple(payload["capacity_stress_rates"])
    try:
        config = AutomatedDiscoveryConfig(**payload)
    except TypeError as exc:
        raise ValueError("automated-discovery manifest fields are invalid") from exc
    config.validate()
    return config


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _ranked_dynamic_memberships(
    source: str | Path, top_n: int
) -> tuple[dict[str, tuple[str, ...]], str]:
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"dynamic membership JSONL does not exist: {path}")
    content = path.read_bytes()
    result: dict[str, tuple[str, ...]] = {}
    for line_number, line in enumerate(content.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            day = date.fromisoformat(str(payload["decision_date"])).isoformat()
            raw_members = payload["members"]
            if not isinstance(raw_members, list):
                raise TypeError
            members = tuple(dict.fromkeys(str(item).strip().upper() for item in raw_members))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"dynamic membership line {line_number} is invalid") from exc
        if day in result or not members:
            raise ValueError(f"dynamic membership date is duplicate or empty: {day}")
        result[day] = members[:top_n]
    if not result:
        raise ValueError("dynamic membership JSONL is empty")
    return result, hashlib.sha256(content).hexdigest()


def _execution_memberships(
    memberships: dict[str, tuple[str, ...]], execution_dates: list[str]
) -> dict[str, tuple[str, ...]]:
    ordered = sorted(memberships)
    result: dict[str, tuple[str, ...]] = {}
    offset = 0
    latest: tuple[str, ...] = ()
    for execution_day in sorted(execution_dates):
        while offset < len(ordered) and ordered[offset] < execution_day:
            latest = memberships[ordered[offset]]
            offset += 1
        result[execution_day] = latest
    return result


def _trim_leading_warmup(
    rows: tuple,
) -> tuple:
    """Drop only leading dates before a factor has any eligible cross-section."""

    eligible_dates = {row.execution_at for row in rows if row.eligible}
    first_usable = min(eligible_dates) if eligible_dates else None
    if first_usable is None:
        return rows
    return tuple(row for row in rows if row.execution_at >= first_usable)


def _alternative_datasets(
    paths: dict[str, str],
    config: AutomatedDiscoveryConfig,
    *,
    ingested_at: str,
    instruments: tuple[str, ...],
) -> dict[str, QdAlternativeDataset]:
    mapping = {
        "qd_fund_flow_dir": ("qd_fund_flow", "fund_flow"),
        "qd_auction_dir": ("qd_auction", "auction"),
        "qd_margin_dir": ("qd_margin", "margin"),
        "qd_industry_dir": ("qd_industry", "industry"),
    }
    datasets: dict[str, QdAlternativeDataset] = {}
    for key, (source_name, kind) in mapping.items():
        if key not in paths:
            continue
        dataset = load_qd_alternative_directory(
            paths[key],
            QdAlternativeConfig(
                source_kind=kind,  # type: ignore[arg-type]
                start_date=config.research_start,
                end_date=config.research_end,
                ingested_at=ingested_at,
                instruments=instruments if kind != "industry" else (),
            ),
        )
        datasets[source_name] = dataset
    return datasets


def run_automated_discovery(
    daily_dir: str | Path,
    instruments: tuple[str, ...],
    *,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: AutomatedDiscoveryConfig,
    alternative_paths: dict[str, str] | None = None,
    dynamic_membership_path: str | Path | None = None,
    ingested_at: str = "1970-01-01T00:00:00+00:00",
) -> AutomatedDiscoveryRun:
    """Run bounded generation, training-only screening and CPCV without opening reserves."""

    config.validate()
    dynamic_memberships: dict[str, tuple[str, ...]] | None = None
    dynamic_sha256: str | None = None
    if dynamic_membership_path is not None:
        dynamic_memberships, dynamic_sha256 = _ranked_dynamic_memberships(
            dynamic_membership_path, config.dynamic_universe_top_n
        )
        instruments = tuple(
            sorted({instrument for members in dynamic_memberships.values() for instrument in members})
        )
    if len(instruments) < 3:
        raise ValueError("automated discovery requires at least three instruments")
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(
        root, start_date=config.data_start, end_date=config.research_end
    )
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    alternative_paths = alternative_paths or {}
    alternative_datasets = _alternative_datasets(
        alternative_paths,
        config,
        ingested_at=ingested_at,
        instruments=tuple(sorted(set(instruments))),
    )
    snapshot_components = {"qd_daily": daily_manifest.snapshot_sha256}
    snapshot_components.update(
        {
            source: dataset.audit.source_sha256
            for source, dataset in alternative_datasets.items()
        }
    )
    if dynamic_sha256 is not None:
        snapshot_components["dynamic_universe"] = dynamic_sha256
    source_manifest = build_composite_snapshot_manifest(snapshot_components)
    snapshot_id = registry.register_snapshot(
        source_manifest,
        vendor_version="QD multi-source point-in-time research snapshot",
        notes="V1.8.16 research sources only; validation and final test remain sealed.",
    )
    source_keys = {
        "qd_fund_flow_dir": "qd_fund_flow",
        "qd_auction_dir": "qd_auction",
        "qd_margin_dir": "qd_margin",
        "qd_industry_dir": "qd_industry",
    }
    available_sources = {"qd_daily"} | {
        source for key, source in source_keys.items() if key in alternative_paths
    }
    plan_seed = (
        flow_stress_generation_plan()
        if config.search_profile == "v1.8.18"
        else normalized_generation_plan()
        if config.search_profile == "v1.8.17"
        else seed_generation_plan()
    )
    plan = GenerationPlan(
        templates=tuple(
            template
            for template in plan_seed.templates
            if set(template.data_sources) <= available_sources
        ),
        windows=config.windows,
        horizons=(config.horizon,),  # type: ignore[arg-type]
    )
    planned_count = len(plan.templates) * len(set(plan.windows))
    if planned_count > config.schema_budget:
        raise ValueError("generation plan exceeds the frozen schema budget")
    search_space = json.dumps(
        {
            "method_version": (
                "v1.8.18-flow-stability-1.0.0"
                if config.search_profile == "v1.8.18"
                else "v1.8.17-normalized-multisource-1.0.0"
                if config.search_profile == "v1.8.17"
                else AUTOMATED_DISCOVERY_VERSION
            ),
            "config": asdict(config),
            "planned_candidates": planned_count,
        },
        indent=2,
        sort_keys=True,
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name=f"{config.search_profile}_automated_factor_discovery",
            hypothesis="A bounded structured search can identify stable factor candidates.",
            dataset_snapshot_id=snapshot_id,
            code_version=code_version,
            search_space=search_space,
        )
    )
    campaign = SearchCampaign(
        registry,
        CampaignSpec(
            name=f"{config.search_profile} structured search",
            experiment_id=experiment_id,
            budget=CampaignBudget(
                config.schema_budget, config.cpcv_budget, config.execution_budget
            ),
            horizons=(config.horizon,),
            ranking_metric="training_mean_rank_ic_then_cpcv_mean_path_rank_ic",
            stopping_rule="fixed schema and shortlist budgets",
            sealed_windows=(
                f"validation:{config.validation_start}:{config.validation_end}",
                f"test:{config.test_start}:{config.test_end}",
            ),
        ),
    )
    candidates = generate_candidates(campaign, plan)
    dataset = load_qd_daily_directory(
        root,
        start_date=config.data_start,
        end_date=config.research_end,
        instruments=tuple(sorted(set(instruments))),
        adjustment="back_ratio",
    )
    eligibility = None
    if dynamic_memberships is not None:
        eligibility = _execution_memberships(
            dynamic_memberships,
            sorted(
                {
                    bar.trade_date
                    for bar in dataset.bars
                    if config.research_start <= bar.trade_date <= config.research_end
                }
            ),
        )
    observations: dict[str, tuple] = {}
    for item in candidates:
        if item.unique and item.schema.data_sources == ("qd_daily",):
            observations[item.schema.fingerprint] = build_qmt_factor_observations(
            dataset.bars,
            item.schema.compile(),
            test_start=config.research_start,
            test_end=config.research_end,
            horizon_sessions=HORIZON_SESSIONS[config.horizon],
            eligible_by_execution_date=eligibility,
        )
    anchor = next(iter(observations.values()))
    for item in candidates:
        if not item.unique or item.schema.data_sources == ("qd_daily",):
            continue
        if len(item.schema.data_sources) == 1:
            source = item.schema.data_sources[0]
            observations[item.schema.fingerprint] = build_alternative_factor_observations(
                alternative_datasets[source].observations,
                item.schema.compile(),
                anchor,
            )
        else:
            sources = {
                source: alternative_datasets[source].observations
                for source in item.schema.data_sources
                if source != "qd_daily"
            }
            observations[item.schema.fingerprint] = build_multisource_factor_observations(
                dataset.bars,
                sources,
                item.schema.compile(),
                anchor,
            )
    if config.search_profile in {"v1.8.17", "v1.8.18"}:
        observations = {
            fingerprint: _trim_leading_warmup(
                normalize_cross_sectional_observations(rows)
            )
            for fingerprint, rows in observations.items()
        }
    window = ScreeningWindow(
        config.research_start,
        config.research_end,
        config.validation_start,
        config.validation_end,
        config.test_start,
        config.test_end,
    )
    screening = run_training_screen(
        registry,
        campaign,
        candidates,
        observations,
        window=window,
        config=ScreeningConfig(
            minimum_coverage=config.minimum_coverage,
            minimum_mean_rank_ic=config.screen_minimum_mean_rank_ic,
            maximum_peer_rank_correlation=config.maximum_peer_rank_correlation,
            family_budgets=config.family_budgets,
            minimum_positive_year_fraction=config.minimum_positive_year_fraction,
            maximum_rank_turnover=config.maximum_rank_turnover,
            stability_weight=config.stability_weight,
            turnover_penalty=config.turnover_penalty,
        ),
        seed=config.seed,
    )
    cpcv: DiscoveryCpcvReport | None = None
    if len(screening.shortlisted_fingerprints) >= 2:
        shortlisted_panels = {
            fingerprint: observations[fingerprint]
            for fingerprint in screening.shortlisted_fingerprints
        }
        common_keys = set.intersection(
            *(
                {
                    (row.execution_at, row.instrument)
                    for row in rows
                    if row.eligible
                }
                for rows in shortlisted_panels.values()
            )
        )
        if not common_keys:
            raise ValueError("shortlisted CPCV candidates have no common observation panel")
        aligned_cpcv_observations = {
            fingerprint: tuple(
                row
                for row in rows
                if row.eligible and (row.execution_at, row.instrument) in common_keys
            )
            for fingerprint, rows in shortlisted_panels.items()
        }
        cpcv = run_discovery_cpcv(
            registry,
            campaign,
            screening,
            candidates,
            aligned_cpcv_observations,
            snapshot_id=snapshot_id,
            code_version=code_version,
            window=window,
            config=DiscoveryCpcvConfig(
                groups=config.groups,
                test_groups=config.test_groups,
                embargo_days=config.embargo_days,
                minimum_mean_path_rank_ic=config.minimum_mean_path_rank_ic,
                minimum_positive_paths=config.minimum_positive_paths,
                maximum_pbo=config.maximum_pbo,
            ),
            seed=config.seed,
        )
    execution: DiscoveryExecutionReport | None = None
    stability_diagnostics: StabilityDiagnosticsReport | None = None
    execution_reports = {}
    if cpcv is not None and cpcv.signal_gate_passed and config.execution_budget >= 2:
        stress_registrations = (
            register_capacity_stress_trials(
                registry,
                experiment_id=campaign.spec.experiment_id,
                window=window,
                participation_rates=config.capacity_stress_rates,
                seed=config.seed,
            )
            if config.capacity_stress_rates
            else ()
        )
        execution_config = DiscoveryExecutionConfig(
            top_k=min(config.execution_top_k, len(instruments)),
            initial_nav=config.initial_nav,
            commission_bps=config.commission_bps,
            sell_tax_bps=config.sell_tax_bps,
            slippage_bps=config.slippage_bps,
            impact_coefficient_bps=config.impact_coefficient_bps,
            max_participation_rate=config.max_participation_rate,
            placebo_repetitions=config.placebo_repetitions,
            max_placebo_p_value=config.max_placebo_p_value,
            min_dsr_probability=config.min_dsr_probability,
            maximum_pbo=config.maximum_pbo,
        )
        execution, execution_reports = run_discovery_execution(
            registry,
            campaign,
            cpcv,
            candidates,
            observations,
            snapshot_id=snapshot_id,
            code_version=code_version,
            window=window,
            horizon_sessions=HORIZON_SESSIONS[config.horizon],
            config=execution_config,
            seed=config.seed,
        )
        if stress_registrations:
            candidate_by_fingerprint = {
                item.schema.fingerprint: item for item in candidates if item.unique
            }
            executed = {item.fingerprint for item in execution.configurations}
            preferred = next(
                (
                    item.schema.fingerprint
                    for item in candidates
                    if item.schema.schema_id.startswith("flow_price_divergence_parent")
                    and item.schema.fingerprint in executed
                ),
                execution.selected_fingerprint,
            )
            target = candidate_by_fingerprint[preferred]
            stability_diagnostics = run_stability_diagnostics(
                registry,
                schema=target.schema,
                rows=observations[preferred],
                bars=dataset.bars,
                registrations=stress_registrations,
                snapshot_id=snapshot_id,
                experiment_id=experiment_id,
                code_version=code_version,
                horizon_sessions=HORIZON_SESSIONS[config.horizon],
                regime_lookback=config.regime_lookback,
                execution_config=execution_config,
            )
    alternative_audits = tuple(
        dataset.audit for _, dataset in sorted(alternative_datasets.items())
    )
    decision = (
        execution.decision
        if execution is not None
        else cpcv.decision
        if cpcv is not None
        else "REJECT_SCREEN_INSUFFICIENT_CPCV_CANDIDATES"
    )
    report = AutomatedDiscoveryReport(
        method_version=(
            "v1.8.18-flow-stability-1.0.0"
            if config.search_profile == "v1.8.18"
            else "v1.8.17-normalized-multisource-1.0.0"
            if config.search_profile == "v1.8.17"
            else AUTOMATED_DISCOVERY_VERSION
        ),
        experiment_id=experiment_id,
        campaign_id=campaign.campaign_id,
        snapshot_id=snapshot_id,
        source_snapshot_sha256=source_manifest.snapshot_sha256,
        generated_candidates=len(candidates),
        unique_candidates=sum(item.unique for item in candidates),
        screening=screening,
        cpcv=cpcv,
        execution=execution,
        stability_diagnostics=stability_diagnostics,
        alternative_audits=alternative_audits,
        dynamic_universe_sha256=dynamic_sha256,
        dynamic_universe_unique_members=(len(instruments) if dynamic_memberships else None),
        dynamic_universe_top_n=(config.dynamic_universe_top_n if dynamic_memberships else None),
        validation_window_opened=False,
        test_window_opened=False,
        decision=decision,
    )
    research_memory = build_research_memory(
        candidates,
        screening,
        cpcv,
        execution,
        experiment_id=experiment_id,
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "automated-discovery.json"
    markdown_en_path = output / "automated-discovery.en.md"
    markdown_zh_path = output / "automated-discovery.zh.md"
    schemas_path = output / "generated-schemas.json"
    memory_json_path = output / "research-memory.json"
    memory_en_path = output / "research-memory.en.md"
    memory_zh_path = output / "research-memory.zh.md"
    stability_json_path = output / "stability-diagnostics.json"
    stability_en_path = output / "stability-diagnostics.en.md"
    stability_zh_path = output / "stability-diagnostics.zh.md"
    json_sha = _write(json_path, report.to_json() + "\n")
    en_sha = _write(markdown_en_path, report.to_markdown("en"))
    zh_sha = _write(markdown_zh_path, report.to_markdown("zh"))
    schemas_sha = _write(
        schemas_path,
        json.dumps(
            [json.loads(item.schema.to_json()) for item in candidates],
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
    )
    memory_json_sha = _write(memory_json_path, research_memory.to_json() + "\n")
    memory_en_sha = _write(memory_en_path, research_memory.to_markdown("en"))
    memory_zh_sha = _write(memory_zh_path, research_memory.to_markdown("zh"))
    stability_artifacts: tuple[tuple[str, Path, str], ...] = ()
    if stability_diagnostics is not None:
        stability_artifacts = (
            (
                "stability_diagnostics_json",
                stability_json_path,
                _write(stability_json_path, stability_diagnostics.to_json() + "\n"),
            ),
            (
                "stability_diagnostics_markdown_en",
                stability_en_path,
                _write(stability_en_path, stability_diagnostics.to_markdown("en")),
            ),
            (
                "stability_diagnostics_markdown_zh",
                stability_zh_path,
                _write(stability_zh_path, stability_diagnostics.to_markdown("zh")),
            ),
        )
    first_trial = screening.scores[0].trial_id
    for fingerprint, baseline_report in execution_reports.items():
        artifacts = write_baseline_report(baseline_report, output / "execution")
        if fingerprint == "__walk_forward__":
            trial_id = execution.alpha_court.lineage.trial_id  # type: ignore[union-attr]
            artifact_prefix = "walk_forward"
        else:
            trial_id = next(
                score.trial_id
                for score in execution.configurations  # type: ignore[union-attr]
                if score.fingerprint == fingerprint
            )
            artifact_prefix = "execution_baseline"
        registry.register_artifact(
            trial_id=trial_id,
            kind=f"{artifact_prefix}_json",
            path=str(artifacts.json_path),
            sha256=artifacts.json_sha256,
        )
        registry.register_artifact(
            trial_id=trial_id,
            kind=f"{artifact_prefix}_markdown",
            path=str(artifacts.markdown_path),
            sha256=artifacts.markdown_sha256,
        )
    if execution is not None:
        court_artifacts = write_alpha_court_report(
            execution.alpha_court, output / "falsification"
        )
        winning_trial = next(
            score.trial_id
            for score in execution.configurations
            if score.fingerprint == execution.selected_fingerprint
        )
        registry.register_artifact(
            trial_id=winning_trial,
            kind="alpha_court_json",
            path=str(court_artifacts.json_path),
            sha256=court_artifacts.json_sha256,
        )
        registry.register_artifact(
            trial_id=winning_trial,
            kind="alpha_court_markdown",
            path=str(court_artifacts.markdown_path),
            sha256=court_artifacts.markdown_sha256,
        )
        winning_schema = next(
            item.schema
            for item in candidates
            if item.schema.fingerprint == execution.selected_fingerprint
        )
        alpha_card = build_alpha_card(
            winning_schema,
            screening,
            cpcv,  # type: ignore[arg-type]
            execution,
            execution_reports[execution.selected_fingerprint],
        )
        alpha_card_path = output / "alpha-card.json"
        alpha_card_sha = _write(alpha_card_path, alpha_card.to_json() + "\n")
        registry.register_artifact(
            trial_id=winning_trial,
            kind="alpha_card_json",
            path=str(alpha_card_path),
            sha256=alpha_card_sha,
        )
        portfolio_gate_path = output / "portfolio-gate.json"
        try:
            portfolio_payload = authorize_portfolio_signal(alpha_card).to_json() + "\n"
            portfolio_kind = "portfolio_signal_json"
        except ValueError as exc:
            portfolio_payload = json.dumps(
                {
                    "authorized": False,
                    "fingerprint": alpha_card.fingerprint,
                    "reason": str(exc),
                },
                indent=2,
                sort_keys=True,
            ) + "\n"
            portfolio_kind = "portfolio_gate_rejection_json"
        portfolio_sha = _write(portfolio_gate_path, portfolio_payload)
        registry.register_artifact(
            trial_id=winning_trial,
            kind=portfolio_kind,
            path=str(portfolio_gate_path),
            sha256=portfolio_sha,
        )
    for kind, path, digest in (
        ("automated_discovery_json", json_path, json_sha),
        ("automated_discovery_markdown_en", markdown_en_path, en_sha),
        ("automated_discovery_markdown_zh", markdown_zh_path, zh_sha),
        ("automated_discovery_schemas", schemas_path, schemas_sha),
        ("research_memory_json", memory_json_path, memory_json_sha),
        ("research_memory_markdown_en", memory_en_path, memory_en_sha),
        ("research_memory_markdown_zh", memory_zh_path, memory_zh_sha),
        *stability_artifacts,
    ):
        registry.register_artifact(trial_id=first_trial, kind=kind, path=str(path), sha256=digest)
    return AutomatedDiscoveryRun(
        report, json_path, markdown_en_path, markdown_zh_path, schemas_path
    )
