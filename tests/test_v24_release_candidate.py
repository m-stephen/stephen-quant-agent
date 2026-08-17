from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from stephen_quant.baseline import BacktestPeriod
from stephen_quant.cli import build_parser
from stephen_quant.evaluation import ols_residuals, pearson_correlation
from stephen_quant.workflows import (
    cumulative_v24_trial_count,
    load_v24_temporal_stability_config,
    sample_return_moments,
    temporal_diagnostics,
    verify_v24_temporal_stability_replay,
)


def _period(year: int, index: int, net_return: float) -> BacktestPeriod:
    month = index + 1
    return BacktestPeriod(
        execution_at=f"{year}-{month:02d}-01T09:30:00+08:00",
        return_end_at=f"{year}-{month:02d}-20T09:30:00+08:00",
        rebalanced=True,
        selected_instruments=("000001.SZ",),
        start_nav=1.0,
        end_nav=1.0 + net_return,
        gross_return=net_return,
        net_return=net_return,
        turnover=1.0,
        traded_notional=1.0,
        total_cost=10.0,
        cash_after_execution=0.0,
        orders=(),
    )


def test_public_ols_residuals_are_orthogonal_and_validate_inputs() -> None:
    controls = [[float(index), float(index % 3)] for index in range(8)]
    target = [float(index**2 + index % 2) for index in range(8)]

    residuals = ols_residuals(target, controls)

    assert abs(pearson_correlation(residuals, [row[0] for row in controls])) < 1e-10
    assert abs(pearson_correlation(residuals, [row[1] for row in controls])) < 1e-10
    with pytest.raises(ValueError, match="same non-zero length"):
        ols_residuals([1.0], [])


def test_sample_return_moments_use_observed_nonzero_distribution() -> None:
    moments = sample_return_moments((-0.02, -0.01, 0.01, 0.02, 0.08))

    assert moments.observations == 5
    assert moments.skewness > 0
    assert math.isfinite(moments.excess_kurtosis)
    with pytest.raises(ValueError, match="at least four"):
        sample_return_moments((0.01, 0.02, 0.03))


def test_v24_manifest_freezes_v23_evidence_and_one_trial() -> None:
    config = load_v24_temporal_stability_config(
        "configs/v2.4-temporal-stability.json"
    )

    assert config.prior_trial_count == 44
    assert config.prior_pbo_scope == "SIGNAL_SELECTION_ONLY"
    assert config.prior_evidence_sha256 == config.calculated_evidence_sha256
    assert cumulative_v24_trial_count(config, 1) == 45
    with pytest.raises(ValueError, match="exactly one"):
        cumulative_v24_trial_count(config, 2)


def test_v24_manifest_rejects_evidence_tamper(tmp_path: Path) -> None:
    payload = json.loads(
        Path("configs/v2.4-temporal-stability.json").read_text(encoding="utf-8")
    )
    payload["prior_dsr_probability"] = 0.95
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence hash"):
        load_v24_temporal_stability_config(path)


def test_temporal_diagnostics_are_deterministic_and_cover_three_years() -> None:
    periods = tuple(
        _period(year, index, 0.01 + ((index % 3) - 1) * 0.005)
        for year in (2022, 2023, 2024)
        for index in range(12)
    )

    first = temporal_diagnostics(periods, rolling_periods=12, periods_per_year=12)
    second = temporal_diagnostics(periods, rolling_periods=12, periods_per_year=12)

    assert first == second
    assert tuple(item.label for item in first.yearly) == ("2022", "2023", "2024")
    assert first.positive_year_fraction == 1.0
    assert len(first.rolling) == 25
    assert 0 < first.top_decile_absolute_return_contribution < 0.5


def test_v24_replay_is_offline_and_fails_on_tamper(tmp_path: Path) -> None:
    artifacts = {
        "json": tmp_path / "v2.4-temporal-stability.json",
        "markdown_en": tmp_path / "v2.4-temporal-stability.en.md",
        "markdown_zh": tmp_path / "v2.4-temporal-stability.zh.md",
    }
    for name, path in artifacts.items():
        path.write_text(name, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in artifacts.items()
    }
    manifest = tmp_path / "v2.4-replay-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "replay_version": "v2.4-temporal-stability-replay-1.0.0",
                "method_version": "v2.4-frozen-temporal-stability-1.0.0",
                "source_snapshot_sha256": "a" * 64,
                "prior_evidence_sha256": "b" * 64,
                "cumulative_trial_count": 45,
                "release_decision": "RESEARCH_PREVIEW_READY",
                "alpha_decision": "RESEARCH_PREVIEW_ONLY",
                "validation_window_opened": False,
                "test_window_opened": False,
                "artifacts": hashes,
            }
        ),
        encoding="utf-8",
    )

    assert verify_v24_temporal_stability_replay(manifest).passed
    artifacts["markdown_en"].write_text("tampered", encoding="utf-8")
    verification = verify_v24_temporal_stability_replay(manifest)
    assert verification.passed is False
    assert verification.mismatches == ("markdown_en",)


def test_v24_cli_replay_and_kill_need_no_local_paths() -> None:
    parser = build_parser()
    replay = parser.parse_args(
        [
            "v2-temporal-stability",
            "--mode",
            "replay",
            "--replay-manifest",
            "frozen.json",
        ]
    )
    kill = parser.parse_args(["v2-temporal-stability", "--mode", "kill"])

    assert replay.paths_config is None
    assert kill.paths_config is None
