from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import combinations
from statistics import NormalDist, stdev

from stephen_quant.cross_validation import SplitManifest
from stephen_quant.evaluation import average_ranks
from stephen_quant.integrity.audit import AuditFinding

from .models import DeflatedSharpeResult, FalsificationError, PBOResult

DSR_METHOD_VERSION = "bailey-lopez-de-prado-dsr-2014"
PBO_METHOD_VERSION = "cscv-on-cpcv-paths-1.0.0"
FOLD_PBO_METHOD_VERSION = "selection-pbo-on-purged-cpcv-folds-1.0.0"
EULER_MASCHERONI = 0.5772156649015329


def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    trial_sharpes: Sequence[float],
    recorded_trial_count: int,
    observations: int,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> DeflatedSharpeResult:
    """Test an unannualized per-observation Sharpe against a multiplicity benchmark."""

    values = tuple(float(value) for value in trial_sharpes)
    numeric = (observed_sharpe, skewness, excess_kurtosis, *values)
    if any(not math.isfinite(value) for value in numeric):
        raise FalsificationError("DSR inputs must be finite")
    if len(values) < 2:
        raise FalsificationError("DSR requires at least two Sharpe estimates")
    if not any(math.isclose(observed_sharpe, value) for value in values):
        raise FalsificationError("observed Sharpe must be present in the trial estimates")
    if recorded_trial_count < len(values):
        raise FalsificationError("recorded trial count cannot be smaller than Sharpe estimates")
    if observations < 2:
        raise FalsificationError("DSR requires at least two return observations")
    dispersion = stdev(values)
    if dispersion == 0:
        raise FalsificationError("DSR requires non-zero dispersion across trial Sharpes")

    if recorded_trial_count == 1:
        benchmark = 0.0
    else:
        normal = NormalDist()
        first = normal.inv_cdf(1 - 1 / recorded_trial_count)
        second = normal.inv_cdf(1 - 1 / (recorded_trial_count * math.e))
        expected_maximum = (1 - EULER_MASCHERONI) * first + EULER_MASCHERONI * second
        benchmark = dispersion * expected_maximum

    denominator_squared = (
        1
        - skewness * observed_sharpe
        + ((excess_kurtosis + 2) / 4) * observed_sharpe**2
    )
    if denominator_squared <= 0:
        raise FalsificationError("DSR moment adjustment is not positive")
    z_score = (
        (observed_sharpe - benchmark)
        * math.sqrt(observations - 1)
        / math.sqrt(denominator_squared)
    )
    return DeflatedSharpeResult(
        method_version=DSR_METHOD_VERSION,
        observed_sharpe=observed_sharpe,
        benchmark_sharpe=benchmark,
        probability=NormalDist().cdf(z_score),
        observations=observations,
        recorded_trial_count=recorded_trial_count,
        sharpe_estimates_used=len(values),
        sharpe_estimate_std=dispersion,
        skewness=skewness,
        excess_kurtosis=excess_kurtosis,
    )


def probability_of_backtest_overfitting(
    manifest: SplitManifest,
    path_scores: Mapping[str, Mapping[str, float]],
    audit_findings: Sequence[AuditFinding],
) -> PBOResult:
    """Apply symmetric selection tests to an audited matrix of CPCV OOS path scores."""

    if manifest.method != "combinatorial_purged_cross_validation":
        raise FalsificationError("PBO requires a CPCV split manifest")
    expected_audit = {
        (check, True, f"fold={fold.fold_id}")
        for fold in manifest.folds
        for check in (
            "train_test_disjoint",
            "no_label_overlap",
            "embargo_respected",
            "temporal_boundaries_recorded",
        )
    }
    supplied_audit = {
        (finding.check, finding.passed, finding.detail) for finding in audit_findings
    }
    if supplied_audit != expected_audit:
        raise FalsificationError("PBO requires a fully passing CPCV audit")
    path_ids = tuple(path.path_id for path in manifest.paths)
    if len(path_ids) < 4 or len(path_ids) % 2:
        raise FalsificationError("PBO requires an even number of at least four CPCV paths")
    configuration_ids = tuple(sorted(path_scores))
    if len(configuration_ids) < 2:
        raise FalsificationError("PBO requires at least two configurations")
    expected_paths = set(path_ids)
    for configuration_id in configuration_ids:
        scores = path_scores[configuration_id]
        if set(scores) != expected_paths:
            raise FalsificationError(
                f"configuration {configuration_id} does not cover the CPCV paths exactly"
            )
        if any(not math.isfinite(float(value)) for value in scores.values()):
            raise FalsificationError(f"configuration {configuration_id} has non-finite scores")

    logits: list[float] = []
    half = len(path_ids) // 2
    all_paths = set(path_ids)
    for in_sample in combinations(path_ids, half):
        out_of_sample = tuple(sorted(all_paths - set(in_sample)))
        in_scores = {
            configuration_id: sum(path_scores[configuration_id][path] for path in in_sample) / half
            for configuration_id in configuration_ids
        }
        selected = max(configuration_ids, key=lambda item: (in_scores[item], item))
        out_scores = [
            sum(path_scores[configuration_id][path] for path in out_of_sample) / half
            for configuration_id in configuration_ids
        ]
        ranks = average_ranks(out_scores)
        selected_rank = ranks[configuration_ids.index(selected)]
        relative_rank = selected_rank / (len(configuration_ids) + 1)
        logits.append(math.log(relative_rank / (1 - relative_rank)))

    return PBOResult(
        method_version=PBO_METHOD_VERSION,
        probability=sum(value <= 0 for value in logits) / len(logits),
        logits=tuple(logits),
        combinations=len(logits),
        paths=len(path_ids),
        configurations=len(configuration_ids),
        split_manifest_sha256=manifest.manifest_sha256,
    )


def probability_of_fold_selection_overfitting(
    manifest: SplitManifest,
    train_scores: Mapping[str, Mapping[str, float]],
    test_scores: Mapping[str, Mapping[str, float]],
    audit_findings: Sequence[AuditFinding],
) -> PBOResult:
    """Estimate selection PBO from audited purged-fold train and complementary OOS scores."""

    if manifest.method != "combinatorial_purged_cross_validation":
        raise FalsificationError("fold-selection PBO requires a CPCV split manifest")
    expected_audit = {
        (check, True, f"fold={fold.fold_id}")
        for fold in manifest.folds
        for check in (
            "train_test_disjoint",
            "no_label_overlap",
            "embargo_respected",
            "temporal_boundaries_recorded",
        )
    }
    supplied_audit = {
        (finding.check, finding.passed, finding.detail) for finding in audit_findings
    }
    if supplied_audit != expected_audit:
        raise FalsificationError("fold-selection PBO requires a fully passing CPCV audit")
    configuration_ids = tuple(sorted(train_scores))
    if configuration_ids != tuple(sorted(test_scores)) or len(configuration_ids) < 2:
        raise FalsificationError("fold-selection PBO requires matching candidate matrices")
    fold_ids = tuple(fold.fold_id for fold in manifest.folds)
    expected_folds = set(fold_ids)
    for configuration_id in configuration_ids:
        for matrix in (train_scores[configuration_id], test_scores[configuration_id]):
            if set(matrix) != expected_folds:
                raise FalsificationError(
                    f"configuration {configuration_id} does not cover CPCV folds exactly"
                )
            if any(not math.isfinite(float(value)) for value in matrix.values()):
                raise FalsificationError(
                    f"configuration {configuration_id} has non-finite fold scores"
                )
    logits: list[float] = []
    for fold_id in fold_ids:
        selected = max(
            configuration_ids,
            key=lambda item: (train_scores[item][fold_id], item),
        )
        oos_values = [test_scores[item][fold_id] for item in configuration_ids]
        ranks = average_ranks(oos_values)
        selected_rank = ranks[configuration_ids.index(selected)]
        relative_rank = selected_rank / (len(configuration_ids) + 1)
        logits.append(math.log(relative_rank / (1 - relative_rank)))
    return PBOResult(
        method_version=FOLD_PBO_METHOD_VERSION,
        probability=sum(value <= 0 for value in logits) / len(logits),
        logits=tuple(logits),
        combinations=len(logits),
        paths=len(fold_ids),
        configurations=len(configuration_ids),
        split_manifest_sha256=manifest.manifest_sha256,
    )
