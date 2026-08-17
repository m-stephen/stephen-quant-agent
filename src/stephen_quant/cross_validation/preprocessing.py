from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .models import FoldManifest


class FoldPreprocessor(Protocol):
    def fit(self, sample_ids: Sequence[str]) -> None: ...

    def transform(self, sample_ids: Sequence[str]) -> Sequence[Any]: ...


@dataclass(frozen=True)
class FoldTransformResult:
    fold_id: str
    transformed_train: tuple[Any, ...]
    transformed_test: tuple[Any, ...]


class WinsorZScorePreprocessor:
    """Winsorize and standardize with parameters learned from training IDs only."""

    def __init__(
        self,
        values: dict[str, float],
        *,
        lower_quantile: float = 0.01,
        upper_quantile: float = 0.99,
    ) -> None:
        if not 0 <= lower_quantile < upper_quantile <= 1:
            raise ValueError("winsor quantiles must satisfy 0 <= lower < upper <= 1")
        if not values or any(not math.isfinite(value) for value in values.values()):
            raise ValueError("preprocessor values must be non-empty and finite")
        self._values = values
        self._lower_quantile = lower_quantile
        self._upper_quantile = upper_quantile
        self._parameters: tuple[float, float, float] | None = None

    @staticmethod
    def _quantile(values: list[float], probability: float) -> float:
        position = probability * (len(values) - 1)
        lower = int(position)
        upper = min(lower + 1, len(values) - 1)
        weight = position - lower
        return values[lower] * (1 - weight) + values[upper] * weight

    def fit(self, sample_ids: Sequence[str]) -> None:
        if not sample_ids or any(sample_id not in self._values for sample_id in sample_ids):
            raise ValueError("training IDs must be non-empty and present in values")
        training = sorted(self._values[sample_id] for sample_id in sample_ids)
        lower = self._quantile(training, self._lower_quantile)
        upper = self._quantile(training, self._upper_quantile)
        clipped = [min(max(value, lower), upper) for value in training]
        center = sum(clipped) / len(clipped)
        scale = math.sqrt(sum((value - center) ** 2 for value in clipped) / len(clipped))
        self._parameters = (lower, upper, center if scale else 0.0)
        self._scale = scale

    def transform(self, sample_ids: Sequence[str]) -> Sequence[float]:
        if self._parameters is None:
            raise ValueError("preprocessor must be fitted before transform")
        if any(sample_id not in self._values for sample_id in sample_ids):
            raise ValueError("transform IDs must be present in values")
        lower, upper, center = self._parameters
        if self._scale == 0:
            return tuple(0.0 for _ in sample_ids)
        return tuple(
            (min(max(self._values[sample_id], lower), upper) - center) / self._scale
            for sample_id in sample_ids
        )


def fit_transform_fold(
    fold: FoldManifest,
    factory: Callable[[], FoldPreprocessor],
) -> FoldTransformResult:
    """Create one fresh transformer, fit on train IDs only, then transform both sides."""

    transformer = factory()
    transformer.fit(fold.train_ids)
    return FoldTransformResult(
        fold_id=fold.fold_id,
        transformed_train=tuple(transformer.transform(fold.train_ids)),
        transformed_test=tuple(transformer.transform(fold.test_ids)),
    )
