from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.v2 import (
    ShadowBudgetError,
    ShadowLoopConfig,
    ShadowLoopStopped,
    run_shadow_validation,
    verify_shadow_replay,
)


def test_one_command_shadow_loop_meets_v2_acceptance(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    report, artifacts = run_shadow_validation(
        registry, tmp_path / "reports", code_version="fixture-commit"
    )
    assert report.status == "COMPLETED"
    assert report.shadow_mode
    assert report.candidates_proposed == 4
    assert report.empirical_trials_used == 4
    assert report.compute_units_used == 4
    assert report.sealed_window_accesses == 0
    assert report.model_requests_during_replay == 0
    assert report.replay_audit_passed
    assert {item.decision for item in report.decisions} == {
        "REJECT",
        "REVISE",
        "STOP_FAMILY",
        "PROMOTE_FOR_FUTURE_VALIDATION",
    }
    assert any(item.parent_candidate_id for item in report.decisions)
    assert registry.search_ledger_count(report.experiment_id) == report.search_ledger_entries
    entries = registry.search_ledger_entries(report.experiment_id)
    linked_trials = {item["inferential_trial_id"] for item in entries if item["empirical_exposure"]}
    assert len(linked_trials) == 4
    assert artifacts.json_path.exists()
    assert "运行报告" in artifacts.zh_markdown_path.read_text(encoding="utf-8")
    assert "Run Report" in artifacts.en_markdown_path.read_text(encoding="utf-8")
    assert artifacts.replay_manifest_path is not None

    replay = verify_shadow_replay(artifacts.replay_manifest_path)
    assert replay.verified
    assert replay.model_requests == 0
    assert replay.sealed_window_accesses == 0
    assert replay.semantic_decision_sha256 == report.semantic_decision_sha256


def test_semantic_decisions_replay_across_fresh_registries(tmp_path: Path) -> None:
    first, _ = run_shadow_validation(
        ExperimentRegistry(tmp_path / "first.sqlite3"),
        tmp_path / "first",
        code_version="same-code",
    )
    second, _ = run_shadow_validation(
        ExperimentRegistry(tmp_path / "second.sqlite3"),
        tmp_path / "second",
        code_version="same-code",
    )
    assert first.semantic_decision_sha256 == second.semantic_decision_sha256
    assert [item.decision for item in first.decisions] == [
        item.decision for item in second.decisions
    ]


def test_dry_run_has_zero_empirical_exposure(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "dry.sqlite3")
    report, artifacts = run_shadow_validation(
        registry,
        tmp_path / "dry",
        code_version="fixture",
        config=replace(ShadowLoopConfig(), dry_run=True),
    )
    assert report.status == "DRY_RUN"
    assert report.empirical_trials_used == 0
    assert report.compute_units_used == 0
    assert report.sealed_window_accesses == 0
    assert registry.global_trial_count() == 0
    assert artifacts.replay_manifest_path is None


def test_kill_switch_stops_before_registry_mutation(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "killed.sqlite3")
    with pytest.raises(ShadowLoopStopped, match="kill switch"):
        run_shadow_validation(
            registry,
            tmp_path / "killed",
            code_version="fixture",
            config=replace(ShadowLoopConfig(), kill_switch=True),
        )
    assert registry.global_trial_count() == 0


def test_budget_exhaustion_fails_closed_and_preserves_trials(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "budget.sqlite3")
    with pytest.raises(ShadowBudgetError, match="compute budget exhausted"):
        run_shadow_validation(
            registry,
            tmp_path / "budget",
            code_version="fixture",
            config=replace(ShadowLoopConfig(), compute_budget=3),
        )
    assert registry.global_trial_count() == 3


def test_cli_exposes_one_command_and_offline_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "v2.0-shadow-1.0.0",
                "seed": 42,
                "shadow_mode": True,
                "budgets": {
                    "candidate": 6,
                    "compute": 4,
                    "token": 1000,
                    "statistical_trial": 4,
                },
                "sealed_windows": ["2025-validation", "2026-final-test"],
            }
        ),
        encoding="utf-8",
    )
    db_path = tmp_path / "cli.sqlite3"
    output = tmp_path / "cli-report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(db_path),
            "v2-shadow-validate",
            "--config",
            str(config_path),
            "--output",
            str(output),
        ],
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["status"] == "COMPLETED"
    manifest_path = payload["replay_manifest_path"]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(db_path),
            "v2-shadow-validate",
            "--replay-manifest",
            manifest_path,
        ],
    )
    main()
    replay = json.loads(capsys.readouterr().out)
    assert replay["verified"]
    assert replay["model_requests"] == 0
