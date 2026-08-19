from __future__ import annotations

import json
from dataclasses import asdict, dataclass

STAGED_SCREENING_VERSION = "5.8.0"


@dataclass(frozen=True)
class StagedScreeningConfig:
    proposal_budget: int = 256
    data_quality_budget: int = 192
    training_budget: int = 96
    cpcv_budget: int = 16
    execution_budget: int = 4
    minimum_coverage: float = 0.80
    maximum_missing_fraction: float = 0.20
    minimum_signal_variance: float = 1e-12
    maximum_rank_turnover: float = 0.60
    minimum_training_rank_ic: float = 0.01
    minimum_positive_year_fraction: float = 0.50
    minimum_cpcv_rank_ic: float = 0.005
    minimum_positive_path_fraction: float = 0.60
    maximum_pbo: float = 0.20
    minimum_net_sharpe: float = 0.0
    minimum_double_cost_sharpe: float = -0.25

    def validate(self) -> None:
        budgets = (
            self.proposal_budget,
            self.data_quality_budget,
            self.training_budget,
            self.cpcv_budget,
            self.execution_budget,
        )
        if not all(value > 0 for value in budgets) or tuple(sorted(budgets, reverse=True)) != budgets:
            raise ValueError("funnel budgets must be positive and non-increasing")
        fractions = (
            self.minimum_coverage,
            self.maximum_missing_fraction,
            self.maximum_rank_turnover,
            self.minimum_positive_year_fraction,
            self.minimum_positive_path_fraction,
            self.maximum_pbo,
        )
        if any(not 0 <= value <= 1 for value in fractions):
            raise ValueError("funnel fractions must be in [0, 1]")
        if self.minimum_signal_variance <= 0:
            raise ValueError("minimum_signal_variance must be positive")


DEFAULT_STAGED_SCREENING_CONFIG = StagedScreeningConfig()


@dataclass(frozen=True)
class FunnelEvidence:
    proposal_id: str
    semantic_identity: str
    coverage: float
    missing_fraction: float
    signal_variance: float
    rank_turnover: float
    training_rank_ic: float | None = None
    positive_year_fraction: float | None = None
    cpcv_rank_ic: float | None = None
    positive_path_fraction: float | None = None
    pbo: float | None = None
    net_sharpe: float | None = None
    double_cost_sharpe: float | None = None

    def validate(self) -> None:
        if not self.proposal_id or not self.semantic_identity:
            raise ValueError("funnel evidence requires proposal and semantic identities")
        fractions = (self.coverage, self.missing_fraction, self.rank_turnover)
        if any(not 0 <= value <= 1 for value in fractions) or self.signal_variance < 0:
            raise ValueError("invalid label-free funnel evidence")
        optional_fractions = (
            self.positive_year_fraction,
            self.positive_path_fraction,
            self.pbo,
        )
        if any(value is not None and not 0 <= value <= 1 for value in optional_fractions):
            raise ValueError("invalid labeled funnel fraction")


@dataclass(frozen=True)
class FunnelDecision:
    proposal_id: str
    semantic_identity: str
    terminal_stage: str
    decision: str
    reason: str
    trial_delta: int


@dataclass(frozen=True)
class StagedScreeningReport:
    method_version: str
    config: StagedScreeningConfig
    input_candidates: int
    data_quality_candidates: int
    training_candidates: int
    cpcv_candidates: int
    execution_candidates: int
    survivors: tuple[str, ...]
    decisions: tuple[FunnelDecision, ...]
    inferential_trial_delta: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _quality_score(item: FunnelEvidence) -> tuple[float, float, float, str]:
    return (-item.coverage, item.missing_fraction, item.rank_turnover, item.semantic_identity)


def run_staged_screening(
    evidence: tuple[FunnelEvidence, ...],
    *,
    config: StagedScreeningConfig = DEFAULT_STAGED_SCREENING_CONFIG,
) -> StagedScreeningReport:
    config.validate()
    if not evidence:
        raise ValueError("staged screening requires evidence")
    for item in evidence:
        item.validate()
    if len({item.proposal_id for item in evidence}) != len(evidence):
        raise ValueError("duplicate proposal_id in funnel evidence")
    if len({item.semantic_identity for item in evidence}) != len(evidence):
        raise ValueError("duplicate semantic identity must be removed before screening")
    ordered = sorted(evidence, key=_quality_score)[: config.proposal_budget]
    decisions: dict[str, FunnelDecision] = {}
    quality_pass = []
    for item in ordered:
        if item.coverage < config.minimum_coverage:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "data_quality", "REJECTED", "coverage", 0
            )
        elif item.missing_fraction > config.maximum_missing_fraction:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "data_quality", "REJECTED", "missingness", 0
            )
        elif item.signal_variance < config.minimum_signal_variance:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "data_quality", "REJECTED", "constant_signal", 0
            )
        elif item.rank_turnover > config.maximum_rank_turnover:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "data_quality", "REJECTED", "turnover_proxy", 0
            )
        else:
            quality_pass.append(item)
    quality_pass = sorted(quality_pass, key=_quality_score)[: config.data_quality_budget]
    training_pool = quality_pass[: config.training_budget]
    training_pass = []
    for item in training_pool:
        if item.training_rank_ic is None or item.positive_year_fraction is None:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "training", "WAITING_FOR_LABELS", "missing_training_evidence", 0
            )
        elif item.training_rank_ic < config.minimum_training_rank_ic:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "training", "REJECTED", "training_rank_ic", 1
            )
        elif item.positive_year_fraction < config.minimum_positive_year_fraction:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "training", "REJECTED", "year_stability", 1
            )
        else:
            training_pass.append(item)
    training_pass.sort(
        key=lambda item: (
            -(item.training_rank_ic or 0),
            -(item.positive_year_fraction or 0),
            item.semantic_identity,
        )
    )
    cpcv_pool = training_pass[: config.cpcv_budget]
    for item in training_pass[config.cpcv_budget :]:
        decisions[item.proposal_id] = FunnelDecision(
            item.proposal_id, item.semantic_identity, "cpcv_budget", "DEFERRED", "cpcv_budget", 1
        )
    cpcv_pass = []
    for item in cpcv_pool:
        if item.cpcv_rank_ic is None or item.positive_path_fraction is None or item.pbo is None:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "cpcv", "WAITING_FOR_CPCV", "missing_cpcv_evidence", 1
            )
        elif (
            item.cpcv_rank_ic < config.minimum_cpcv_rank_ic
            or item.positive_path_fraction < config.minimum_positive_path_fraction
            or item.pbo > config.maximum_pbo
        ):
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "cpcv", "REJECTED", "cpcv_or_pbo", 2
            )
        else:
            cpcv_pass.append(item)
    cpcv_pass.sort(key=lambda item: (-(item.cpcv_rank_ic or 0), item.semantic_identity))
    execution_pool = cpcv_pass[: config.execution_budget]
    for item in cpcv_pass[config.execution_budget :]:
        decisions[item.proposal_id] = FunnelDecision(
            item.proposal_id,
            item.semantic_identity,
            "execution_budget",
            "DEFERRED",
            "execution_budget",
            2,
        )
    survivors = []
    for item in execution_pool:
        if item.net_sharpe is None or item.double_cost_sharpe is None:
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "execution", "WAITING_FOR_EXECUTION", "missing_execution_evidence", 2
            )
        elif (
            item.net_sharpe < config.minimum_net_sharpe
            or item.double_cost_sharpe < config.minimum_double_cost_sharpe
        ):
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "execution", "REJECTED", "cost_stress", 3
            )
        else:
            survivors.append(item.proposal_id)
            decisions[item.proposal_id] = FunnelDecision(
                item.proposal_id, item.semantic_identity, "execution", "SHORTLISTED", "passed_funnel", 3
            )
    for item in ordered:
        decisions.setdefault(
            item.proposal_id,
            FunnelDecision(item.proposal_id, item.semantic_identity, "budget", "DEFERRED", "stage_budget", 0),
        )
    ordered_decisions = tuple(decisions[item.proposal_id] for item in ordered)
    return StagedScreeningReport(
        STAGED_SCREENING_VERSION,
        config,
        len(ordered),
        len(quality_pass),
        len(training_pool),
        len(cpcv_pool),
        len(execution_pool),
        tuple(survivors),
        ordered_decisions,
        sum(item.trial_delta for item in ordered_decisions),
    )
