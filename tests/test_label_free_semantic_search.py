from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.workflows.label_free_semantic_search import (
    LABEL_FREE_CONFIG_VERSION,
    evaluate_label_free_config,
    load_label_free_config,
    run_label_free_benchmark,
    verify_label_free_replay,
)

CONFIG = Path("configs/v2.8-label-free-semantic-search.json")


def test_frozen_config_has_three_isolated_synthetic_splits() -> None:
    config = load_label_free_config(CONFIG)
    assert config.version == LABEL_FREE_CONFIG_VERSION
    assert {case.split for case in config.cases} == {"train", "validation", "sealed_test"}
    assert len(config.cases) == 9
    assert config.proposal_budget == 9


def test_semantic_controller_outperforms_bounded_baseline_without_labels() -> None:
    report = evaluate_label_free_config(load_label_free_config(CONFIG))
    assert report.decision == "EFFICIENCY_GAIN"
    assert report.worst_seed_semantic_duplicate_recall == 1.0
    assert report.minimum_expensive_evaluations_avoided == 6
    assert all(
        seed.semantic_duplicate_recall > seed.baseline_duplicate_recall
        for seed in report.seed_results
    )
    assert all(
        decision.semantic_correct
        for seed in report.seed_results
        for decision in seed.decisions
    )


def test_report_proves_zero_empirical_and_restricted_access() -> None:
    report = evaluate_label_free_config(load_label_free_config(CONFIG))
    assert report.inferential_trial_delta == 0
    assert report.access_2025 == 0
    assert report.access_2026 == 0
    assert report.real_market_matrix_reads == 0
    assert report.remote_model_requests == 0


def test_same_config_produces_byte_identical_report_payload() -> None:
    config = load_label_free_config(CONFIG)
    left = evaluate_label_free_config(config)
    right = evaluate_label_free_config(config)
    assert left.report_sha256 == right.report_sha256
    assert json.dumps(asdict(left), sort_keys=True) == json.dumps(asdict(right), sort_keys=True)


def test_artifacts_are_bilingual_and_replayable(tmp_path: Path) -> None:
    report, artifacts = run_label_free_benchmark(CONFIG, tmp_path)
    assert artifacts.json_path.exists()
    assert "Synthetic fixtures only" in artifacts.markdown_en_path.read_text(encoding="utf-8")
    assert "仅使用合成 fixture" in artifacts.markdown_zh_path.read_text(encoding="utf-8")
    verification = verify_label_free_replay(CONFIG, artifacts.replay_manifest_path)
    assert verification.passed
    assert verification.result_reproduced
    assert report.report_sha256 == json.loads(
        artifacts.replay_manifest_path.read_text(encoding="utf-8")
    )["report_sha256"]


def test_replay_fails_closed_after_manifest_tampering(tmp_path: Path) -> None:
    _, artifacts = run_label_free_benchmark(CONFIG, tmp_path)
    payload = json.loads(artifacts.replay_manifest_path.read_text(encoding="utf-8"))
    payload["inferential_trial_delta"] = 1
    artifacts.replay_manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    verification = verify_label_free_replay(CONFIG, artifacts.replay_manifest_path)
    assert not verification.passed
    assert not verification.zero_inferential_trials


def test_config_rejects_consumed_or_sealed_window_references(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["notes"] = "inspect validation_2025"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed or consumed"):
        load_label_free_config(path)


def test_config_rejects_budget_smaller_than_case_population(tmp_path: Path) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["proposal_budget"] = 1
    path = tmp_path / "bad-budget.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fit the proposal budget"):
        load_label_free_config(path)


def test_config_hash_changes_when_fixture_changes(tmp_path: Path) -> None:
    original = load_label_free_config(CONFIG)
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["seeds"] = [7, 19, 43]
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    changed = load_label_free_config(path)
    assert original.config_sha256 != changed.config_sha256
    assert evaluate_label_free_config(original).report_sha256 != evaluate_label_free_config(
        changed
    ).report_sha256


def test_cli_run_and_offline_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(tmp_path / "unused.sqlite3"),
            "v2-label-free-search",
            "--config",
            str(CONFIG),
            "--output",
            str(output),
        ],
    )
    main()
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["report"]["decision"] == "EFFICIENCY_GAIN"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(tmp_path / "unused.sqlite3"),
            "v2-label-free-search",
            "--mode",
            "replay",
            "--config",
            str(CONFIG),
            "--replay-manifest",
            run_payload["replay_manifest_path"],
        ],
    )
    main()
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["passed"]


def test_cli_kill_switch_stops_before_config_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stephen-quant",
            "--db",
            str(tmp_path / "unused.sqlite3"),
            "v2-label-free-search",
            "--mode",
            "kill",
            "--config",
            str(tmp_path / "missing.json"),
        ],
    )
    with pytest.raises(SystemExit, match="stopped before config"):
        main()
