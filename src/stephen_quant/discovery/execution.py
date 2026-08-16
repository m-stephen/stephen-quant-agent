from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from statistics import stdev

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    BaselineReport,
    run_momentum_topk,
)
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import (
    AlphaCourtReport,
    AuditThresholds,
    FalsificationLineage,
    build_alpha_court_report,
    deflated_sharpe_ratio,
    run_placebo,
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


@dataclass(frozen=True)
class DiscoveryExecutionReport:
    method_version: str
    campaign_id: str
    experiment_id: str
    configurations: tuple[ExecutionCandidateScore, ...]
    selected_fingerprint: str
    alpha_court: AlphaCourtReport
    decision: str


def _non_overlapping(
    observations: tuple[BaselineObservation, ...], horizon_sessions: int
) -> tuple[BaselineObservation, ...]:
    dates = sorted({row.execution_at for row in observations})
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
) -> tuple[DiscoveryExecutionReport, dict[str, BaselineReport]]:
    """Run a bounded cost-aware execution tournament and the final Alpha Court."""

    config.validate()
    if not cpcv.signal_gate_passed:
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
            observations[schema.fingerprint], horizon_sessions
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
            BaselineConfig(
                top_k=config.top_k,
                direction=schema.direction,
                commission_bps=config.commission_bps,
                sell_tax_bps=config.sell_tax_bps,
                slippage_bps=config.slippage_bps,
                impact_coefficient_bps=config.impact_coefficient_bps,
                max_participation_rate=config.max_participation_rate,
                periods_per_year=max(1, 252 // horizon_sessions),
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
        )
        reports[schema.fingerprint] = report
        scores.append(score)
        registry.record_trial_result(
            trial_id,
            json.dumps(asdict(score), separators=(",", ":"), sort_keys=True),
        )

    winner = max(scores, key=lambda item: (item.raw_net_sharpe, item.fingerprint))
    winner_schema = candidate_by_fingerprint[winner.fingerprint].schema
    recorded_trials = registry.trial_count(campaign.spec.experiment_id)
    dsr = deflated_sharpe_ratio(
        observed_sharpe=winner.raw_net_sharpe,
        trial_sharpes=[item.raw_net_sharpe for item in scores],
        recorded_trial_count=recorded_trials,
        observations=winner.periods,
    )
    placebo_rows = _evaluation_rows(
        observations[winner.fingerprint], winner_schema.horizon
    )
    signal_placebo = run_placebo(
        placebo_rows,
        horizon=winner_schema.horizon,
        direction=winner_schema.direction,
        method="signal_shuffle",
        seed=seed,
        repetitions=config.placebo_repetitions,
    )
    return_placebo = run_placebo(
        placebo_rows,
        horizon=winner_schema.horizon,
        direction=winner_schema.direction,
        method="return_permutation",
        seed=seed + 1,
        repetitions=config.placebo_repetitions,
    )
    alpha_court = build_alpha_court_report(
        FalsificationLineage(
            winner_schema.schema_id,
            winner_schema.version,
            snapshot_id,
            campaign.spec.experiment_id,
            winner.trial_id,
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
    decision = "PASS_ALPHA_COURT" if alpha_court.decision.passed else "REJECT_ALPHA_COURT"
    return (
        DiscoveryExecutionReport(
            method_version=EXECUTION_DISCOVERY_VERSION,
            campaign_id=campaign.campaign_id,
            experiment_id=campaign.spec.experiment_id,
            configurations=tuple(scores),
            selected_fingerprint=winner.fingerprint,
            alpha_court=alpha_court,
            decision=decision,
        ),
        reports,
    )
