from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.evaluation.metrics import daily_correlations
from stephen_quant.integrity.audit import audit_feature_timing
from stephen_quant.integrity.models import FeatureObservation

from .models import FalsificationError, PlaceboResult

PLACEBO_METHOD_VERSION = "cross-sectional-placebo-1.0.0"


def _seed(base_seed: int, method: str, repetition: int) -> int:
    payload = f"{base_seed}:{method}:{repetition}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _validate_rows(
    observations: Sequence[EvaluationObservation], horizon: str
) -> tuple[EvaluationObservation, ...]:
    rows = tuple(row for row in observations if row.horizon == horizon)
    if not rows:
        raise FalsificationError(f"no observations for horizon {horizon}")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.timestamp, row.instrument)
        if key in seen:
            raise FalsificationError(f"duplicate placebo observation: {key}")
        seen.add(key)
        if not math.isfinite(row.factor_value) or not math.isfinite(row.forward_return):
            raise FalsificationError(f"non-finite placebo observation: {key}")
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
            raise FalsificationError(f"future information detected: {finding.detail}")
    return rows


def _mean_rank_ic(
    rows: Sequence[EvaluationObservation], *, direction: int, min_cross_section: int
) -> float:
    try:
        _, values = daily_correlations(
            rows, direction=direction, min_cross_section=min_cross_section
        )
    except ValueError as exc:
        raise FalsificationError(str(exc)) from exc
    return sum(values) / len(values)


def _permuted_rows(
    rows: Sequence[EvaluationObservation], *, field: str, seed: int
) -> tuple[EvaluationObservation, ...]:
    groups: dict[str, list[EvaluationObservation]] = defaultdict(list)
    for row in rows:
        groups[row.timestamp].append(row)

    shuffled: list[EvaluationObservation] = []
    generator = random.Random(seed)
    for timestamp in sorted(groups):
        cross_section = sorted(groups[timestamp], key=lambda row: row.instrument)
        values = [getattr(row, field) for row in cross_section]
        generator.shuffle(values)
        shuffled.extend(
            replace(row, **{field: value})
            for row, value in zip(cross_section, values, strict=True)
        )
    return tuple(shuffled)


def run_placebo(
    observations: Sequence[EvaluationObservation],
    *,
    horizon: str,
    direction: int,
    method: str,
    seed: int,
    repetitions: int = 199,
    min_cross_section: int = 3,
) -> PlaceboResult:
    """Break the factor/return link within each date and form a null distribution."""

    fields = {"signal_shuffle": "factor_value", "return_permutation": "forward_return"}
    if method not in fields:
        raise FalsificationError(f"unknown placebo method: {method}")
    if direction not in {-1, 1}:
        raise FalsificationError("direction must be -1 or 1")
    if repetitions < 1:
        raise FalsificationError("repetitions must be positive")
    if min_cross_section < 2:
        raise FalsificationError("min_cross_section must be at least two")

    rows = _validate_rows(observations, horizon)
    observed = _mean_rank_ic(rows, direction=direction, min_cross_section=min_cross_section)
    placebo_scores = tuple(
        _mean_rank_ic(
            _permuted_rows(
                rows,
                field=fields[method],
                seed=_seed(seed, method, repetition),
            ),
            direction=direction,
            min_cross_section=min_cross_section,
        )
        for repetition in range(repetitions)
    )
    p_value = (1 + sum(score >= observed for score in placebo_scores)) / (repetitions + 1)
    return PlaceboResult(
        method=method,
        method_version=PLACEBO_METHOD_VERSION,
        seed=seed,
        repetitions=repetitions,
        observed_mean_rank_ic=observed,
        placebo_mean_rank_ics=placebo_scores,
        empirical_p_value=p_value,
    )
