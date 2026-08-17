from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import pairwise
from statistics import stdev

from .models import EvaluationError, EvaluationObservation, MetricSummary


def _validate_numeric(values: Sequence[float], name: str) -> list[float]:
    converted = [float(value) for value in values]
    if any(not math.isfinite(value) for value in converted):
        raise EvaluationError(f"{name} contains non-finite values")
    return converted


def pearson_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise EvaluationError("correlation inputs must have equal length")
    if len(left) < 2:
        raise EvaluationError("correlation requires at least two observations")
    x = _validate_numeric(left, "left input")
    y = _validate_numeric(right, "right input")
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y, strict=True))
    x_scale = math.sqrt(sum((value - x_mean) ** 2 for value in x))
    y_scale = math.sqrt(sum((value - y_mean) ** 2 for value in y))
    if x_scale == 0 or y_scale == 0:
        raise EvaluationError("correlation is undefined for a constant input")
    return numerator / (x_scale * y_scale)


def average_ranks(values: Sequence[float]) -> list[float]:
    numeric = _validate_numeric(values, "rank input")
    ordered = sorted(enumerate(numeric), key=lambda item: item[1])
    ranks = [0.0] * len(numeric)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = (start + 1 + end) / 2
        for position in range(start, end):
            ranks[ordered[position][0]] = average_rank
        start = end
    return ranks


def spearman_correlation(left: Sequence[float], right: Sequence[float]) -> float:
    return pearson_correlation(average_ranks(left), average_ranks(right))


def daily_correlations(
    observations: Sequence[EvaluationObservation],
    *,
    direction: int,
    min_cross_section: int,
) -> tuple[list[float], list[float]]:
    by_date: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for observation in observations:
        by_date[observation.timestamp].append(observation)

    daily_ic: list[float] = []
    daily_rank_ic: list[float] = []
    for timestamp in sorted(by_date):
        cross_section = by_date[timestamp]
        if len(cross_section) < min_cross_section:
            raise EvaluationError(
                f"cross-section {timestamp} has {len(cross_section)} observations; "
                f"minimum is {min_cross_section}"
            )
        factors = [direction * row.factor_value for row in cross_section]
        returns = [row.forward_return for row in cross_section]
        if len(set(factors)) < 2 or len(set(returns)) < 2:
            continue
        daily_ic.append(pearson_correlation(factors, returns))
        daily_rank_ic.append(spearman_correlation(factors, returns))
    return daily_ic, daily_rank_ic


def _information_ratio(values: Sequence[float], annualization_factor: int) -> float | None:
    if len(values) < 2:
        return None
    dispersion = stdev(values)
    if dispersion == 0:
        return None
    return (sum(values) / len(values)) / dispersion * math.sqrt(annualization_factor)


def summarize_horizon(
    horizon: str,
    observations: Sequence[EvaluationObservation],
    *,
    direction: int,
    min_cross_section: int = 3,
    annualization_factor: int = 252,
) -> MetricSummary:
    if annualization_factor < 1:
        raise EvaluationError("annualization_factor must be positive")
    daily_ic, daily_rank_ic = daily_correlations(
        observations, direction=direction, min_cross_section=min_cross_section
    )
    if len(daily_ic) < 2:
        raise EvaluationError(f"horizon {horizon} requires at least two evaluation dates")
    return MetricSummary(
        horizon=horizon,
        observations=len(observations),
        dates=len(daily_ic),
        mean_ic=sum(daily_ic) / len(daily_ic),
        mean_rank_ic=sum(daily_rank_ic) / len(daily_rank_ic),
        icir=_information_ratio(daily_ic, annualization_factor),
        rank_icir=_information_ratio(daily_rank_ic, annualization_factor),
        ic_hit_rate=sum(value > 0 for value in daily_ic) / len(daily_ic),
        rank_ic_hit_rate=sum(value > 0 for value in daily_rank_ic) / len(daily_rank_ic),
    )


def rank_turnover(observations: Sequence[EvaluationObservation], *, direction: int) -> float:
    by_date: dict[str, dict[str, float]] = defaultdict(dict)
    for row in observations:
        by_date[row.timestamp][row.instrument] = direction * row.factor_value

    dates = sorted(by_date)
    if len(dates) < 2:
        raise EvaluationError("turnover requires at least two evaluation dates")
    changes: list[float] = []
    for previous_date, current_date in pairwise(dates):
        common = sorted(set(by_date[previous_date]) & set(by_date[current_date]))
        if len(common) < 2:
            raise EvaluationError(
                f"turnover transition {previous_date}->{current_date} needs two common instruments"
            )
        previous_ranks = average_ranks([by_date[previous_date][item] for item in common])
        current_ranks = average_ranks([by_date[current_date][item] for item in common])
        denominator = max(len(common) - 1, 1)
        changes.extend(
            abs(current - previous) / denominator
            for previous, current in zip(previous_ranks, current_ranks, strict=True)
        )
    return sum(changes) / len(changes)


def peer_rank_correlation(
    observations: Sequence[EvaluationObservation],
    peer_values: Mapping[tuple[str, str], float],
    *,
    direction: int,
    min_cross_section: int = 3,
) -> tuple[float, int]:
    by_date: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in observations:
        if (row.timestamp, row.instrument) in peer_values:
            by_date[row.timestamp].append(row)

    correlations: list[float] = []
    for timestamp in sorted(by_date):
        rows = by_date[timestamp]
        if len(rows) < min_cross_section:
            continue
        candidate = [direction * row.factor_value for row in rows]
        peer = [peer_values[(row.timestamp, row.instrument)] for row in rows]
        if len(set(candidate)) < 2 or len(set(peer)) < 2:
            continue
        correlations.append(spearman_correlation(candidate, peer))
    if not correlations:
        raise EvaluationError("peer correlation has no valid cross-sections")
    return sum(correlations) / len(correlations), len(correlations)
