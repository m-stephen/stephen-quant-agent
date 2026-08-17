from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.cli import build_parser
from stephen_quant.workflows import (
    cumulative_v23_trial_count,
    load_v23_style_residualization_config,
    residualize_v23_style,
    verify_v23_style_residualization_replay,
)


def _panels() -> tuple[tuple[BaselineObservation, ...], tuple[BaselineObservation, ...]]:
    targets = []
    controls = []
    for index in range(8):
        common = {
            "instrument": f"00000{index}.SZ",
            "signal_at": "2023-01-02T15:00:00+08:00",
            "signal_available_at": "2023-01-02T15:01:00+08:00",
            "average_daily_value": math.exp(10 + index % 3),
            "liquidity_available_at": "2023-01-02T15:01:00+08:00",
            "execution_at": "2023-01-03T09:30:00+08:00",
            "return_end_at": "2023-02-07T09:30:00+08:00",
            "forward_return": index / 100,
            "can_buy_open": True,
            "can_sell_open": True,
            "tradability_reason": None,
            "eligible": True,
        }
        targets.append(BaselineObservation(signal=float(index**2 + index % 2), **common))
        controls.append(BaselineObservation(signal=float(index), **common))
    return tuple(targets), tuple(controls)


def test_v23_manifest_carries_frozen_v22_evidence_and_trial_count() -> None:
    config = load_v23_style_residualization_config(
        "configs/v2.3-style-residualization.json"
    )

    assert config.prior_trial_count == 42
    assert config.top_k == 5
    assert config.prior_evidence_sha256 == config.calculated_evidence_sha256
    assert cumulative_v23_trial_count(config, 2) == 44
    with pytest.raises(ValueError, match="one candidate"):
        cumulative_v23_trial_count(config, 1)


def test_v23_manifest_rejects_tampered_prior_evidence(tmp_path: Path) -> None:
    payload = json.loads(
        Path("configs/v2.3-style-residualization.json").read_text(encoding="utf-8")
    )
    payload["prior_dsr_probability"] = 0.95
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence hash"):
        load_v23_style_residualization_config(path)


def test_v23_residualization_is_same_date_orthogonal_and_deterministic() -> None:
    targets, controls = _panels()

    first, audit = residualize_v23_style(
        targets, controls, target_direction=1, control_direction=1
    )
    second, repeated = residualize_v23_style(
        targets, controls, target_direction=1, control_direction=1
    )

    assert first == second
    assert audit == repeated
    assert audit.signal_changed
    assert audit.forward_returns_used_in_fit is False
    assert audit.point_in_time_visible
    assert audit.mean_abs_price_control_correlation < 1e-10
    assert audit.mean_abs_log_adv_correlation < 1e-10


def test_v23_residualization_fails_closed_on_future_control() -> None:
    targets, controls = _panels()
    controls = (
        replace(controls[0], signal_available_at="2023-01-03T10:00:00+08:00"),
        *controls[1:],
    )

    with pytest.raises(ValueError, match="point-in-time visible"):
        residualize_v23_style(
            targets, controls, target_direction=1, control_direction=1
        )


def test_v23_replay_is_offline_and_fails_on_tamper(tmp_path: Path) -> None:
    artifacts = {
        "json": tmp_path / "v2.3-style-residualization.json",
        "markdown_en": tmp_path / "v2.3-style-residualization.en.md",
        "markdown_zh": tmp_path / "v2.3-style-residualization.zh.md",
    }
    for name, path in artifacts.items():
        path.write_text(name, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in artifacts.items()
    }
    manifest = tmp_path / "v2.3-replay-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "replay_version": "v2.3-style-residualization-replay-1.0.0",
                "method_version": "v2.3-same-day-style-residualization-1.0.0",
                "source_snapshot_sha256": "a" * 64,
                "prior_evidence_sha256": "b" * 64,
                "cumulative_trial_count": 44,
                "validation_window_opened": False,
                "test_window_opened": False,
                "artifacts": hashes,
            }
        ),
        encoding="utf-8",
    )

    assert verify_v23_style_residualization_replay(manifest).passed
    artifacts["json"].write_text("tampered", encoding="utf-8")
    verification = verify_v23_style_residualization_replay(manifest)
    assert verification.passed is False
    assert verification.mismatches == ("json",)


def test_v23_cli_replay_and_kill_need_no_local_paths() -> None:
    parser = build_parser()
    replay = parser.parse_args(
        [
            "v2-style-residualization",
            "--mode",
            "replay",
            "--replay-manifest",
            "frozen.json",
        ]
    )
    kill = parser.parse_args(["v2-style-residualization", "--mode", "kill"])

    assert replay.paths_config is None
    assert kill.paths_config is None
