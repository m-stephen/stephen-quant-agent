from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.falsification import deflated_sharpe_ratio, run_placebo
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import (
    build_composite_snapshot_manifest,
    build_selected_files_snapshot_manifest,
)
from stephen_quant.qmt import (
    QdAlternativeConfig,
    load_qd_alternative_directory,
    load_qd_daily_directory,
    select_qd_daily_files,
)

from .price_discovery_lab import _execution_memberships, _load_memberships
from .v41_semantic_alpha import (
    UsageSpec,
    V41Config,
    _anchors,
    classify_prior_regimes,
    evaluate_usage,
    evaluate_usage_events,
)
from .v43_conversion import _schemas
from .v44_path_robust_alpha import PathRobustness, _build_panel, summarize_paths

V45_VERSION = "v4.5-candidate-level-forward-validation-1.0.0"
FROZEN_CANDIDATE_ID = "limit_up_persistence_20_inverse_20_20d"
FROZEN_USAGE = "AVOID"
FROZEN_BREADTH = 10
FROZEN_REGIME = "mixed"


@dataclass(frozen=True)
class V45Config:
    data_start: str = "2021-01-01"
    validation_year: int = 2025
    membership_frozen_as_of: str = "2024-12-31"
    horizon: int = 20
    universe_top_n: int = 50
    primary_nav: float = 3_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_bps: float = 10.0
    participation_rate: float = 0.05
    stress_navs: tuple[float, ...] = (3_000_000.0, 10_000_000.0, 20_000_000.0)
    stress_cost_multipliers: tuple[float, ...] = (1.0, 2.0, 3.0)
    stress_breadths: tuple[int, ...] = (5, 10, 15)
    minimum_portfolio_sharpe: float = 0.50
    minimum_median_path_sharpe: float = 0.50
    minimum_positive_paths: int = 16
    maximum_drawdown: float = 0.15
    minimum_positive_stress_fraction: float = 0.75
    minimum_dsr: float = 0.95
    maximum_placebo_p: float = 0.05
    placebo_repetitions: int = 199
    ingested_at: str = "2026-08-18T00:00:00+08:00"
    seed: int = 42

    def validate(self) -> None:
        if self.validation_year != 2025 or self.membership_frozen_as_of != "2024-12-31":
            raise ValueError("V4.5 validation year and membership cutoff are frozen")
        if self.horizon != 20 or self.primary_nav != 3_000_000.0:
            raise ValueError("V4.5 horizon and primary NAV are frozen")
        if self.stress_navs != (3_000_000.0, 10_000_000.0, 20_000_000.0):
            raise ValueError("V4.5 NAV stress grid is frozen")
        if self.stress_cost_multipliers != (1.0, 2.0, 3.0):
            raise ValueError("V4.5 cost stress grid is frozen")
        if self.stress_breadths != (5, 10, 15):
            raise ValueError("V4.5 breadth stress grid is frozen")


@dataclass(frozen=True)
class StressResult:
    nav: float
    cost_multiplier: float
    breadth: int
    metrics: PathRobustness
    capacity_clipped_notional: float
    mean_turnover: float
    trial_id: str
    trial_number: int

    @property
    def primary(self) -> bool:
        return self.nav == 3_000_000.0 and self.cost_multiplier == 1.0 and self.breadth == 10


@dataclass(frozen=True)
class V45Report:
    method_version: str
    experiment_id: str
    snapshot_id: str
    snapshot_sha256: str
    candidate_id: str
    validation_year: int
    membership_policy: str
    project_level_holdout_status: str
    candidate_level_holdout_status: str
    stress_trials: int
    primary: StressResult
    positive_stress_cells: int
    stress_pass_fraction: float
    double_cost_primary_breadth_return: float
    triple_cost_primary_breadth_return: float
    twenty_million_primary_cost_return: float
    dsr_probability: float
    signal_placebo_p: float
    return_placebo_p: float
    recorded_trial_count: int
    decision: str
    failures: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"zh", "en"}:
            raise ValueError("language must be zh or en")
        zh = language == "zh"
        m = self.primary.metrics
        lines = [
            "# V4.5 候选级 2025 验证" if zh else "# V4.5 Candidate-Level 2025 Validation",
            "",
            f"**{'结论' if zh else 'Decision'}: `{self.decision}`**",
            "",
            f"- {'候选' if zh else 'Candidate'}: `{self.candidate_id}`",
            f"- {'股票池策略' if zh else 'Universe policy'}: {self.membership_policy}",
            f"- {'压力测试通过率' if zh else 'Positive stress fraction'}: {self.stress_pass_fraction:.2%}",
            f"- DSR: {self.dsr_probability:.6f}",
            (
                f"- {'置换 p 值' if zh else 'Placebo p-values'}: "
                f"{self.signal_placebo_p:.6f} / {self.return_placebo_p:.6f}"
            ),
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Portfolio excess Sharpe | {m.portfolio_excess_sharpe:.4f} |",
            f"| Portfolio excess return | {m.portfolio_excess_return:.2%} |",
            f"| Incremental return | {m.incremental_return:.2%} |",
            f"| Median / Q25 path Sharpe | {m.median_sharpe:.4f} / {m.lower_quartile_sharpe:.4f} |",
            f"| Positive paths | {m.positive_return_paths}/{m.paths} |",
            f"| Drawdown | {m.portfolio_drawdown:.2%} |",
            f"| 2x cost return | {self.double_cost_primary_breadth_return:.2%} |",
            f"| 3x cost return | {self.triple_cost_primary_breadth_return:.2%} |",
            f"| CNY 20m return | {self.twenty_million_primary_cost_return:.2%} |",
            "",
            (
                f"- {'失败门禁' if zh else 'Failed gates'}: "
                f"{', '.join(self.failures) or ('无' if zh else 'none')}"
            ),
            "",
        ]
        return "\n".join(lines)


def primary_result(results: tuple[StressResult, ...]) -> StressResult:
    matches = [item for item in results if item.primary]
    if len(matches) != 1:
        raise ValueError("V4.5 requires exactly one primary stress cell")
    return matches[0]


def _trial(
    registry: ExperimentRegistry,
    experiment_id: str,
    *,
    nav: float,
    multiplier: float,
    breadth: int,
    seed: int,
) -> tuple[str, int]:
    return registry.create_trial(
        TrialSpec(
            experiment_id,
            "v4.5_2025_candidate_validation",
            f"{FROZEN_CANDIDATE_ID}:{FROZEN_USAGE.lower()}_breadth{breadth}_{FROZEN_REGIME}",
            json.dumps(
                {"nav": nav, "cost_multiplier": multiplier, "breadth": breadth},
                sort_keys=True,
                separators=(",", ":"),
            ),
            seed,
            "2022-01-01",
            "2024-12-31",
            "2025-01-01",
            "2025-12-31",
            "2026-01-01",
            "2026-12-31",
        )
    )


def run_v45_candidate_validation(
    daily_dir: str | Path,
    membership_path: str | Path,
    *,
    limit_event_dir: str | Path,
    registry: ExperimentRegistry,
    output_dir: str | Path,
    code_version: str,
    config: V45Config | None = None,
    prior_inferential_trials: int = 1022,
) -> V45Report:
    config = config or V45Config()
    config.validate()
    if prior_inferential_trials < 0:
        raise ValueError("prior_inferential_trials cannot be negative")
    memberships, membership_sha = _load_memberships(membership_path, config.universe_top_n)
    if max(memberships) != config.membership_frozen_as_of:
        raise ValueError("membership source must end at the frozen 2024-12-31 cutoff")
    instruments = tuple(sorted({item for members in memberships.values() for item in members}))
    root = Path(daily_dir).expanduser().resolve()
    files = select_qd_daily_files(root, start_date=config.data_start, end_date="2025-12-31")
    daily_manifest = build_selected_files_snapshot_manifest(root, files)
    daily = load_qd_daily_directory(
        root, start_date=config.data_start, end_date="2025-12-31", instruments=instruments
    )
    alternative = load_qd_alternative_directory(
        limit_event_dir,
        QdAlternativeConfig(
            source_kind="limit_event",
            start_date="2022-01-01",
            end_date="2025-12-31",
            ingested_at=config.ingested_at,
            instruments=instruments,
        ),
    )
    composite = build_composite_snapshot_manifest(
        {
            "qd_daily": daily_manifest.snapshot_sha256,
            "dynamic_universe_frozen_2024_12_31": membership_sha,
            "qd_limit_event": alternative.audit.source_sha256,
        }
    )
    snapshot_id = registry.register_snapshot(
        composite,
        vendor_version=V45_VERSION,
        notes="candidate-level 2025 validation; project-level reused year; 2024-end universe frozen",
    )
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            "V4.5 frozen candidate-level 2025 validation",
            "The V4.4 mixed-regime weakest-stock avoidance overlay remains positive under 2025 and stress tests.",
            snapshot_id,
            code_version,
            json.dumps({"version": V45_VERSION, "config": asdict(config)}, sort_keys=True),
        )
    )
    calendar = tuple(sorted({item.trade_date for item in daily.bars}))
    by_instrument = defaultdict(dict)
    for bar in daily.bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
    execution_members = _execution_memberships(memberships, calendar)
    regime_config = V41Config(ingested_at=config.ingested_at)
    regimes = classify_prior_regimes(
        calendar=calendar,
        bars=by_instrument,
        execution_members=execution_members,
        config=regime_config,
    )
    anchors = _anchors(
        year=config.validation_year,
        horizon=config.horizon,
        calendar=calendar,
        bars=by_instrument,
        execution_members=execution_members,
    )
    schema = _schemas()[FROZEN_CANDIDATE_ID]
    rows = _build_panel(
        schema,
        year=config.validation_year,
        bars=daily.bars,
        alternatives={"qd_limit_event": alternative.observations},
        anchors=anchors,
    )
    if not rows:
        raise ValueError("V4.5 2025 panel is empty")
    results: list[StressResult] = []
    raw_sharpes: list[float] = []
    for nav in config.stress_navs:
        for multiplier in config.stress_cost_multipliers:
            for breadth in config.stress_breadths:
                usage_config = V41Config(
                    primary_nav=nav,
                    commission_bps=config.commission_bps * multiplier,
                    sell_tax_bps=config.sell_tax_bps * multiplier,
                    slippage_bps=config.slippage_bps * multiplier,
                    impact_bps=config.impact_bps * multiplier,
                    participation_rate=config.participation_rate,
                    ingested_at=config.ingested_at,
                )
                spec = UsageSpec(FROZEN_USAGE, breadth, FROZEN_REGIME)
                trial = _trial(
                    registry,
                    experiment_id,
                    nav=nav,
                    multiplier=multiplier,
                    breadth=breadth,
                    seed=config.seed,
                )
                candidate_events, clipped = evaluate_usage_events(
                    rows,
                    rows,
                    spec,
                    horizon=config.horizon,
                    nav=nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes=regimes,
                    config=usage_config,
                    hold_equal_weight_when_inactive=True,
                )
                controls, _ = evaluate_usage_events(
                    rows,
                    rows,
                    UsageSpec("AVOID", 0, "all"),
                    horizon=config.horizon,
                    nav=nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes=regimes,
                    config=usage_config,
                )
                portfolio, _ = evaluate_usage(
                    FROZEN_CANDIDATE_ID,
                    rows,
                    rows,
                    spec,
                    year=config.validation_year,
                    horizon=config.horizon,
                    nav=nav,
                    bars=by_instrument,
                    calendar=calendar,
                    regimes=regimes,
                    config=usage_config,
                    hold_equal_weight_when_inactive=True,
                )
                metrics = summarize_paths(
                    config.validation_year,
                    candidate_events,
                    controls,
                    horizon=config.horizon,
                    portfolio_sharpe=portfolio.excess_sharpe,
                    portfolio_return=portfolio.cumulative_excess_return,
                    portfolio_drawdown=portfolio.maximum_drawdown,
                )
                result = StressResult(
                    nav,
                    multiplier,
                    breadth,
                    metrics,
                    clipped,
                    portfolio.mean_turnover,
                    trial[0],
                    trial[1],
                )
                registry.record_trial_result(trial[0], json.dumps(asdict(result), sort_keys=True))
                results.append(result)
                raw_sharpes.append(portfolio.excess_sharpe / math.sqrt(252))
    frozen_primary = primary_result(tuple(results))
    primary_metrics = frozen_primary.metrics
    recorded = prior_inferential_trials + registry.global_trial_count()
    dsr = deflated_sharpe_ratio(
        observed_sharpe=primary_metrics.portfolio_excess_sharpe / math.sqrt(252),
        trial_sharpes=raw_sharpes,
        recorded_trial_count=recorded,
        observations=max(len({row.timestamp[:10] for row in rows}), 2),
    )
    mixed_rows = tuple(
        row
        for row in rows
        if regimes.get(row.timestamp[:10]) is not None
        and regimes[row.timestamp[:10]].state == FROZEN_REGIME
    )
    signal_placebo = run_placebo(
        mixed_rows,
        horizon="20d",
        direction=1,
        method="signal_shuffle",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    )
    return_placebo = run_placebo(
        mixed_rows,
        horizon="20d",
        direction=1,
        method="return_permutation",
        seed=config.seed,
        repetitions=config.placebo_repetitions,
        min_cross_section=10,
    )
    positive = sum(
        item.metrics.portfolio_excess_return > 0 and item.metrics.incremental_return > 0
        for item in results
    )
    stress_fraction = positive / len(results)
    lookup = {(item.nav, item.cost_multiplier, item.breadth): item for item in results}
    double_cost = lookup[(config.primary_nav, 2.0, FROZEN_BREADTH)].metrics.portfolio_excess_return
    triple_cost = lookup[(config.primary_nav, 3.0, FROZEN_BREADTH)].metrics.portfolio_excess_return
    twenty_million = lookup[(20_000_000.0, 1.0, FROZEN_BREADTH)].metrics.portfolio_excess_return
    failures = []
    if primary_metrics.portfolio_excess_sharpe < config.minimum_portfolio_sharpe:
        failures.append("portfolio_sharpe")
    if primary_metrics.portfolio_excess_return <= 0 or primary_metrics.incremental_return <= 0:
        failures.append("portfolio_return")
    if primary_metrics.median_sharpe < config.minimum_median_path_sharpe:
        failures.append("median_path_sharpe")
    if primary_metrics.positive_return_paths < config.minimum_positive_paths:
        failures.append("positive_paths")
    if primary_metrics.portfolio_drawdown < -config.maximum_drawdown:
        failures.append("drawdown")
    if stress_fraction < config.minimum_positive_stress_fraction:
        failures.append("stress_robustness")
    if double_cost <= 0 or triple_cost <= 0 or twenty_million <= 0:
        failures.append("cost_or_capacity_stress")
    if dsr.probability < config.minimum_dsr:
        failures.append("multiplicity_dsr")
    if signal_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("signal_placebo")
    if return_placebo.empirical_p_value > config.maximum_placebo_p:
        failures.append("return_placebo")
    report = V45Report(
        V45_VERSION,
        experiment_id,
        snapshot_id,
        composite.snapshot_sha256,
        FROZEN_CANDIDATE_ID,
        config.validation_year,
        "freeze 2024-12-31 top-50 membership through 2025; no future constituent backfill",
        "reused/contaminated by earlier project research",
        "unopened for this frozen candidate before V4.5",
        len(results),
        frozen_primary,
        positive,
        stress_fraction,
        double_cost,
        triple_cost,
        twenty_million,
        dsr.probability,
        signal_placebo.empirical_p_value,
        return_placebo.empirical_p_value,
        recorded,
        "PASS_ALPHA_COURT" if not failures else "REJECT_ALPHA_COURT",
        tuple(failures),
    )
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "v4.5-candidate-validation.json").write_text(
        report.to_json() + "\n", encoding="utf-8"
    )
    (output / "v4.5-candidate-validation.zh.md").write_text(
        report.to_markdown("zh"), encoding="utf-8"
    )
    (output / "v4.5-candidate-validation.en.md").write_text(
        report.to_markdown("en"), encoding="utf-8"
    )
    return report
