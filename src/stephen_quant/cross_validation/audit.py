from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from stephen_quant.integrity.audit import AuditFinding

from .engine import embargo_affects_any, interval_sets_overlap
from .models import FoldManifest, SampleInterval, SplitManifest


def audit_fold(
    fold: FoldManifest,
    samples: Sequence[SampleInterval],
    *,
    embargo: timedelta,
) -> tuple[AuditFinding, ...]:
    by_id = {sample.sample_id: sample for sample in samples}
    train = [by_id[sample_id] for sample_id in fold.train_ids]
    test = [by_id[sample_id] for sample_id in fold.test_ids]
    disjoint = not (set(fold.train_ids) & set(fold.test_ids))
    no_overlap = not interval_sets_overlap(train, test)
    no_embargo = not embargo_affects_any(train, test, embargo)
    complete_lineage = all(
        (
            fold.fold_id,
            fold.snapshot_id,
            fold.experiment_id,
            fold.trial_id,
            fold.train_start_at,
            fold.train_end_at,
            fold.test_start_at,
            fold.test_end_at,
        )
    )
    return (
        AuditFinding("train_test_disjoint", disjoint, f"fold={fold.fold_id}"),
        AuditFinding("no_label_overlap", no_overlap, f"fold={fold.fold_id}"),
        AuditFinding("embargo_respected", no_embargo, f"fold={fold.fold_id}"),
        AuditFinding("temporal_boundaries_recorded", complete_lineage, f"fold={fold.fold_id}"),
    )


def audit_manifest(
    manifest: SplitManifest,
    samples: Sequence[SampleInterval],
) -> tuple[AuditFinding, ...]:
    embargo = timedelta(seconds=manifest.embargo_seconds)
    return tuple(
        finding
        for fold in manifest.folds
        for finding in audit_fold(fold, samples, embargo=embargo)
    )
