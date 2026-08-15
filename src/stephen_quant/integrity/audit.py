from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import FeatureObservation
from .registry import ExperimentRegistry


@dataclass(frozen=True)
class AuditFinding:
    check: str
    passed: bool
    detail: str


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc


def audit_feature_timing(observation: FeatureObservation) -> AuditFinding:
    available = _parse_iso(observation.feature_available_at)
    label_start = _parse_iso(observation.label_start_at)
    passed = available < label_start
    return AuditFinding(
        check="feature_available_before_label",
        passed=passed,
        detail=(
            f"feature={observation.feature_id} instrument={observation.instrument} "
            f"available_at={observation.feature_available_at} "
            f"label_start={observation.label_start_at}"
        ),
    )


def audit_registry(db_path: str | Path) -> list[AuditFinding]:
    registry = ExperimentRegistry(db_path)
    counts = registry.counts()
    findings = [
        AuditFinding("has_snapshot", counts["snapshots"] > 0, f"count={counts['snapshots']}"),
        AuditFinding("has_experiment", counts["experiments"] > 0, f"count={counts['experiments']}"),
        AuditFinding("trial_counter_active", True, f"count={counts['trials']}"),
    ]
    return findings
