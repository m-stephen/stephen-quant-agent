from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PointInTimeRecord:
    """Minimal metadata required to establish whether a datum was knowable at decision time."""

    source: str
    instrument: str
    effective_at: str
    available_at: str
    ingested_at: str
    vendor_version: str | None = None


@dataclass(frozen=True)
class FeatureObservation:
    """Timing envelope for one feature observation and its label."""

    feature_id: str
    instrument: str
    observation_at: str
    feature_available_at: str
    label_start_at: str
    label_end_at: str


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    hypothesis: str
    dataset_snapshot_id: str
    code_version: str
    search_space: str = "{}"
    status: str = "active"


@dataclass(frozen=True)
class TrialSpec:
    experiment_id: str
    model_name: str
    factor_set: str
    hyperparams: str
    seed: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
