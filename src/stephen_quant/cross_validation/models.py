from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SampleInterval:
    """Temporal envelope for one model sample and its overlapping label."""

    sample_id: str
    instrument: str
    feature_at: str
    label_start_at: str
    label_end_at: str


@dataclass(frozen=True)
class SplitLineage:
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str


@dataclass(frozen=True)
class FoldManifest:
    fold_id: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    test_groups: tuple[int, ...]
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    purged_ids: tuple[str, ...]
    embargoed_ids: tuple[str, ...]
    train_start_at: str
    train_end_at: str
    test_start_at: str
    test_end_at: str


@dataclass(frozen=True)
class PathSegment:
    group_id: int
    fold_id: str


@dataclass(frozen=True)
class OOSPath:
    path_id: str
    segments: tuple[PathSegment, ...]


@dataclass(frozen=True)
class SplitManifest:
    method: str
    lineage: SplitLineage
    samples_sha256: str
    n_groups: int
    n_test_groups: int
    embargo_seconds: int
    folds: tuple[FoldManifest, ...]
    paths: tuple[OOSPath, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


class CrossValidationError(ValueError):
    """Raised when a temporal split cannot satisfy integrity constraints."""
