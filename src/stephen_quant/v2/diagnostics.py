from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise

from stephen_quant.evaluation.metrics import (
    average_ranks,
    pearson_correlation,
    spearman_correlation,
)


class DiagnosticCode(str, Enum):
    PASS = "PASS"
    LOW_COVERAGE = "LOW_COVERAGE"
    HIGH_MISSINGNESS = "HIGH_MISSINGNESS"
    STALE_SIGNAL = "STALE_SIGNAL"
    FLAT_QUANTILES = "FLAT_QUANTILES"
    EXCESS_TURNOVER = "EXCESS_TURNOVER"
    DATE_CONCENTRATION = "DATE_CONCENTRATION"
    REGIME_CONCENTRATION = "REGIME_CONCENTRATION"
    COST_ERASED = "COST_ERASED"


@dataclass(frozen=True)
class DiagnosticObservation:
    date: str
    instrument: str
    value: float | None
    forward_return: float
    residual_return: float
    stale_days: int
    regime: str
    industry: str
    style_exposures: tuple[tuple[str, float], ...]
    holding_returns: tuple[float, ...]


@dataclass(frozen=True)
class DiagnosticPolicy:
    expected_observations: int
    minimum_coverage: float = 0.80
    maximum_missingness: float = 0.20
    maximum_stale_fraction: float = 0.20
    maximum_turnover: float = 0.80
    maximum_date_concentration: float = 0.60
    maximum_regime_concentration: float = 0.80
    cost_bps: float = 10.0


@dataclass(frozen=True)
class CheapDiagnosticReport:
    coverage: float
    missingness: float
    stale_fraction: float
    mean_ic: float
    mean_rank_ic: float
    residual_ic: float
    quantile_returns: tuple[float, ...]
    long_return: float
    short_return: float
    gross_spread: float
    turnover: float
    holding_decay: tuple[float, ...]
    style_exposures: tuple[tuple[str, float], ...]
    industry_concentration: float
    date_concentration: float
    regime_concentration: float
    net_spread_after_cost: float
    codes: tuple[DiagnosticCode, ...]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def run_cheap_diagnostics(
    observations: tuple[DiagnosticObservation, ...], policy: DiagnosticPolicy
) -> CheapDiagnosticReport:
    if policy.expected_observations < 1 or not observations:
        raise ValueError("cheap diagnostics require observations and expected count")
    valid = [row for row in observations if row.value is not None and math.isfinite(row.value)]
    if len(valid) < 6:
        raise ValueError("cheap diagnostics require at least six valid observations")
    coverage = len(valid) / policy.expected_observations
    missingness = 1 - len(valid) / len(observations)
    stale_fraction = sum(row.stale_days > 0 for row in valid) / len(valid)
    by_date: dict[str, list[DiagnosticObservation]] = defaultdict(list)
    for row in valid:
        by_date[row.date].append(row)
    daily_ic: list[float] = []
    daily_rank: list[float] = []
    daily_spread: list[float] = []
    ranks_by_date: dict[str, dict[str, float]] = {}
    quantiles: list[list[float]] = [[] for _ in range(5)]
    for date, rows in sorted(by_date.items()):
        ordered = sorted(rows, key=lambda row: row.instrument)
        if len(ordered) < 5:
            continue
        values = [float(row.value) for row in ordered if row.value is not None]
        returns = [row.forward_return for row in ordered]
        daily_ic.append(pearson_correlation(values, returns))
        daily_rank.append(spearman_correlation(values, returns))
        ranked_rows = sorted(ordered, key=lambda row: float(row.value))
        for index, row in enumerate(ranked_rows):
            bucket = min(index * 5 // len(ranked_rows), 4)
            quantiles[bucket].append(row.forward_return)
        bottom = [row.forward_return for row in ranked_rows[: max(1, len(rows) // 5)]]
        top = [row.forward_return for row in ranked_rows[-max(1, len(rows) // 5) :]]
        daily_spread.append(_mean(top) - _mean(bottom))
        ranks = average_ranks(values)
        denominator = max(len(ranks) - 1, 1)
        ranks_by_date[date] = {
            row.instrument: (rank - 1) / denominator
            for row, rank in zip(ordered, ranks, strict=True)
        }
    if not daily_ic:
        raise ValueError("cheap diagnostics have no valid daily cross-sections")
    residual_ic = pearson_correlation(
        [float(row.value) for row in valid if row.value is not None],
        [row.residual_return for row in valid],
    )
    quantile_returns = tuple(_mean(bucket) if bucket else 0.0 for bucket in quantiles)
    long_return, short_return = quantile_returns[-1], quantile_returns[0]
    gross_spread = long_return - short_return
    changes: list[float] = []
    for previous, current in pairwise(sorted(ranks_by_date)):
        common = set(ranks_by_date[previous]) & set(ranks_by_date[current])
        changes.extend(
            abs(ranks_by_date[current][item] - ranks_by_date[previous][item]) for item in common
        )
    turnover = _mean(changes) if changes else 0.0
    horizon_count = len(valid[0].holding_returns)
    if any(len(row.holding_returns) != horizon_count for row in valid):
        raise ValueError("holding-return vectors must have equal length")
    holding_decay = tuple(
        spearman_correlation(
            [float(row.value) for row in valid if row.value is not None],
            [row.holding_returns[index] for row in valid],
        )
        for index in range(horizon_count)
    )
    style_names = sorted({name for row in valid for name, _ in row.style_exposures})
    styles = tuple(
        (
            name,
            pearson_correlation(
                [float(row.value) for row in valid if row.value is not None],
                [dict(row.style_exposures).get(name, 0.0) for row in valid],
            ),
        )
        for name in style_names
    )
    industries: dict[str, list[float]] = defaultdict(list)
    regimes: dict[str, list[float]] = defaultdict(list)
    for row in valid:
        industries[row.industry].append(float(row.value))
        regimes[row.regime].append(row.forward_return * float(row.value))
    industry_means = [_mean(values) for values in industries.values()]
    industry_concentration = max(abs(value) for value in industry_means)
    contributions = [abs(value) for value in daily_spread]
    date_concentration = max(contributions) / sum(contributions) if sum(contributions) else 1.0
    regime_totals = [abs(sum(values)) for values in regimes.values()]
    regime_concentration = max(regime_totals) / sum(regime_totals) if sum(regime_totals) else 1.0
    net_spread = gross_spread - turnover * policy.cost_bps / 10_000
    codes: list[DiagnosticCode] = []
    if coverage < policy.minimum_coverage:
        codes.append(DiagnosticCode.LOW_COVERAGE)
    if missingness > policy.maximum_missingness:
        codes.append(DiagnosticCode.HIGH_MISSINGNESS)
    if stale_fraction > policy.maximum_stale_fraction:
        codes.append(DiagnosticCode.STALE_SIGNAL)
    if quantile_returns[-1] <= quantile_returns[0]:
        codes.append(DiagnosticCode.FLAT_QUANTILES)
    if turnover > policy.maximum_turnover:
        codes.append(DiagnosticCode.EXCESS_TURNOVER)
    if date_concentration > policy.maximum_date_concentration:
        codes.append(DiagnosticCode.DATE_CONCENTRATION)
    if regime_concentration > policy.maximum_regime_concentration:
        codes.append(DiagnosticCode.REGIME_CONCENTRATION)
    if net_spread <= 0:
        codes.append(DiagnosticCode.COST_ERASED)
    if not codes:
        codes.append(DiagnosticCode.PASS)
    return CheapDiagnosticReport(
        coverage,
        missingness,
        stale_fraction,
        _mean(daily_ic),
        _mean(daily_rank),
        residual_ic,
        quantile_returns,
        long_return,
        short_return,
        gross_spread,
        turnover,
        holding_decay,
        styles,
        industry_concentration,
        date_concentration,
        regime_concentration,
        net_spread,
        tuple(codes),
    )
