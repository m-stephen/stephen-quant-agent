from stephen_quant.integrity.audit import audit_feature_timing
from stephen_quant.integrity.models import FeatureObservation


def test_feature_timing_passes_when_available_before_label() -> None:
    result = audit_feature_timing(
        FeatureObservation(
            feature_id="ret20",
            instrument="000001.SZ",
            observation_at="2026-01-05T15:00:00+08:00",
            feature_available_at="2026-01-05T15:01:00+08:00",
            label_start_at="2026-01-06T09:30:00+08:00",
            label_end_at="2026-01-26T15:00:00+08:00",
        )
    )
    assert result.passed


def test_feature_timing_fails_on_lookahead() -> None:
    result = audit_feature_timing(
        FeatureObservation(
            feature_id="bad_feature",
            instrument="000001.SZ",
            observation_at="2026-01-05T15:00:00+08:00",
            feature_available_at="2026-01-07T10:00:00+08:00",
            label_start_at="2026-01-06T09:30:00+08:00",
            label_end_at="2026-01-26T15:00:00+08:00",
        )
    )
    assert not result.passed
