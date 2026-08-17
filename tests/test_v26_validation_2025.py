from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.workflows import (
    V26_PBO_STATUS,
    load_v26_validation_config,
    run_v26_validation,
    verify_v26_validation_replay,
)


def test_v26_config_freezes_one_shot_2025_validation() -> None:
    config = load_v26_validation_config("configs/v2.6-validation-2025.json")

    assert config.frozen_policy_id == "risk_off_cash"
    assert config.regime_threshold == 0.0
    assert config.prior_trial_count == 47
    assert len(config.prior_research_period_returns) == 35
    assert config.prior_evidence_sha256 == config.calculated_evidence_sha256
    assert config.validation_end < config.sealed_test_start


def test_v26_config_rejects_policy_or_evidence_tamper(tmp_path: Path) -> None:
    payload = json.loads(Path("configs/v2.6-validation-2025.json").read_text())
    payload["regime_threshold"] = 0.01
    threshold = tmp_path / "threshold.json"
    threshold.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash"):
        load_v26_validation_config(threshold)

    payload["regime_threshold"] = 0.0
    payload["prior_research_net_return"] = 9.0
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash"):
        load_v26_validation_config(evidence)


def test_v26_rejects_registry_with_prior_validation_trial(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "fixture.txt").write_text("fixture", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(data))
    experiment_id = registry.create_experiment(
        ExperimentSpec("prior", "prior", snapshot_id, "test", "{}")
    )
    registry.create_trial(
        TrialSpec(
            experiment_id,
            "prior",
            "prior",
            "{}",
            42,
            "2022-01-01",
            "2024-12-31",
            "2025-01-03",
            "2025-12-31",
            "2026-01-05",
            "2026-12-31",
        )
    )

    with pytest.raises(ValueError, match="already contains"):
        run_v26_validation(
            LocalPathConfig(None, {}),
            "configs/v2.6-validation-2025.json",
            registry=registry,
            output_dir=tmp_path / "output",
            code_version="test",
            ingested_at="2026-08-17T17:00:00+08:00",
        )


def test_v26_replay_is_offline_and_fails_on_tamper(tmp_path: Path) -> None:
    artifacts = {
        "readiness": tmp_path / "readiness" / "v2.6-readiness.json",
        "json": tmp_path / "v2.6-validation.json",
        "markdown_en": tmp_path / "v2.6-validation.en.md",
        "markdown_zh": tmp_path / "v2.6-validation.zh.md",
    }
    artifacts["readiness"].parent.mkdir()
    for name, path in artifacts.items():
        path.write_text(name, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in artifacts.items()
    }
    manifest = tmp_path / "v2.6-replay-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "replay_version": "v2.6-validation-replay-1.0.0",
                "cumulative_trial_count": 48,
                "pbo_status": V26_PBO_STATUS,
                "final_test_window_opened": False,
                "live_trading_authorized": False,
                "artifacts": hashes,
            }
        ),
        encoding="utf-8",
    )

    assert verify_v26_validation_replay(manifest).passed
    artifacts["markdown_zh"].write_text("tampered", encoding="utf-8")
    assert verify_v26_validation_replay(manifest).mismatches == ("markdown_zh",)


def test_v26_cli_modes_preserve_one_shot_boundary() -> None:
    parser = build_parser()
    readiness = parser.parse_args(
        [
            "v2-validate-2025",
            "--mode",
            "readiness",
            "--paths-config",
            "local.json",
            "--ingested-at",
            "2026-08-17T17:00:00+08:00",
        ]
    )
    replay = parser.parse_args(
        ["v2-validate-2025", "--mode", "replay", "--replay-manifest", "frozen.json"]
    )
    kill = parser.parse_args(["v2-validate-2025", "--mode", "kill"])

    assert readiness.mode == "readiness"
    assert replay.paths_config is None
    assert kill.paths_config is None
