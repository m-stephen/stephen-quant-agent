from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import stdev

from stephen_quant.baseline import BaselineObservation, BaselineReport
from stephen_quant.evaluation import EvaluationObservation

RETURN_MOMENTS_VERSION = "bias-corrected-sample-moments-1.0.0"


def canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execution_memberships(
    memberships: dict[str, tuple[str, ...]], execution_dates: list[str]
) -> dict[str, tuple[str, ...]]:
    ordered = sorted(memberships)
    result: dict[str, tuple[str, ...]] = {}
    offset = 0
    latest: tuple[str, ...] = ()
    for execution_day in sorted(execution_dates):
        while offset < len(ordered) and ordered[offset] < execution_day:
            latest = memberships[ordered[offset]]
            offset += 1
        result[execution_day] = latest
    return result


def shared_non_overlapping(
    rows: tuple[BaselineObservation, ...], horizon: int, minimum_eligible: int
) -> tuple[BaselineObservation, ...]:
    if horizon < 1 or minimum_eligible < 1:
        raise ValueError("research epoch horizon and minimum eligibility must be positive")
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.eligible:
            counts[row.execution_at] += 1
    dates = sorted(day for day, count in counts.items() if count >= minimum_eligible)
    selected = set(dates[::horizon])
    if len(selected) < 2:
        raise ValueError("research epoch has insufficient shared non-overlapping periods")
    return tuple(row for row in rows if row.execution_at in selected)


def raw_sharpe(report: BaselineReport) -> float:
    values = [item.net_return for item in report.periods]
    dispersion = stdev(values)
    return 0.0 if dispersion == 0 else (sum(values) / len(values)) / dispersion


def evaluation_rows(
    rows: tuple[BaselineObservation, ...], *, horizon: str
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
        for row in rows
        if row.eligible
    )


@dataclass(frozen=True)
class ReturnMoments:
    method_version: str
    observations: int
    skewness: float
    excess_kurtosis: float


def sample_return_moments(values: list[float] | tuple[float, ...]) -> ReturnMoments:
    """Return bias-corrected sample skewness and excess kurtosis."""

    returns = tuple(float(value) for value in values)
    if len(returns) < 4:
        raise ValueError("return moments require at least four observations")
    if any(not math.isfinite(value) for value in returns):
        raise ValueError("return moments require finite observations")
    count = len(returns)
    mean = sum(returns) / count
    sample_variance = sum((value - mean) ** 2 for value in returns) / (count - 1)
    if sample_variance <= 0:
        raise ValueError("return moments require non-zero sample variance")
    deviation = math.sqrt(sample_variance)
    standardized_third = sum(((value - mean) / deviation) ** 3 for value in returns)
    standardized_fourth = sum(((value - mean) / deviation) ** 4 for value in returns)
    skewness = count * standardized_third / ((count - 1) * (count - 2))
    excess_kurtosis = (
        count
        * (count + 1)
        * standardized_fourth
        / ((count - 1) * (count - 2) * (count - 3))
        - 3 * (count - 1) ** 2 / ((count - 2) * (count - 3))
    )
    return ReturnMoments(
        RETURN_MOMENTS_VERSION,
        count,
        skewness,
        excess_kurtosis,
    )
