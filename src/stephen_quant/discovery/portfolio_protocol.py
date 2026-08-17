from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from stephen_quant.baseline import BaselineReport

from .cpcv import DiscoveryCpcvReport
from .execution import DiscoveryExecutionReport
from .models import FactorSchema
from .screening import ScreeningReport

SIGNAL_PORTFOLIO_PROTOCOL_VERSION = "signal-portfolio-gate-1.0.0"


@dataclass(frozen=True)
class AlphaCard:
    protocol_version: str
    schema_id: str
    fingerprint: str
    horizon: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str
    coverage: float
    cpcv_mean_path_rank_ic: float
    cpcv_positive_paths: int
    cpcv_paths: int
    turnover: float
    net_total_return: float
    annualized_net_sharpe: float | None
    maximum_drawdown: float
    total_cost: float
    capacity_clipped_notional: float
    maximum_adv_participation: float
    industry_exposure: str
    style_exposure: str
    alpha_court_passed: bool
    walk_forward_passed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class PortfolioSignalPackage:
    protocol_version: str
    alpha_card: AlphaCard
    state_fields: tuple[str, ...]
    reward_fields: tuple[str, ...]
    risk_constraints: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def build_alpha_card(
    schema: FactorSchema,
    screening: ScreeningReport,
    cpcv: DiscoveryCpcvReport,
    execution: DiscoveryExecutionReport,
    baseline: BaselineReport,
) -> AlphaCard:
    """Create a complete signal contract even when the signal is rejected."""

    fingerprint = schema.fingerprint
    if execution.selected_fingerprint != fingerprint:
        raise ValueError("Alpha Card schema is not the selected execution candidate")
    screen = next(
        (score for score in screening.scores if score.fingerprint == fingerprint), None
    )
    cpcv_score = next(
        (score for score in cpcv.configurations if score.fingerprint == fingerprint), None
    )
    if screen is None or cpcv_score is None:
        raise ValueError("Alpha Card lineage is incomplete")
    if baseline.lineage.trial_id != execution.alpha_court.lineage.trial_id:
        raise ValueError("Alpha Card baseline and Alpha Court trials differ")
    metrics = baseline.metrics
    return AlphaCard(
        protocol_version=SIGNAL_PORTFOLIO_PROTOCOL_VERSION,
        schema_id=schema.schema_id,
        fingerprint=fingerprint,
        horizon=schema.horizon,
        snapshot_id=baseline.lineage.snapshot_id,
        experiment_id=baseline.lineage.experiment_id,
        trial_id=baseline.lineage.trial_id,
        code_version=baseline.lineage.code_version,
        coverage=screen.coverage,
        cpcv_mean_path_rank_ic=cpcv_score.mean_path_rank_ic,
        cpcv_positive_paths=cpcv_score.positive_paths,
        cpcv_paths=len(cpcv_score.path_scores),
        turnover=metrics.total_turnover,
        net_total_return=metrics.net_total_return,
        annualized_net_sharpe=metrics.net_sharpe,
        maximum_drawdown=metrics.max_drawdown,
        total_cost=metrics.total_cost,
        capacity_clipped_notional=metrics.capacity_clipped_notional,
        maximum_adv_participation=baseline.config.max_participation_rate,
        industry_exposure="not_measured",
        style_exposure="not_measured",
        alpha_court_passed=execution.alpha_court.decision.passed,
        walk_forward_passed=execution.walk_forward.passed,
    )


def authorize_portfolio_signal(card: AlphaCard) -> PortfolioSignalPackage:
    """Fail closed: rejected or incomplete evidence can never reach PPO/portfolio code."""

    if not card.alpha_court_passed or not card.walk_forward_passed:
        raise ValueError("signal is not authorized for portfolio or PPO consumption")
    return PortfolioSignalPackage(
        protocol_version=SIGNAL_PORTFOLIO_PROTOCOL_VERSION,
        alpha_card=card,
        state_fields=("signal", "coverage", "turnover", "capacity", "risk_exposure"),
        reward_fields=("net_return", "transaction_cost", "drawdown_penalty"),
        risk_constraints=(
            "long_only",
            "maximum_adv_participation",
            "industry_exposure_monitoring",
            "style_exposure_monitoring",
        ),
    )
