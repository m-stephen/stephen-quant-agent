from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime

from stephen_quant.factors import FactorDefinition
from stephen_quant.integrity.audit import audit_feature_timing
from stephen_quant.integrity.models import FeatureObservation

from .metrics import daily_correlations, peer_rank_correlation, rank_turnover, summarize_horizon
from .models import (
    AlphaCard,
    CorrelationSummary,
    EvaluationError,
    EvaluationLineage,
    EvaluationObservation,
    GroupSummary,
)


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationError(f"invalid ISO timestamp: {value}") from exc


def _validate_observations(observations: Sequence[EvaluationObservation]) -> None:
    if not observations:
        raise EvaluationError("evaluation requires observations")
    seen: set[tuple[str, str, str]] = set()
    for row in observations:
        key = (row.timestamp, row.instrument, row.horizon)
        if key in seen:
            raise EvaluationError(f"duplicate evaluation observation: {key}")
        seen.add(key)
        if not math.isfinite(row.factor_value) or not math.isfinite(row.forward_return):
            raise EvaluationError(f"non-finite observation: {key}")
        if _parse_iso(row.label_end_at) < _parse_iso(row.label_start_at):
            raise EvaluationError(f"label ends before it starts: {key}")
        finding = audit_feature_timing(
            FeatureObservation(
                feature_id="candidate",
                instrument=row.instrument,
                observation_at=row.timestamp,
                feature_available_at=row.factor_available_at,
                label_start_at=row.label_start_at,
                label_end_at=row.label_end_at,
            )
        )
        if not finding.passed:
            raise EvaluationError(f"future information detected: {finding.detail}")


def _horizon_sort_key(horizon: str) -> tuple[float, str]:
    match = re.search(r"\d+(?:\.\d+)?", horizon)
    return (float(match.group()) if match else math.inf, horizon)


def _group_summaries(
    observations: Sequence[EvaluationObservation],
    attribute: str,
    *,
    direction: int,
    min_cross_section: int,
) -> tuple[GroupSummary, ...]:
    groups: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in observations:
        groups[getattr(row, attribute)].append(row)

    summaries: list[GroupSummary] = []
    for name in sorted(groups):
        rows = groups[name]
        _, rank_ic = daily_correlations(
            rows, direction=direction, min_cross_section=min_cross_section
        )
        summaries.append(
            GroupSummary(
                group=name,
                observations=len(rows),
                dates=len(rank_ic),
                mean_rank_ic=sum(rank_ic) / len(rank_ic),
            )
        )
    return tuple(summaries)


def evaluate_alpha(
    definition: FactorDefinition,
    observations: Sequence[EvaluationObservation],
    lineage: EvaluationLineage,
    *,
    peer_factors: Mapping[str, Mapping[tuple[str, str], float]] | None = None,
    min_cross_section: int = 3,
    annualization_factor: int = 252,
) -> AlphaCard:
    """Evaluate a candidate without applying acceptance thresholds or final-test tuning."""

    if lineage.factor_id != definition.factor_id or lineage.factor_version != definition.version:
        raise EvaluationError("lineage factor identity does not match the definition")
    if not all(
        (
            lineage.snapshot_id,
            lineage.experiment_id,
            lineage.trial_id,
            lineage.code_version,
        )
    ):
        raise EvaluationError("lineage identifiers cannot be empty")
    if min_cross_section < 2:
        raise EvaluationError("min_cross_section must be at least two")
    _validate_observations(observations)

    by_horizon: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in observations:
        by_horizon[row.horizon].append(row)
    ordered_horizons = sorted(by_horizon, key=_horizon_sort_key)
    primary_horizon = ordered_horizons[0]
    primary = by_horizon[primary_horizon]

    horizon_metrics = tuple(
        summarize_horizon(
            horizon,
            by_horizon[horizon],
            direction=definition.direction,
            min_cross_section=min_cross_section,
            annualization_factor=annualization_factor,
        )
        for horizon in ordered_horizons
    )
    correlations = tuple(
        CorrelationSummary(
            factor_id=peer_id,
            mean_rank_correlation=result[0],
            dates=result[1],
        )
        for peer_id, result in (
            (
                peer_id,
                peer_rank_correlation(
                    primary,
                    values,
                    direction=definition.direction,
                    min_cross_section=min_cross_section,
                ),
            )
            for peer_id, values in sorted((peer_factors or {}).items())
        )
    )
    return AlphaCard(
        lineage=lineage,
        primary_horizon=primary_horizon,
        horizon_metrics=horizon_metrics,
        subperiods=_group_summaries(
            primary,
            "subperiod",
            direction=definition.direction,
            min_cross_section=min_cross_section,
        ),
        regimes=_group_summaries(
            primary,
            "regime",
            direction=definition.direction,
            min_cross_section=min_cross_section,
        ),
        turnover=rank_turnover(primary, direction=definition.direction),
        correlations=correlations,
    )
