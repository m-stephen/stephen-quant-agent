from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.cross_validation import (
    CrossValidationError,
    SampleInterval,
    SplitLineage,
    audit_manifest,
    embargo_affects_any,
    fit_transform_fold,
    generate_cpcv_manifest,
    interval_sets_overlap,
    purge_and_embargo,
    write_split_artifacts,
)


def test_indexed_interval_and_embargo_queries_match_closed_boundaries() -> None:
    test = (_sample("test", date(2025, 1, 1), date(2025, 1, 10), date(2025, 1, 13)),)
    overlap = (_sample("overlap", date(2025, 1, 1), date(2025, 1, 13), date(2025, 1, 14)),)
    separate = (_sample("separate", date(2025, 1, 1), date(2025, 1, 14), date(2025, 1, 15)),)
    embargoed = (_sample("embargoed", date(2025, 1, 15), date(2025, 1, 16), date(2025, 1, 17)),)

    assert interval_sets_overlap(overlap, test)
    assert not interval_sets_overlap(separate, test)
    assert embargo_affects_any(embargoed, test, timedelta(days=2))
    assert not embargo_affects_any(embargoed, test, timedelta(days=1))


def _sample(
    sample_id: str,
    feature_day: date,
    label_start_day: date,
    label_end_day: date,
    instrument: str = "A",
) -> SampleInterval:
    return SampleInterval(
        sample_id=sample_id,
        instrument=instrument,
        feature_at=f"{feature_day.isoformat()}T15:00:00+08:00",
        label_start_at=f"{label_start_day.isoformat()}T09:30:00+08:00",
        label_end_at=f"{label_end_day.isoformat()}T15:00:00+08:00",
    )


def _lineage() -> SplitLineage:
    return SplitLineage(
        snapshot_id="snap_fixture",
        experiment_id="exp_fixture",
        trial_id="trial_fixture",
        code_version="test-sha",
    )


def _daily_samples(days: int = 24, instruments: tuple[str, ...] = ("A",)) -> list[SampleInterval]:
    start = date(2025, 1, 1)
    samples: list[SampleInterval] = []
    for day_index in range(days):
        feature_day = start + timedelta(days=day_index)
        for instrument in instruments:
            samples.append(
                _sample(
                    f"{feature_day.isoformat()}-{instrument}",
                    feature_day,
                    feature_day + timedelta(days=1),
                    feature_day + timedelta(days=3),
                    instrument,
                )
            )
    return samples


def test_purge_and_embargo_use_label_intervals_and_exact_boundaries() -> None:
    test = [_sample("test", date(2025, 1, 4), date(2025, 1, 5), date(2025, 1, 10))]
    candidates = [
        _sample("before", date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 4)),
        _sample("overlap", date(2025, 1, 3), date(2025, 1, 4), date(2025, 1, 5)),
        _sample("embargo_start", date(2025, 1, 11), date(2025, 1, 13), date(2025, 1, 14)),
        _sample("embargo_end", date(2025, 1, 12), date(2025, 1, 13), date(2025, 1, 15)),
        _sample("after", date(2025, 1, 13), date(2025, 1, 14), date(2025, 1, 16)),
    ]

    retained, purged, embargoed = purge_and_embargo(
        candidates, test, embargo=timedelta(days=2)
    )

    assert retained == ("before", "after")
    assert purged == ("overlap",)
    assert embargoed == ("embargo_start", "embargo_end")


def test_zero_embargo_does_not_remove_post_test_samples() -> None:
    test = [_sample("test", date(2025, 1, 4), date(2025, 1, 5), date(2025, 1, 10))]
    candidate = _sample("next", date(2025, 1, 11), date(2025, 1, 12), date(2025, 1, 13))

    retained, purged, embargoed = purge_and_embargo(
        [candidate], test, embargo=timedelta(0)
    )

    assert retained == ("next",)
    assert not purged
    assert not embargoed


def test_cpcv_combinations_paths_and_hashes_are_deterministic() -> None:
    samples = _daily_samples()
    first = generate_cpcv_manifest(
        samples,
        _lineage(),
        n_groups=6,
        n_test_groups=2,
        embargo=timedelta(days=1),
    )
    second = generate_cpcv_manifest(
        list(reversed(samples)),
        _lineage(),
        n_groups=6,
        n_test_groups=2,
        embargo=timedelta(days=1),
    )

    assert len(first.folds) == 15
    assert len(first.paths) == 5
    assert first.to_json() == second.to_json()
    assert first.manifest_sha256 == second.manifest_sha256
    assert all(len(path.segments) == 6 for path in first.paths)
    assert all({segment.group_id for segment in path.segments} == set(range(6)) for path in first.paths)
    assert all(fold.snapshot_id == "snap_fixture" for fold in first.folds)
    assert all(fold.train_start_at and fold.test_start_at for fold in first.folds)
    assert all(finding.passed for finding in audit_manifest(first, samples))


def test_split_manifest_and_audit_artifacts_are_deterministic(tmp_path: Path) -> None:
    samples = _daily_samples()
    manifest = generate_cpcv_manifest(
        samples,
        _lineage(),
        n_groups=4,
        n_test_groups=1,
        embargo=timedelta(days=1),
    )
    findings = audit_manifest(manifest, samples)

    first = write_split_artifacts(manifest, findings, tmp_path / "first")
    second = write_split_artifacts(manifest, findings, tmp_path / "second")
    audit_payload = json.loads(first.audit_path.read_text(encoding="utf-8"))

    assert first.manifest_sha256 == second.manifest_sha256
    assert first.audit_sha256 == second.audit_sha256
    assert all(item["passed"] for item in audit_payload)
    assert first.manifest_path.read_text(encoding="utf-8").endswith("\n")


def test_complete_cross_sections_stay_in_one_time_group() -> None:
    samples = _daily_samples(days=12, instruments=("A", "B", "C"))
    manifest = generate_cpcv_manifest(
        samples,
        _lineage(),
        n_groups=3,
        n_test_groups=1,
    )
    by_time: dict[str, set[str]] = {}
    for sample in samples:
        by_time.setdefault(sample.feature_at, set()).add(sample.sample_id)

    for fold in manifest.folds:
        test_ids = set(fold.test_ids)
        for timestamp_ids in by_time.values():
            assert not (timestamp_ids & test_ids) or timestamp_ids <= test_ids


def test_odd_group_count_also_produces_complete_paths() -> None:
    manifest = generate_cpcv_manifest(
        _daily_samples(days=25),
        _lineage(),
        n_groups=5,
        n_test_groups=2,
    )

    assert len(manifest.folds) == 10
    assert len(manifest.paths) == 4
    assert all({segment.group_id for segment in path.segments} == set(range(5)) for path in manifest.paths)


def test_fold_preprocessor_fits_on_train_ids_only() -> None:
    manifest = generate_cpcv_manifest(
        _daily_samples(),
        _lineage(),
        n_groups=4,
        n_test_groups=1,
    )
    created: list[RecordingTransformer] = []

    class RecordingTransformer:
        def __init__(self) -> None:
            self.fit_ids: tuple[str, ...] = ()

        def fit(self, sample_ids: tuple[str, ...]) -> None:
            self.fit_ids = tuple(sample_ids)

        def transform(self, sample_ids: tuple[str, ...]) -> tuple[str, ...]:
            return tuple(f"scaled:{sample_id}" for sample_id in sample_ids)

    def factory() -> RecordingTransformer:
        transformer = RecordingTransformer()
        created.append(transformer)
        return transformer

    fold = manifest.folds[0]
    result = fit_transform_fold(fold, factory)

    assert created[0].fit_ids == fold.train_ids
    assert not (set(created[0].fit_ids) & set(fold.test_ids))
    assert len(result.transformed_test) == len(fold.test_ids)


def test_invalid_samples_and_split_parameters_fail() -> None:
    samples = _daily_samples(days=6)
    with pytest.raises(CrossValidationError, match="exceeds unique"):
        generate_cpcv_manifest(samples, _lineage(), n_groups=7, n_test_groups=1)
    with pytest.raises(CrossValidationError, match="between one"):
        generate_cpcv_manifest(samples, _lineage(), n_groups=3, n_test_groups=3)

    duplicate = samples + [samples[0]]
    with pytest.raises(CrossValidationError, match="duplicate"):
        generate_cpcv_manifest(duplicate, _lineage(), n_groups=3, n_test_groups=1)

    bad = [_sample("bad", date(2025, 1, 2), date(2025, 1, 2), date(2025, 1, 3))]
    with pytest.raises(CrossValidationError, match="not earlier"):
        generate_cpcv_manifest(bad, _lineage(), n_groups=2, n_test_groups=1)
