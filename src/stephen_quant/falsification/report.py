from __future__ import annotations

from .models import (
    METHOD_VERSION,
    AlphaCourtReport,
    AuditDecision,
    AuditThresholds,
    DeflatedSharpeResult,
    FalsificationError,
    FalsificationLineage,
    PBOResult,
    PlaceboResult,
)


def build_alpha_court_report(
    lineage: FalsificationLineage,
    signal_placebo: PlaceboResult,
    return_placebo: PlaceboResult,
    deflated_sharpe: DeflatedSharpeResult,
    pbo: PBOResult,
    *,
    recorded_trial_count: int,
    thresholds: AuditThresholds | None = None,
) -> AlphaCourtReport:
    thresholds = thresholds or AuditThresholds()
    if not all(
        (
            lineage.factor_id,
            lineage.factor_version,
            lineage.snapshot_id,
            lineage.experiment_id,
            lineage.trial_id,
            lineage.code_version,
        )
    ):
        raise FalsificationError("falsification lineage identifiers cannot be empty")
    if recorded_trial_count != deflated_sharpe.recorded_trial_count:
        raise FalsificationError("report trial count does not match DSR trial count")
    if signal_placebo.method != "signal_shuffle":
        raise FalsificationError("signal placebo has the wrong method")
    if return_placebo.method != "return_permutation":
        raise FalsificationError("return placebo has the wrong method")
    if not 0 < thresholds.max_placebo_p_value < 1:
        raise FalsificationError("placebo threshold must be between zero and one")
    if not 0 < thresholds.min_dsr_probability < 1:
        raise FalsificationError("DSR threshold must be between zero and one")
    if not 0 <= thresholds.max_pbo < 1:
        raise FalsificationError("PBO threshold must be between zero and one")

    checks = (
        (
            "signal shuffle rejects the null",
            signal_placebo.empirical_p_value <= thresholds.max_placebo_p_value,
        ),
        (
            "return permutation rejects the null",
            return_placebo.empirical_p_value <= thresholds.max_placebo_p_value,
        ),
        (
            "Sharpe survives multiplicity deflation",
            deflated_sharpe.probability >= thresholds.min_dsr_probability,
        ),
        ("CPCV selection has acceptable PBO", pbo.probability <= thresholds.max_pbo),
    )
    return AlphaCourtReport(
        method_version=METHOD_VERSION,
        lineage=lineage,
        recorded_trial_count=recorded_trial_count,
        seeds=(signal_placebo.seed, return_placebo.seed),
        thresholds=thresholds,
        signal_placebo=signal_placebo,
        return_placebo=return_placebo,
        deflated_sharpe=deflated_sharpe,
        pbo=pbo,
        decision=AuditDecision(passed=all(passed for _, passed in checks), checks=checks),
    )
