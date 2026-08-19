from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

PORTFOLIO_OBJECTIVE_VERSION = "6.0.0"


@dataclass(frozen=True)
class PortfolioCandidateEvidence:
    proposal_id: str
    semantic_identity: str
    net_sharpe: float
    double_cost_sharpe: float
    marginal_information_ratio: float
    positive_path_fraction: float
    annual_turnover: float
    capacity_cny: float
    maximum_drawdown: float
    evidence_scope: str = "research_only"

    def validate(self) -> None:
        numeric = (
            self.net_sharpe,
            self.double_cost_sharpe,
            self.marginal_information_ratio,
            self.positive_path_fraction,
            self.annual_turnover,
            self.capacity_cny,
            self.maximum_drawdown,
        )
        if not self.proposal_id or not self.semantic_identity or any(not math.isfinite(x) for x in numeric):
            raise ValueError("portfolio evidence requires identities and finite metrics")
        if not 0 <= self.positive_path_fraction <= 1 or self.annual_turnover < 0 or self.capacity_cny < 0:
            raise ValueError("invalid portfolio path, turnover or capacity evidence")
        if self.maximum_drawdown > 0:
            raise ValueError("maximum_drawdown must be non-positive")
        if self.evidence_scope != "research_only":
            raise ValueError("portfolio objective accepts research-only evidence")


@dataclass(frozen=True)
class PairwiseDependence:
    left_proposal_id: str
    right_proposal_id: str
    rank_correlation: float

    def validate(self) -> None:
        if self.left_proposal_id == self.right_proposal_id:
            raise ValueError("pairwise dependence requires distinct candidates")
        if not -1 <= self.rank_correlation <= 1:
            raise ValueError("pairwise correlation must be in [-1, 1]")


@dataclass(frozen=True)
class PortfolioObjectiveConfig:
    maximum_factors: int = 5
    maximum_pair_correlation: float = 0.70
    minimum_capacity_cny: float = 3_000_000.0
    maximum_annual_turnover: float = 24.0
    minimum_double_cost_sharpe: float = -0.25
    minimum_marginal_ir: float = 0.0
    marginal_ir_weight: float = 1.0
    net_sharpe_weight: float = 0.25
    path_stability_weight: float = 0.25
    double_cost_weight: float = 0.20
    turnover_penalty: float = 0.02
    drawdown_penalty: float = 0.20
    correlation_penalty: float = 0.50

    def validate(self) -> None:
        if self.maximum_factors < 1 or not 0 <= self.maximum_pair_correlation <= 1:
            raise ValueError("invalid portfolio breadth or correlation gate")
        if self.minimum_capacity_cny <= 0 or self.maximum_annual_turnover <= 0:
            raise ValueError("capacity and turnover gates must be positive")
        weights = (
            self.marginal_ir_weight,
            self.net_sharpe_weight,
            self.path_stability_weight,
            self.double_cost_weight,
            self.turnover_penalty,
            self.drawdown_penalty,
            self.correlation_penalty,
        )
        if any(value < 0 for value in weights):
            raise ValueError("portfolio objective weights cannot be negative")


DEFAULT_PORTFOLIO_OBJECTIVE_CONFIG = PortfolioObjectiveConfig()


@dataclass(frozen=True)
class PortfolioSelectionScore:
    proposal_id: str
    objective: float | None
    maximum_selected_correlation: float | None
    decision: str
    reason: str
    weight: float


@dataclass(frozen=True)
class PortfolioSelectionReport:
    method_version: str
    selected_proposal_ids: tuple[str, ...]
    scores: tuple[PortfolioSelectionScore, ...]
    total_weight: float
    inferential_trial_delta: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _dependence_index(
    candidates: tuple[PortfolioCandidateEvidence, ...], pairs: tuple[PairwiseDependence, ...]
) -> dict[frozenset[str], float]:
    candidate_ids = {item.proposal_id for item in candidates}
    index: dict[frozenset[str], float] = {}
    for item in pairs:
        item.validate()
        if {item.left_proposal_id, item.right_proposal_id} - candidate_ids:
            raise ValueError("pairwise dependence refers to an unknown candidate")
        key = frozenset((item.left_proposal_id, item.right_proposal_id))
        if key in index:
            raise ValueError("duplicate pairwise dependence")
        index[key] = item.rank_correlation
    expected = len(candidates) * (len(candidates) - 1) // 2
    if len(index) != expected:
        raise ValueError("portfolio selection requires a complete pairwise dependence matrix")
    return index


def select_portfolio_candidates(
    candidates: tuple[PortfolioCandidateEvidence, ...],
    pairs: tuple[PairwiseDependence, ...],
    *,
    config: PortfolioObjectiveConfig = DEFAULT_PORTFOLIO_OBJECTIVE_CONFIG,
) -> PortfolioSelectionReport:
    config.validate()
    if not candidates:
        raise ValueError("portfolio objective requires candidates")
    for item in candidates:
        item.validate()
    if len({item.proposal_id for item in candidates}) != len(candidates):
        raise ValueError("portfolio candidate IDs must be unique")
    if len({item.semantic_identity for item in candidates}) != len(candidates):
        raise ValueError("portfolio candidates must have unique semantic identities")
    dependence = _dependence_index(candidates, pairs)
    selected: list[PortfolioCandidateEvidence] = []
    outcomes: dict[str, PortfolioSelectionScore] = {}
    remaining = list(candidates)
    while remaining and len(selected) < config.maximum_factors:
        ranked = []
        for item in remaining:
            correlations = [
                abs(dependence[frozenset((item.proposal_id, peer.proposal_id))]) for peer in selected
            ]
            maximum_correlation = max(correlations) if correlations else 0.0
            objective = (
                config.marginal_ir_weight * item.marginal_information_ratio
                + config.net_sharpe_weight * item.net_sharpe
                + config.path_stability_weight * item.positive_path_fraction
                + config.double_cost_weight * item.double_cost_sharpe
                - config.turnover_penalty * item.annual_turnover
                - config.drawdown_penalty * abs(item.maximum_drawdown)
                - config.correlation_penalty * maximum_correlation
            )
            ranked.append((objective, maximum_correlation, item))
        objective, maximum_correlation, item = min(
            ranked, key=lambda row: (-row[0], row[2].semantic_identity)
        )
        remaining.remove(item)
        if item.capacity_cny < config.minimum_capacity_cny:
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "REJECTED", "capacity", 0.0
            )
        elif item.annual_turnover > config.maximum_annual_turnover:
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "REJECTED", "turnover", 0.0
            )
        elif item.double_cost_sharpe < config.minimum_double_cost_sharpe:
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "REJECTED", "double_cost", 0.0
            )
        elif item.marginal_information_ratio < config.minimum_marginal_ir:
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "REJECTED", "marginal_ir", 0.0
            )
        elif maximum_correlation > config.maximum_pair_correlation:
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "REJECTED", "redundancy", 0.0
            )
        else:
            selected.append(item)
            outcomes[item.proposal_id] = PortfolioSelectionScore(
                item.proposal_id, objective, maximum_correlation, "SELECTED", "marginal_value", 0.0
            )
    for item in remaining:
        correlations = [
            abs(dependence[frozenset((item.proposal_id, peer.proposal_id))]) for peer in selected
        ]
        maximum_correlation = max(correlations) if correlations else 0.0
        outcomes[item.proposal_id] = PortfolioSelectionScore(
            item.proposal_id,
            None,
            maximum_correlation,
            "REJECTED" if maximum_correlation > config.maximum_pair_correlation else "DEFERRED",
            "redundancy" if maximum_correlation > config.maximum_pair_correlation else "portfolio_breadth_budget",
            0.0,
        )
    positive = {
        item.proposal_id: max(outcomes[item.proposal_id].objective or 0.0, 1e-12) for item in selected
    }
    denominator = sum(positive.values())
    for proposal_id, value in positive.items():
        outcomes[proposal_id] = PortfolioSelectionScore(
            **{**asdict(outcomes[proposal_id]), "weight": value / denominator}
        )
    ordered = tuple(outcomes[item.proposal_id] for item in candidates)
    return PortfolioSelectionReport(
        PORTFOLIO_OBJECTIVE_VERSION,
        tuple(item.proposal_id for item in selected),
        ordered,
        sum(item.weight for item in ordered),
        0,
    )
