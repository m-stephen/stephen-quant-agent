from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.workflows import (
    PITReadinessStatus,
    load_v27_m1_config,
    run_v27_m1_pit_readiness,
    verify_v27_m1_replay,
)

CONFIG = "configs/v2.7-m1-pit-readiness.json"


def test_m1_contract_is_fail_closed_and_authorizes_price_controls_only() -> None:
    config = load_v27_m1_config(CONFIG)
    contracts = {item.source: item for item in config.contracts}
    assert config.prior_inferential_trials == 48
    assert contracts["qd_daily"].status is PITReadinessStatus.READY_FOR_M2_CONTROLS
    assert contracts["stock_industry_membership"].status is PITReadinessStatus.DATA_NOT_RESEARCH_READY
    assert contracts["corporate_actions"].status is PITReadinessStatus.DATA_NOT_RESEARCH_READY
    assert contracts["expectation_revisions"].status is PITReadinessStatus.DATA_NOT_RESEARCH_READY
    assert not any(
        "membership" in use for use in contracts["qd_industry_index"].authorized_uses
    )


def test_m1_run_has_no_trials_returns_or_sealed_access(tmp_path: Path) -> None:
    report, artifacts = run_v27_m1_pit_readiness(CONFIG, tmp_path)
    assert report.decision == "PARTIAL_M2_AUTHORIZATION"
    assert report.new_inferential_trials == 0
    assert report.cumulative_inferential_trials == 48
    assert report.return_observations == 0
    assert report.directory_enumerations == 0
    assert report.consumed_window_accesses == 0
    assert report.sealed_window_accesses == 0
    assert report.remote_model_requests == 0
    assert report.live_trading_authorized is False
    assert set(report.m2_authorized_controls) == {
        "market_beta",
        "realized_volatility",
        "adv_liquidity",
        "price_reversal",
        "price_momentum",
    }
    assert verify_v27_m1_replay(artifacts.replay_manifest_path).passed


def test_industry_index_cannot_be_promoted_to_membership(tmp_path: Path) -> None:
    payload = json.loads(Path(CONFIG).read_text(encoding="utf-8"))
    industry = next(item for item in payload["contracts"] if item["source"] == "qd_industry_index")
    industry["authorized_uses"] = ["stock_membership"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="industry indices"):
        load_v27_m1_config(path)


def test_blocked_source_cannot_authorize_use(tmp_path: Path) -> None:
    payload = json.loads(Path(CONFIG).read_text(encoding="utf-8"))
    actions = next(item for item in payload["contracts"] if item["source"] == "corporate_actions")
    actions["authorized_uses"] = ["adjust_returns"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot authorize"):
        load_v27_m1_config(path)


def test_m1_replay_detects_tampering(tmp_path: Path) -> None:
    _, artifacts = run_v27_m1_pit_readiness(CONFIG, tmp_path)
    artifacts.json_path.write_text("{}\n", encoding="utf-8")
    result = verify_v27_m1_replay(artifacts.replay_manifest_path)
    assert not result.passed
    assert artifacts.json_path.name in result.mismatches


def test_m1_cli_audit_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["stephen-quant", "v2-pit-readiness", "--config", CONFIG, "--output", str(tmp_path)],
    )
    main()
    audit = json.loads(capsys.readouterr().out)
    assert audit["report"]["decision"] == "PARTIAL_M2_AUTHORIZATION"
    monkeypatch.setattr(
        "sys.argv",
        [
            "stephen-quant",
            "v2-pit-readiness",
            "--mode",
            "replay",
            "--replay-manifest",
            audit["replay_manifest_path"],
        ],
    )
    main()
    replay = json.loads(capsys.readouterr().out)
    assert replay["passed"] is True
