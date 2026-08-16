from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from itertools import combinations

from .models import (
    CrossValidationError,
    FoldManifest,
    OOSPath,
    PathSegment,
    SampleInterval,
    SplitLineage,
    SplitManifest,
)


def parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CrossValidationError(f"invalid ISO timestamp: {value}") from exc


def intervals_overlap(left: SampleInterval, right: SampleInterval) -> bool:
    return not (
        parse_timestamp(left.label_end_at) < parse_timestamp(right.label_start_at)
        or parse_timestamp(right.label_end_at) < parse_timestamp(left.label_start_at)
    )


def _is_embargoed(
    candidate: SampleInterval,
    test_samples: Sequence[SampleInterval],
    embargo: timedelta,
) -> bool:
    if embargo <= timedelta(0):
        return False
    feature_time = parse_timestamp(candidate.feature_at)
    return any(
        test_end < feature_time <= test_end + embargo
        for test_end in (parse_timestamp(sample.label_end_at) for sample in test_samples)
    )


def purge_and_embargo(
    train_candidates: Sequence[SampleInterval],
    test_samples: Sequence[SampleInterval],
    *,
    embargo: timedelta,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Return retained, purged, and embargoed training IDs in deterministic order."""

    if embargo < timedelta(0):
        raise CrossValidationError("embargo cannot be negative")
    retained: list[str] = []
    purged: list[str] = []
    embargoed: list[str] = []
    for candidate in sorted(train_candidates, key=lambda item: (item.feature_at, item.sample_id)):
        if any(intervals_overlap(candidate, test) for test in test_samples):
            purged.append(candidate.sample_id)
        elif _is_embargoed(candidate, test_samples, embargo):
            embargoed.append(candidate.sample_id)
        else:
            retained.append(candidate.sample_id)
    return tuple(retained), tuple(purged), tuple(embargoed)


def _validate_samples(samples: Sequence[SampleInterval]) -> None:
    if not samples:
        raise CrossValidationError("CPCV requires samples")
    seen: set[str] = set()
    for sample in samples:
        if not sample.sample_id:
            raise CrossValidationError("sample_id cannot be empty")
        if sample.sample_id in seen:
            raise CrossValidationError(f"duplicate sample_id: {sample.sample_id}")
        seen.add(sample.sample_id)
        feature_time = parse_timestamp(sample.feature_at)
        label_start = parse_timestamp(sample.label_start_at)
        label_end = parse_timestamp(sample.label_end_at)
        if feature_time >= label_start:
            raise CrossValidationError(f"feature is not earlier than label: {sample.sample_id}")
        if label_end < label_start:
            raise CrossValidationError(f"label ends before it starts: {sample.sample_id}")


def _time_groups(samples: Sequence[SampleInterval], n_groups: int) -> tuple[tuple[str, ...], ...]:
    by_time: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        by_time[sample.feature_at].append(sample.sample_id)
    timestamps = sorted(by_time, key=parse_timestamp)
    if len(timestamps) < n_groups:
        raise CrossValidationError(
            f"n_groups={n_groups} exceeds unique feature timestamps={len(timestamps)}"
        )

    size, remainder = divmod(len(timestamps), n_groups)
    groups: list[tuple[str, ...]] = []
    offset = 0
    for group_id in range(n_groups):
        width = size + (1 if group_id < remainder else 0)
        group_times = timestamps[offset : offset + width]
        groups.append(
            tuple(
                sample_id
                for timestamp in group_times
                for sample_id in sorted(by_time[timestamp])
            )
        )
        offset += width
    return tuple(groups)


def _sample_hash(samples: Sequence[SampleInterval]) -> str:
    canonical = [
        {
            "sample_id": sample.sample_id,
            "instrument": sample.instrument,
            "feature_at": sample.feature_at,
            "label_start_at": sample.label_start_at,
            "label_end_at": sample.label_end_at,
        }
        for sample in sorted(samples, key=lambda item: item.sample_id)
    ]
    payload = json.dumps(canonical, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _boundaries(sample_ids: Sequence[str], by_id: dict[str, SampleInterval]) -> tuple[str, str]:
    if not sample_ids:
        return "", ""
    timestamps = sorted((by_id[sample_id].feature_at for sample_id in sample_ids), key=parse_timestamp)
    return timestamps[0], timestamps[-1]


def _build_paths(
    folds: Sequence[FoldManifest],
    *,
    n_groups: int,
    n_test_groups: int,
) -> tuple[OOSPath, ...]:
    path_count = math.comb(n_groups - 1, n_test_groups - 1)
    folds_by_group: dict[int, list[str]] = defaultdict(list)
    for fold in folds:
        for group_id in fold.test_groups:
            folds_by_group[group_id].append(fold.fold_id)

    paths: list[OOSPath] = []
    for path_id in range(path_count):
        segments = tuple(
            PathSegment(group_id=group_id, fold_id=sorted(folds_by_group[group_id])[path_id])
            for group_id in range(n_groups)
        )
        paths.append(OOSPath(path_id=f"path_{path_id:03d}", segments=segments))
    return tuple(paths)


def generate_cpcv_manifest(
    samples: Sequence[SampleInterval],
    lineage: SplitLineage,
    *,
    n_groups: int,
    n_test_groups: int,
    embargo: timedelta = timedelta(0),
) -> SplitManifest:
    _validate_samples(samples)
    if not all((lineage.snapshot_id, lineage.experiment_id, lineage.trial_id, lineage.code_version)):
        raise CrossValidationError("split lineage identifiers cannot be empty")
    if n_groups < 2:
        raise CrossValidationError("n_groups must be at least two")
    if not 1 <= n_test_groups < n_groups:
        raise CrossValidationError("n_test_groups must be between one and n_groups - 1")
    if embargo < timedelta(0):
        raise CrossValidationError("embargo cannot be negative")

    ordered = sorted(samples, key=lambda item: (parse_timestamp(item.feature_at), item.sample_id))
    by_id = {sample.sample_id: sample for sample in ordered}
    groups = _time_groups(ordered, n_groups)
    folds: list[FoldManifest] = []
    for fold_number, test_groups in enumerate(combinations(range(n_groups), n_test_groups)):
        test_ids = tuple(sample_id for group_id in test_groups for sample_id in groups[group_id])
        test_id_set = set(test_ids)
        train_candidates = [sample for sample in ordered if sample.sample_id not in test_id_set]
        test_samples = [by_id[sample_id] for sample_id in test_ids]
        train_ids, purged_ids, embargoed_ids = purge_and_embargo(
            train_candidates, test_samples, embargo=embargo
        )
        if not train_ids:
            raise CrossValidationError(f"fold {fold_number} has no training samples after hygiene")
        train_start, train_end = _boundaries(train_ids, by_id)
        test_start, test_end = _boundaries(test_ids, by_id)
        folds.append(
            FoldManifest(
                fold_id=f"fold_{fold_number:03d}",
                snapshot_id=lineage.snapshot_id,
                experiment_id=lineage.experiment_id,
                trial_id=lineage.trial_id,
                test_groups=test_groups,
                train_ids=train_ids,
                test_ids=test_ids,
                purged_ids=purged_ids,
                embargoed_ids=embargoed_ids,
                train_start_at=train_start,
                train_end_at=train_end,
                test_start_at=test_start,
                test_end_at=test_end,
            )
        )

    return SplitManifest(
        method="combinatorial_purged_cross_validation",
        lineage=lineage,
        samples_sha256=_sample_hash(ordered),
        n_groups=n_groups,
        n_test_groups=n_test_groups,
        embargo_seconds=int(embargo.total_seconds()),
        folds=tuple(folds),
        paths=_build_paths(folds, n_groups=n_groups, n_test_groups=n_test_groups),
    )
