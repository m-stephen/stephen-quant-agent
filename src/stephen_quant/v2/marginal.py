from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from statistics import stdev
from typing import Literal

from stephen_quant.evaluation.metrics import pearson_correlation, spearman_correlation

from .replay import ReferenceLibraryRecord

Phase = Literal["train", "test"]


@dataclass(frozen=True)
class MarginalObservation:
    fold_id: str
    phase: Phase
    date: str
    instrument: str
    candidate_value: float
    reference_value: float
    forward_return: float
    adv: float


@dataclass(frozen=True)
class MarginalPolicy:
    top_fraction: float = 0.20
    residual_blend: float = 0.50
    transaction_cost_bps: float = 10.0
    capital: float = 3_000_000.0
    maximum_participation: float = 0.05
    complexity_penalty: float = 0.02
    data_cost_penalty: float = 0.02

    def validate(self) -> None:
        if not 0 < self.top_fraction <= 0.5 or not 0 <= self.residual_blend <= 1:
            raise ValueError("invalid marginal portfolio fractions")
        if self.transaction_cost_bps < 0 or self.capital <= 0:
            raise ValueError("marginal costs and capital must be non-negative/positive")
        if not 0 < self.maximum_participation <= 1:
            raise ValueError("maximum participation must be in (0, 1]")


DEFAULT_MARGINAL_POLICY = MarginalPolicy()


@dataclass(frozen=True)
class FoldResidualModel:
    fold_id: str
    intercept: float
    reference_beta: float
    fitted_train_rows: int
    evaluated_test_rows: int


@dataclass(frozen=True)
class PortfolioMetrics:
    net_return: float
    net_sharpe: float
    maximum_drawdown: float
    turnover: float
    tail_return: float
    capacity: float


@dataclass(frozen=True)
class MarginalScorecard:
    candidate_id: str
    library_id: str
    library_version: str
    library_status: Literal["reference_only", "validated_alpha"]
    standalone_ic: float
    standalone_rank_ic: float
    residual_ic: float
    residual_rank_ic: float
    redundancy_correlation: float
    reference_long_only: PortfolioMetrics
    augmented_long_only: PortfolioMetrics
    reference_long_short: PortfolioMetrics
    augmented_long_short: PortfolioMetrics
    delta_net_sharpe: float
    delta_turnover: float
    drawdown_improvement: float
    delta_tail_return: float
    capacity: float
    complexity_cost: float
    data_cost: float
    marginal_utility: float
    fold_models: tuple[FoldResidualModel, ...]


def _fit_residual(rows: list[MarginalObservation]) -> tuple[float, float]:
    x = [row.reference_value for row in rows]
    y = [row.candidate_value for row in rows]
    x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    beta = (
        0.0
        if denominator == 0
        else sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True)) / denominator
    )
    return y_mean - beta * x_mean, beta


def _standardize(values: list[float]) -> list[float]:
    center = sum(values) / len(values)
    scale = math.sqrt(sum((value - center) ** 2 for value in values) / len(values))
    return [0.0 for _ in values] if scale == 0 else [(value - center) / scale for value in values]


def _drawdown(returns: list[float]) -> float:
    wealth = peak = 1.0
    worst = 0.0
    for value in returns:
        wealth *= 1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1)
    return worst


def _sharpe(returns: list[float]) -> float:
    if len(returns) < 2 or stdev(returns) == 0:
        return 0.0
    return sum(returns) / len(returns) / stdev(returns) * math.sqrt(252)


def _portfolio(
    rows: list[tuple[MarginalObservation, float]],
    policy: MarginalPolicy,
    *,
    long_short: bool,
) -> PortfolioMetrics:
    by_date: dict[str, list[tuple[MarginalObservation, float]]] = defaultdict(list)
    for row in rows:
        by_date[row[0].date].append(row)
    daily: list[float] = []
    selected_history: list[set[str]] = []
    capacities: list[float] = []
    for _, cross_section in sorted(by_date.items()):
        ordered = sorted(cross_section, key=lambda item: (item[1], item[0].instrument))
        count = max(1, math.ceil(len(ordered) * policy.top_fraction))
        top, bottom = ordered[-count:], ordered[:count]
        selected = {row.instrument for row, _ in top}
        selected_history.append(selected)
        long_return = sum(row.forward_return for row, _ in top) / len(top)
        short_return = sum(row.forward_return for row, _ in bottom) / len(bottom)
        daily.append(long_return - short_return if long_short else long_return)
        capacities.append(sum(row.adv for row, _ in top) * policy.maximum_participation)
    turnovers = [
        1 - len(previous & current) / max(len(previous | current), 1)
        for previous, current in pairwise(selected_history)
    ]
    turnover = sum(turnovers) / len(turnovers) if turnovers else 0.0
    cost = turnover * policy.transaction_cost_bps / 10_000
    net_daily = [value - cost for value in daily]
    ordered_returns = sorted(net_daily)
    tail_index = max(0, math.ceil(len(ordered_returns) * 0.05) - 1)
    compounded = math.prod(1 + value for value in net_daily) - 1
    return PortfolioMetrics(
        compounded,
        _sharpe(net_daily),
        _drawdown(net_daily),
        turnover,
        ordered_returns[tail_index],
        min(capacities),
    )


def evaluate_marginal_candidate(
    candidate_id: str,
    observations: tuple[MarginalObservation, ...],
    reference_library: ReferenceLibraryRecord,
    *,
    complexity_cost: float,
    data_cost: float,
    policy: MarginalPolicy = DEFAULT_MARGINAL_POLICY,
) -> MarginalScorecard:
    """Fit residual models on each train fold and apply them only to that fold's test rows."""

    policy.validate()
    reference_library.validate()
    if complexity_cost < 0 or data_cost < 0:
        raise ValueError("marginal complexity and data costs cannot be negative")
    by_fold: dict[str, list[MarginalObservation]] = defaultdict(list)
    for row in observations:
        if row.adv <= 0 or any(
            not math.isfinite(value)
            for value in (
                row.candidate_value,
                row.reference_value,
                row.forward_return,
                row.adv,
            )
        ):
            raise ValueError("marginal observations require finite values and positive ADV")
        by_fold[row.fold_id].append(row)
    evaluated: list[tuple[MarginalObservation, float]] = []
    models: list[FoldResidualModel] = []
    for fold_id, rows in sorted(by_fold.items()):
        train = [row for row in rows if row.phase == "train"]
        test = [row for row in rows if row.phase == "test"]
        if len(train) < 3 or len(test) < 3:
            raise ValueError("every marginal fold requires at least three train and test rows")
        intercept, beta = _fit_residual(train)
        evaluated.extend(
            (row, row.candidate_value - (intercept + beta * row.reference_value)) for row in test
        )
        models.append(FoldResidualModel(fold_id, intercept, beta, len(train), len(test)))
    test_rows = [row for row, _ in evaluated]
    residuals = [value for _, value in evaluated]
    returns = [row.forward_return for row in test_rows]
    candidate_values = [row.candidate_value for row in test_rows]
    reference_values = [row.reference_value for row in test_rows]
    reference_scored = [(row, row.reference_value) for row in test_rows]
    augmented_scored: list[tuple[MarginalObservation, float]] = []
    by_date: dict[str, list[tuple[MarginalObservation, float]]] = defaultdict(list)
    for item in evaluated:
        by_date[item[0].date].append(item)
    for items in by_date.values():
        reference_z = _standardize([row.reference_value for row, _ in items])
        residual_z = _standardize([value for _, value in items])
        augmented_scored.extend(
            (row, ref + policy.residual_blend * residual)
            for (row, _), ref, residual in zip(items, reference_z, residual_z, strict=True)
        )
    ref_long = _portfolio(reference_scored, policy, long_short=False)
    aug_long = _portfolio(augmented_scored, policy, long_short=False)
    ref_ls = _portfolio(reference_scored, policy, long_short=True)
    aug_ls = _portfolio(augmented_scored, policy, long_short=True)
    delta_sharpe = aug_long.net_sharpe - ref_long.net_sharpe
    delta_turnover = aug_long.turnover - ref_long.turnover
    drawdown_improvement = aug_long.maximum_drawdown - ref_long.maximum_drawdown
    delta_tail = aug_long.tail_return - ref_long.tail_return
    residual_ic = pearson_correlation(residuals, returns)
    utility = (
        delta_sharpe
        + 2 * residual_ic
        + drawdown_improvement
        + delta_tail
        - max(delta_turnover, 0)
        - policy.complexity_penalty * complexity_cost
        - policy.data_cost_penalty * data_cost
    )
    status: Literal["reference_only", "validated_alpha"] = (
        "validated_alpha" if reference_library.validated_alpha else "reference_only"
    )
    return MarginalScorecard(
        candidate_id,
        reference_library.library_id,
        reference_library.version,
        status,
        pearson_correlation(candidate_values, returns),
        spearman_correlation(candidate_values, returns),
        residual_ic,
        spearman_correlation(residuals, returns),
        pearson_correlation(candidate_values, reference_values),
        ref_long,
        aug_long,
        ref_ls,
        aug_ls,
        delta_sharpe,
        delta_turnover,
        drawdown_improvement,
        delta_tail,
        min(aug_long.capacity, aug_ls.capacity),
        complexity_cost,
        data_cost,
        utility,
        tuple(models),
    )


def rank_marginal_candidates(
    scorecards: tuple[MarginalScorecard, ...],
) -> tuple[MarginalScorecard, ...]:
    return tuple(sorted(scorecards, key=lambda item: (-item.marginal_utility, item.candidate_id)))
