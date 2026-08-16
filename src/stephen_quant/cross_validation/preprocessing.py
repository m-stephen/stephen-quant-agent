from __future__ import annotations

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
