from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.cross_validation import (
    SampleInterval,
    SplitLineage,
    audit_manifest,
    generate_cpcv_manifest,
)
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import (
    FalsificationError,
    FalsificationLineage,
    build_alpha_court_report,
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
    run_placebo,
    write_alpha_court_report,
)
from stephen_quant.integrity.audit import AuditFinding


def _observations() -> list[EvaluationObservation]:
    rows: list[EvaluationObservation] = []
    start = date(2025, 1, 2)
    for date_index in range(10):
        as_of = start + timedelta(days=date_index * 7)
        for instrument_index in range(20):
            factor = float(instrument_index)
            noise = ((date_index * 7 + instrument_index * 3) % 5 - 2) * 0.001
            rows.append(
                EvaluationObservation(
                    timestamp=f"{as_of.isoformat()}T15:00:00+08:00",
                    instrument=f"asset_{instrument_index:02d}",
                    factor_value=factor,
                    factor_available_at=f"{as_of.isoformat()}T15:01:00+08:00",
                    label_start_at=(
                        f"{(as_of + timedelta(days=1)).isoformat()}T09:30:00+08:00"
                    ),
                    label_end_at=(
                        f"{(as_of + timedelta(days=5)).isoformat()}T15:00:00+08:00"
                    ),
                    forward_return=factor * 0.01 + noise,
                    horizon="5d",
                    subperiod="all",
                    regime="synthetic",
                )
            )
    return rows


def _cpcv_fixture():
    start = date(2025, 1, 2)
    samples = [
        SampleInterval(
            sample_id=f"sample_{index}",
            instrument="asset",
            feature_at=f"{(start + timedelta(days=index * 3)).isoformat()}T08:00:00+00:00",
            label_start_at=f"{(start + timedelta(days=index * 3)).isoformat()}T09:00:00+00:00",
            label_end_at=f"{(start + timedelta(days=index * 3)).isoformat()}T10:00:00+00:00",
        )
        for index in range(10)
    ]
    manifest = generate_cpcv_manifest(
        samples,
        SplitLineage("snap_test", "exp_test", "trial_test", "test-sha"),
        n_groups=5,
        n_test_groups=2,
    )
    return manifest, audit_manifest(manifest, samples)


def test_both_placebos_destroy_a_known_cross_sectional_signal() -> None:
    signal = run_placebo(
        _observations(),
        horizon="5d",
        direction=1,
        method="signal_shuffle",
        seed=42,
        repetitions=199,
    )
    returns = run_placebo(
        _observations(),
        horizon="5d",
        direction=1,
        method="return_permutation",
        seed=43,
        repetitions=199,
    )

    assert signal.observed_mean_rank_ic > 0.99
    assert returns.observed_mean_rank_ic > 0.99
    assert signal.empirical_p_value <= 0.05
    assert returns.empirical_p_value <= 0.05
    assert abs(sum(signal.placebo_mean_rank_ics) / signal.repetitions) < 0.05
    assert abs(sum(returns.placebo_mean_rank_ics) / returns.repetitions) < 0.05
    assert signal == run_placebo(
        _observations(),
        horizon="5d",
        direction=1,
        method="signal_shuffle",
        seed=42,
        repetitions=199,
    )


def test_dsr_penalizes_the_full_recorded_search() -> None:
    inputs = {
        "observed_sharpe": 0.7,
        "trial_sharpes": (-0.2, 0.0, 0.1, 0.3, 0.7),
        "observations": 252,
        "skewness": -0.4,
        "excess_kurtosis": 2.0,
    }
    few_trials = deflated_sharpe_ratio(**inputs, recorded_trial_count=5)
    many_trials = deflated_sharpe_ratio(**inputs, recorded_trial_count=100)

    assert many_trials.benchmark_sharpe > few_trials.benchmark_sharpe
    assert many_trials.probability < few_trials.probability
    assert many_trials.recorded_trial_count == 100
    assert many_trials.sharpe_estimates_used == 5


def test_pbo_uses_only_complete_audited_cpcv_paths() -> None:
    manifest, findings = _cpcv_fixture()
    path_ids = [path.path_id for path in manifest.paths]
    scores = {
        "stable": {path: 1.0 + index * 0.01 for index, path in enumerate(path_ids)},
        "weak": {path: 0.3 + index * 0.01 for index, path in enumerate(path_ids)},
        "noise": {path: -0.2 + index * 0.01 for index, path in enumerate(path_ids)},
    }

    result = probability_of_backtest_overfitting(manifest, scores, findings)

    assert len(path_ids) == 4
    assert result.probability == 0.0
    assert result.combinations == 6
    assert result.split_manifest_sha256 == manifest.manifest_sha256

    incomplete = {name: dict(values) for name, values in scores.items()}
    incomplete["stable"].pop(path_ids[0])
    with pytest.raises(FalsificationError, match="cover"):
        probability_of_backtest_overfitting(manifest, incomplete, findings)

    with pytest.raises(FalsificationError, match="fully passing"):
        probability_of_backtest_overfitting(
            manifest,
            scores,
            (AuditFinding("unrelated_check", True, "not this manifest"),),
        )


def test_alpha_court_report_is_deterministic_and_complete(tmp_path: Path) -> None:
    rows = _observations()
    signal = run_placebo(
        rows, horizon="5d", direction=1, method="signal_shuffle", seed=42, repetitions=99
    )
    returns = run_placebo(
        rows,
        horizon="5d",
        direction=1,
        method="return_permutation",
        seed=43,
        repetitions=99,
    )
    dsr = deflated_sharpe_ratio(
        observed_sharpe=1.2,
        trial_sharpes=(-0.1, 0.0, 0.1, 0.2, 1.2),
        recorded_trial_count=5,
        observations=504,
    )
    manifest, findings = _cpcv_fixture()
    paths = [path.path_id for path in manifest.paths]
    pbo = probability_of_backtest_overfitting(
        manifest,
        {
            "candidate": {path: 1.0 for path in paths},
            "baseline": {path: 0.0 for path in paths},
        },
        findings,
    )
    report = build_alpha_court_report(
        FalsificationLineage(
            factor_id="ret_60",
            factor_version="1.0.0",
            snapshot_id="snap_fixture",
            experiment_id="exp_fixture",
            trial_id="trial_fixture",
            code_version="test-sha",
        ),
        signal,
        returns,
        dsr,
        pbo,
        recorded_trial_count=5,
    )

    first = write_alpha_court_report(report, tmp_path / "first")
    second = write_alpha_court_report(report, tmp_path / "second")
    payload = json.loads(first.json_path.read_text(encoding="utf-8"))

    assert report.decision.passed
    assert first.json_sha256 == second.json_sha256
    assert first.markdown_sha256 == second.markdown_sha256
    assert payload["lineage"]["snapshot_id"] == "snap_fixture"
    assert payload["recorded_trial_count"] == 5
    assert payload["seeds"] == [42, 43]
    assert payload["pbo"]["method_version"]
