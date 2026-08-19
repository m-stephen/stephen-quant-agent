from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from statistics import stdev

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.evaluation import EvaluationObservation, spearman_correlation
from stephen_quant.falsification import (
    AlphaCourtReport,
    AuditThresholds,
    FalsificationLineage,
    build_alpha_court_report,
    deflated_sharpe_ratio,
    run_placebo,
    run_rank_placebo_fast,
)
from stephen_quant.integrity.models import TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry

from .campaign import SearchCampaign
from .cpcv import DiscoveryCpcvReport
from .generator import GeneratedCandidate
from .screening import ScreeningWindow

EXECUTION_DISCOVERY_VERSION = "v1.8.16-generated-factor-execution-1.0.0"


@dataclass(frozen=True)
class DiscoveryExecutionConfig:
    top_k: int = 5
    initial_nav: float = 1_000_000.0
    commission_bps: float = 3.0
    sell_tax_bps: float = 5.0
    slippage_bps: float = 5.0
    impact_coefficient_bps: float = 10.0
    max_participation_rate: float = 0.05
    placebo_repetitions: int = 199
    max_placebo_p_value: float = 0.05
    min_dsr_probability: float = 0.95
    maximum_pbo: float = 0.20
    walk_forward_blocks: int = 6
    minimum_annualized_sharpe: float | None = None
    maximum_drawdown: float | None = None
    all_candidate_court: bool = False
    doubled_cost_multiplier: float = 2.0
    minimum_candidate_positive_paths: int | None = None

    def validate(self) -> None:
        if self.top_k < 1:
            raise ValueError("execution top_k must be positive")
        if not math.isfinite(self.initial_nav) or self.initial_nav <= 0:
            raise ValueError("execution initial_nav must be finite and positive")
        if self.placebo_repetitions < 1:
            raise ValueError("placebo_repetitions must be positive")
        if not 0 < self.max_placebo_p_value < 1:
            raise ValueError("max_placebo_p_value must be between zero and one")
        if not 0 < self.min_dsr_probability < 1:
            raise ValueError("min_dsr_probability must be between zero and one")
        if not 0 <= self.maximum_pbo < 1:
            raise ValueError("maximum_pbo must be in [0, 1)")
        if self.walk_forward_blocks < 3:
            raise ValueError("walk_forward_blocks must be at least three")
        if self.minimum_annualized_sharpe is not None and not math.isfinite(
            self.minimum_annualized_sharpe
        ):
            raise ValueError("minimum_annualized_sharpe must be finite when configured")
        if self.maximum_drawdown is not None and not 0 < self.maximum_drawdown < 1:
            raise ValueError("maximum_drawdown must be in (0, 1) when configured")
        if not math.isfinite(self.doubled_cost_multiplier) or self.doubled_cost_multiplier < 1:
            raise ValueError("doubled_cost_multiplier must be finite and at least one")
        if (
            self.minimum_candidate_positive_paths is not None
            and self.minimum_candidate_positive_paths < 1
        ):
            raise ValueError("minimum_candidate_positive_paths must be positive")
        if any(
            not math.isfinite(value) or value < 0
            for value in (
                self.commission_bps,
                self.sell_tax_bps,
                self.slippage_bps,
                self.impact_coefficient_bps,
            )
        ):
            raise ValueError("execution costs must be finite and non-negative")
        if not 0 < self.max_participation_rate <= 1:
            raise ValueError("max_participation_rate must be in (0, 1]")


@dataclass(frozen=True)
class ExecutionCandidateScore:
    schema_id: str
    fingerprint: str
    trial_id: str
    trial_number: int
    periods: int
    raw_net_sharpe: float
    annualized_net_sharpe: float | None
    net_total_return: float
    max_drawdown: float
    total_cost: float
    capacity_clipped_notional: float = 0.0
    doubled_cost_trial_id: str | None = None
    doubled_cost_annualized_net_sharpe: float | None = None
    doubled_cost_net_total_return: float | None = None
    doubled_cost_max_drawdown: float | None = None
    doubled_cost_total_cost: float | None = None
    doubled_cost_capacity_clipped_notional: float | None = None


@dataclass(frozen=True)
class CandidateCourtScore:
    schema_id: str
    fingerprint: str
    alpha_court: AlphaCourtReport
    empirical_skewness: float
    empirical_excess_kurtosis: float
    economic_checks: tuple[tuple[str, bool], ...]
    passed: bool


@dataclass(frozen=True)
class DiscoveryExecutionReport:
    method_version: str
    campaign_id: str
    experiment_id: str
    configurations: tuple[ExecutionCandidateScore, ...]
    selected_fingerprint: str
    alpha_court: AlphaCourtReport
    candidate_courts: tuple[CandidateCourtScore, ...]
    walk_forward: WalkForwardSummary
    decision: str


@dataclass(frozen=True)
class WalkForwardBlock:
    block_number: int
    train_start: str
    train_end: str
    deploy_start: str
    deploy_end: str
    selected_fingerprint: str
    training_mean_rank_ic: float


@dataclass(frozen=True)
class WalkForwardSummary:
    method_version: str
    blocks: tuple[WalkForwardBlock, ...]
    periods: int
    net_total_return: float
    annualized_net_sharpe: float | None
    max_drawdown: float
    total_cost: float
    passed: bool


def _non_overlapping(
    observations: tuple[BaselineObservation, ...],
    horizon_sessions: int,
    minimum_eligible: int = 1,
) -> tuple[BaselineObservation, ...]:
    eligible_by_date: dict[str, int] = defaultdict(int)
    for row in observations:
        if row.eligible:
            eligible_by_date[row.execution_at] += 1
    dates = sorted(
        day for day, eligible in eligible_by_date.items() if eligible >= minimum_eligible
    )
    if not dates:
        raise ValueError(
            f"no execution cross-section has at least {minimum_eligible} eligible assets"
        )
    selected = set(dates[::horizon_sessions])
    return tuple(row for row in observations if row.execution_at in selected)


def _raw_sharpe(report: BaselineReport) -> float:
    returns = [period.net_return for period in report.periods]
    if len(returns) < 2:
        raise ValueError("execution DSR requires at least two portfolio returns")
    dispersion = stdev(returns)
    if dispersion == 0:
        return 0.0
    return (sum(returns) / len(returns)) / dispersion


def _empirical_moments(report: BaselineReport) -> tuple[float, float]:
    returns = [period.net_return for period in report.periods]
    if len(returns) < 4:
        return 0.0, 0.0
    average = sum(returns) / len(returns)
    centered = [value - average for value in returns]
    second = sum(value**2 for value in centered) / len(centered)
    if second <= 0:
        return 0.0, 0.0
    third = sum(value**3 for value in centered) / len(centered)
    fourth = sum(value**4 for value in centered) / len(centered)
    return third / second**1.5, fourth / second**2 - 3.0


def _evaluation_rows(
    observations: tuple[BaselineObservation, ...], horizon: str
) -> tuple[EvaluationObservation, ...]:
    return tuple(
        EvaluationObservation(
            instrument=row.instrument,
            timestamp=row.execution_at,
            factor_value=row.signal,
            forward_return=row.forward_return,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            horizon=horizon,
            subperiod="research",
            regime="unspecified",
        )
        for row in observations
        if row.eligible
    )


def _training_rank_ic(
    rows: tuple[BaselineObservation, ...], dates: set[str], direction: int
) -> float:
    grouped: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in rows:
        day = row.execution_at[:10]
        if day in dates and row.eligible:
            grouped[day].append(row)
    values = []
    for day in sorted(grouped):
        cross_section = sorted(grouped[day], key=lambda row: row.instrument)
        if len(cross_section) < 3:
            continue
        signals = [direction * row.signal for row in cross_section]
        returns = [row.forward_return for row in cross_section]
        if len(set(signals)) < 2 or len(set(returns)) < 2:
            continue
        values.append(
            spearman_correlation(
                signals,
                returns,
            )
        )
    if not values:
        raise ValueError("walk-forward training block has no valid cross-section")
    return sum(values) / len(values)


def _walk_forward(
    ranked_fingerprints: tuple[str, ...],
    candidate_by_fingerprint: dict[str, GeneratedCandidate],
    observations: dict[str, tuple[BaselineObservation, ...]],
    *,
    lineage: BaselineLineage,
    horizon_sessions: int,
    config: DiscoveryExecutionConfig,
) -> tuple[WalkForwardSummary, BaselineReport]:
    common_keys = set.intersection(
        *(
            {(row.execution_at, row.instrument) for row in observations[fingerprint]}
            for fingerprint in ranked_fingerprints
        )
    )
    common_dates = {
        row.execution_at[:10]
        for row in observations[ranked_fingerprints[0]]
        if row.eligible and (row.execution_at, row.instrument) in common_keys
    }
    dates = sorted(common_dates)
    if len(dates) < config.walk_forward_blocks * 2:
        raise ValueError("walk-forward research history is too short for configured blocks")
    width, remainder = divmod(len(dates), config.walk_forward_blocks)
    blocks: list[list[str]] = []
    offset = 0
    for block_index in range(config.walk_forward_blocks):
        size = width + (1 if block_index < remainder else 0)
        blocks.append(dates[offset : offset + size])
        offset += size

    selections: list[WalkForwardBlock] = []
    deployment_rows: list[BaselineObservation] = []
    for block_index in range(1, len(blocks)):
        train_dates = {day for block in blocks[:block_index] for day in block}
        deploy_dates = set(blocks[block_index])
        scores = {
            fingerprint: _training_rank_ic(
                observations[fingerprint],
                train_dates,
                candidate_by_fingerprint[fingerprint].schema.direction,
            )
            for fingerprint in ranked_fingerprints
        }
        selected = max(scores, key=lambda fingerprint: (scores[fingerprint], fingerprint))
        direction = candidate_by_fingerprint[selected].schema.direction
        selections.append(
            WalkForwardBlock(
                block_number=block_index,
                train_start=min(train_dates),
                train_end=max(train_dates),
                deploy_start=min(deploy_dates),
                deploy_end=max(deploy_dates),
                selected_fingerprint=selected,
                training_mean_rank_ic=scores[selected],
            )
        )
        deployment_rows.extend(
            replace(row, signal=direction * row.signal)
            for row in observations[selected]
            if row.execution_at[:10] in deploy_dates
            and (row.execution_at, row.instrument) in common_keys
        )
    replay = run_momentum_topk(
        _non_overlapping(tuple(deployment_rows), horizon_sessions, config.top_k),
        lineage,
        BaselineConfig(
            top_k=config.top_k,
            direction=1,
            commission_bps=config.commission_bps,
            sell_tax_bps=config.sell_tax_bps,
            slippage_bps=config.slippage_bps,
            impact_coefficient_bps=config.impact_coefficient_bps,
            max_participation_rate=config.max_participation_rate,
            periods_per_year=max(1, 252 // horizon_sessions),
            missing_holding_policy="stale_zero_return",
        ),
        initial_nav=config.initial_nav,
    )
    passed = (
        replay.metrics.net_sharpe is not None
        and replay.metrics.net_sharpe > 0
        and (
            config.minimum_annualized_sharpe is None
            or replay.metrics.net_sharpe >= config.minimum_annualized_sharpe
        )
        and (
            config.maximum_drawdown is None
            or replay.metrics.max_drawdown >= -config.maximum_drawdown
        )
    )
    return (
        WalkForwardSummary(
            method_version="expanding-window-factor-selection-1.0.0",
            blocks=tuple(selections),
            periods=replay.metrics.periods,
            net_total_return=replay.metrics.net_total_return,
            annualized_net_sharpe=replay.metrics.net_sharpe,
            max_drawdown=replay.metrics.max_drawdown,
            total_cost=replay.metrics.total_cost,
            passed=passed,
        ),
        replay,
    )


def run_discovery_execution(
    registry: ExperimentRegistry,
    campaign: SearchCampaign,
    cpcv: DiscoveryCpcvReport,
    candidates: tuple[GeneratedCandidate, ...],
    observations: dict[str, tuple[BaselineObservation, ...]],
    *,
    snapshot_id: str,
    code_version: str,
    window: ScreeningWindow,
    horizon_sessions: int,
    config: DiscoveryExecutionConfig,
    seed: int = 42,
    prior_inferential_trials: int = 0,
) -> tuple[DiscoveryExecutionReport, dict[str, BaselineReport]]:
    """Run a bounded cost-aware execution tournament and the final Alpha Court."""

    config.validate()
    if prior_inferential_trials < 0:
        raise ValueError("prior_inferential_trials cannot be negative")
    if not cpcv.signal_gate_passed and not (
        config.all_candidate_court and cpcv.hygiene_passed
    ):
        raise ValueError("execution is forbidden before the CPCV signal gate passes")
    if campaign.spec.budget.execution < 2:
        raise ValueError("execution budget must be at least two for DSR multiplicity evidence")
    candidate_by_fingerprint = {item.schema.fingerprint: item for item in candidates}
    ranked = sorted(
        cpcv.configurations,
        key=lambda item: (item.mean_path_rank_ic, item.fingerprint),
        reverse=True,
    )[: campaign.spec.budget.execution]
    if len(ranked) < 2:
        raise ValueError("execution tournament requires at least two CPCV configurations")

    reports: dict[str, BaselineReport] = {}
    scores: list[ExecutionCandidateScore] = []
    for cpcv_score in ranked:
        item = candidate_by_fingerprint[cpcv_score.fingerprint]
        schema = item.schema
        trial_id, trial_number = registry.create_trial(
            TrialSpec(
                experiment_id=campaign.spec.experiment_id,
                model_name="v1.8.16_cost_aware_topk_execution",
                factor_set=schema.schema_id,
                hyperparams=json.dumps(
                    {
                        "campaign_id": campaign.campaign_id,
                        "fingerprint": schema.fingerprint,
                        "execution": asdict(config),
                        "horizon_sessions": horizon_sessions,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                seed=seed,
                train_start=window.research_start,
                train_end=window.research_end,
                validation_start=window.validation_start,
                validation_end=window.validation_end,
                test_start=window.test_start,
                test_end=window.test_end,
            )
        )
        execution_rows = _non_overlapping(
            observations[schema.fingerprint], horizon_sessions, config.top_k
        )
        baseline_config = BaselineConfig(
            top_k=config.top_k,
            direction=schema.direction,
            commission_bps=config.commission_bps,
            sell_tax_bps=config.sell_tax_bps,
            slippage_bps=config.slippage_bps,
            impact_coefficient_bps=config.impact_coefficient_bps,
            max_participation_rate=config.max_participation_rate,
            periods_per_year=max(1, 252 // horizon_sessions),
            missing_holding_policy="stale_zero_return",
        )
        report = run_momentum_topk(
            execution_rows,
            BaselineLineage(
                schema.schema_id,
                schema.version,
                snapshot_id,
                campaign.spec.experiment_id,
                trial_id,
                code_version,
            ),
            baseline_config,
            initial_nav=config.initial_nav,
        )
        doubled_trial_id = None
        doubled_report = None
        if config.all_candidate_court:
            doubled_trial_id, _ = registry.create_trial(
                TrialSpec(
                    experiment_id=campaign.spec.experiment_id,
                    model_name="v7.3_doubled_cost_topk_execution",
                    factor_set=schema.schema_id,
                    hyperparams=json.dumps(
                        {
                            "campaign_id": campaign.campaign_id,
                            "fingerprint": schema.fingerprint,
                            "cost_multiplier": config.doubled_cost_multiplier,
                            "execution": asdict(config),
                            "horizon_sessions": horizon_sessions,
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    seed=seed,
                    train_start=window.research_start,
                    train_end=window.research_end,
                    validation_start=window.validation_start,
                    validation_end=window.validation_end,
                    test_start=window.test_start,
                    test_end=window.test_end,
                )
            )
            multiplier = config.doubled_cost_multiplier
            doubled_report = run_momentum_topk(
                execution_rows,
                BaselineLineage(
                    schema.schema_id,
                    schema.version,
                    snapshot_id,
                    campaign.spec.experiment_id,
                    doubled_trial_id,
                    code_version,
                ),
                replace(
                    baseline_config,
                    commission_bps=config.commission_bps * multiplier,
                    sell_tax_bps=config.sell_tax_bps * multiplier,
                    slippage_bps=config.slippage_bps * multiplier,
                    impact_coefficient_bps=config.impact_coefficient_bps * multiplier,
                ),
                initial_nav=config.initial_nav,
            )
        raw_sharpe = _raw_sharpe(report)
        score = ExecutionCandidateScore(
            schema_id=schema.schema_id,
            fingerprint=schema.fingerprint,
            trial_id=trial_id,
            trial_number=trial_number,
            periods=report.metrics.periods,
            raw_net_sharpe=raw_sharpe,
            annualized_net_sharpe=report.metrics.net_sharpe,
            net_total_return=report.metrics.net_total_return,
            max_drawdown=report.metrics.max_drawdown,
            total_cost=report.metrics.total_cost,
            capacity_clipped_notional=report.metrics.capacity_clipped_notional,
            doubled_cost_trial_id=doubled_trial_id,
            doubled_cost_annualized_net_sharpe=(
                doubled_report.metrics.net_sharpe if doubled_report is not None else None
            ),
            doubled_cost_net_total_return=(
                doubled_report.metrics.net_total_return if doubled_report is not None else None
            ),
            doubled_cost_max_drawdown=(
                doubled_report.metrics.max_drawdown if doubled_report is not None else None
            ),
            doubled_cost_total_cost=(
                doubled_report.metrics.total_cost if doubled_report is not None else None
            ),
            doubled_cost_capacity_clipped_notional=(
                doubled_report.metrics.capacity_clipped_notional
                if doubled_report is not None
                else None
            ),
        )
        reports[schema.fingerprint] = report
        if doubled_report is not None:
            reports[f"{schema.fingerprint}::double_cost"] = doubled_report
        scores.append(score)
        registry.record_trial_result(
            trial_id,
            json.dumps(asdict(score), separators=(",", ":"), sort_keys=True),
        )
        if doubled_trial_id is not None:
            registry.record_trial_result(
                doubled_trial_id,
                json.dumps(
                    {
                        "fingerprint": schema.fingerprint,
                        "cost_multiplier": config.doubled_cost_multiplier,
                        "metrics": asdict(doubled_report.metrics),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )

    winner = max(scores, key=lambda item: (item.raw_net_sharpe, item.fingerprint))
    recorded_trials = prior_inferential_trials + registry.global_trial_count()
    candidate_courts: list[CandidateCourtScore] = []
    court_targets = scores if config.all_candidate_court else [winner]
    cpcv_by_fingerprint = {item.fingerprint: item for item in cpcv.configurations}
    for candidate_score in court_targets:
        schema = candidate_by_fingerprint[candidate_score.fingerprint].schema
        baseline = reports[candidate_score.fingerprint]
        skewness, excess_kurtosis = (
            _empirical_moments(baseline) if config.all_candidate_court else (0.0, 0.0)
        )
        dsr = deflated_sharpe_ratio(
            observed_sharpe=candidate_score.raw_net_sharpe,
            trial_sharpes=[item.raw_net_sharpe for item in scores],
            recorded_trial_count=recorded_trials,
            observations=candidate_score.periods,
            skewness=skewness,
            excess_kurtosis=excess_kurtosis,
        )
        placebo_rows = _evaluation_rows(observations[candidate_score.fingerprint], schema.horizon)
        placebo_runner = run_rank_placebo_fast if config.all_candidate_court else run_placebo
        signal_placebo = placebo_runner(
            placebo_rows,
            horizon=schema.horizon,
            direction=schema.direction,
            method="signal_shuffle",
            seed=seed,
            repetitions=config.placebo_repetitions,
        )
        return_placebo = placebo_runner(
            placebo_rows,
            horizon=schema.horizon,
            direction=schema.direction,
            method="return_permutation",
            seed=seed + 1,
            repetitions=config.placebo_repetitions,
        )
        court = build_alpha_court_report(
            FalsificationLineage(
                schema.schema_id,
                schema.version,
                snapshot_id,
                campaign.spec.experiment_id,
                candidate_score.trial_id,
                code_version,
            ),
            signal_placebo,
            return_placebo,
            dsr,
            cpcv.pbo,
            recorded_trial_count=recorded_trials,
            thresholds=AuditThresholds(
                max_placebo_p_value=config.max_placebo_p_value,
                min_dsr_probability=config.min_dsr_probability,
                max_pbo=config.maximum_pbo,
            ),
        )
        economic_checks = (
            ("cpcv_signal_gate", cpcv.signal_gate_passed),
            (
                "cpcv_positive_paths",
                config.minimum_candidate_positive_paths is None
                or cpcv_by_fingerprint[candidate_score.fingerprint].positive_paths
                >= config.minimum_candidate_positive_paths,
            ),
            (
                "annualized_net_sharpe",
                config.minimum_annualized_sharpe is None
                or (
                    candidate_score.annualized_net_sharpe is not None
                    and candidate_score.annualized_net_sharpe
                    >= config.minimum_annualized_sharpe
                ),
            ),
            (
                "maximum_drawdown",
                config.maximum_drawdown is None
                or candidate_score.max_drawdown >= -config.maximum_drawdown,
            ),
            ("capacity", candidate_score.capacity_clipped_notional <= 1e-9),
            (
                "doubled_cost_positive_return",
                not config.all_candidate_court
                or (
                    candidate_score.doubled_cost_net_total_return is not None
                    and candidate_score.doubled_cost_net_total_return > 0
                ),
            ),
            (
                "doubled_cost_capacity",
                not config.all_candidate_court
                or (
                    candidate_score.doubled_cost_capacity_clipped_notional is not None
                    and candidate_score.doubled_cost_capacity_clipped_notional <= 1e-9
                ),
            ),
        )
        candidate_courts.append(
            CandidateCourtScore(
                schema.schema_id,
                candidate_score.fingerprint,
                court,
                skewness,
                excess_kurtosis,
                economic_checks,
                court.decision.passed and all(passed for _, passed in economic_checks),
            )
        )
    alpha_court = next(
        item.alpha_court
        for item in candidate_courts
        if item.fingerprint == winner.fingerprint
    )
    walk_forward, walk_forward_report = _walk_forward(
        tuple(item.fingerprint for item in ranked),
        candidate_by_fingerprint,
        observations,
        lineage=BaselineLineage(
            "walk_forward_selector",
            "1.0.0",
            snapshot_id,
            campaign.spec.experiment_id,
            winner.trial_id,
            code_version,
        ),
        horizon_sessions=horizon_sessions,
        config=config,
    )
    reports["__walk_forward__"] = walk_forward_report
    winner_court = next(
        item for item in candidate_courts if item.fingerprint == winner.fingerprint
    )
    decision = (
        "PASS_ALPHA_COURT"
        if winner_court.passed and walk_forward.passed
        else "REJECT_EXECUTION_QUALITY"
        if alpha_court.decision.passed and walk_forward.passed
        else "REJECT_WALK_FORWARD"
        if alpha_court.decision.passed
        else "REJECT_ALPHA_COURT"
    )
    return (
        DiscoveryExecutionReport(
            method_version=EXECUTION_DISCOVERY_VERSION,
            campaign_id=campaign.campaign_id,
            experiment_id=campaign.spec.experiment_id,
            configurations=tuple(scores),
            selected_fingerprint=winner.fingerprint,
            alpha_court=alpha_court,
            candidate_courts=tuple(candidate_courts),
            walk_forward=walk_forward,
            decision=decision,
        ),
        reports,
    )
