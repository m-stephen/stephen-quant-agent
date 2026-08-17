from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from stephen_quant.cli import main
from stephen_quant.v2 import (
    FIREWALL_VERSION,
    AllowlistedFile,
    BoundedResearchManifest,
    EpochBudget,
    EpochPolicy,
    FailureCode,
    FailureStore,
    FamilySignature,
    SealedDataFirewall,
    SearchAction,
    VariantSignature,
    WindowState,
    decision_hash_without_sealed_data,
)
from stephen_quant.workflows import (
    load_v27_m0_config,
    run_v27_m0_governance,
    verify_v27_m0_replay,
)


def _family(mechanism: str = "flow_confirmation") -> FamilySignature:
    return FamilySignature(
        mechanism,
        ("flow", "price"),
        ("prior_close", "published_flow"),
        "persistent flow predicts continuation",
        "positive",
    )


def _variant(family: FamilySignature, horizon: int, wrapper: str) -> VariantSignature:
    return VariantSignature(
        family,
        "flow_confirmation_expression",
        horizon,
        None,
        ("raw", "residual"),
        "top_k",
        wrapper,
    )


def _seed_store(path: Path) -> tuple[FailureStore, tuple[str, ...]]:
    store = FailureStore(path)
    store.start_epoch(
        "v2.7-m0",
        27,
        EpochPolicy("v2.7-test", 1),
        EpochBudget((("flow_confirmation", 0),), 0, 0, 0, 0),
    )
    nodes = tuple(
        store.add_failure(
            epoch_id="v2.7-m0",
            family_id="flow_confirmation",
            candidate_id="rejected",
            stage="independent_validation",
            code=code,
            payload={"granularity": "FROZEN_GATE_ONLY"},
        ).node_id
        for code in (
            FailureCode.TEMPORAL_NON_GENERALIZATION,
            FailureCode.PLACEBO_FAILURE_OOS,
        )
    )
    return store, nodes


def test_family_tombstone_blocks_variants_but_not_distinct_mechanisms(tmp_path: Path) -> None:
    store, node_ids = _seed_store(tmp_path / "failure.sqlite3")
    tombstone = store.record_family_tombstone(
        _family(),
        reason_code="VALIDATION_FAIL_STOP",
        authority="issue-67",
        source_failure_node_ids=node_ids,
        recorded_at="2026-08-17T17:36:46+08:00",
    )
    original = store.tombstone_decision(_variant(_family(), 20, "risk_off_cash"))
    changed = store.tombstone_decision(_variant(_family(), 5, "new_threshold"))
    distinct = store.tombstone_decision(_variant(_family("margin_shock"), 5, "none"))
    assert original.action == changed.action == SearchAction.STOP_FAMILY
    assert original.tombstone_id == changed.tombstone_id == tombstone.tombstone_id
    assert distinct.action == SearchAction.EXPLORE
    assert distinct.tombstone_id is None


def test_validation_failure_stops_family_before_exhaustion() -> None:
    from stephen_quant.v2.failures import FailureNode, _action_for

    node = FailureNode(
        "node",
        "epoch",
        "family",
        "candidate",
        "independent_validation",
        FailureCode.DSR_FAILURE,
        "{}",
        "0" * 64,
    )
    assert _action_for((node,), threshold=99) == (
        SearchAction.STOP_FAMILY,
        "VALIDATION_FAIL_STOP",
    )


def test_window_state_is_append_only_and_rejects_invalid_transition(tmp_path: Path) -> None:
    store = FailureStore(tmp_path / "windows.sqlite3")
    event = store.record_window_state(
        window_id="2025-validation",
        previous_state=WindowState.SEALED_VALIDATION,
        new_state=WindowState.CONSUMED_VALIDATION,
        authority="issue-67",
        source_artifact_sha256="a" * 64,
        recorded_at="2026-08-17T17:36:46+08:00",
    )
    assert store.window_state_events("2025-validation") == (event,)
    with pytest.raises(ValueError, match="not permitted"):
        store.record_window_state(
            window_id="2025-validation",
            previous_state=WindowState.CONSUMED_VALIDATION,
            new_state=WindowState.SEALED_VALIDATION,
            authority="issue-67",
            source_artifact_sha256="a" * 64,
            recorded_at="2026-08-17T17:37:00+08:00",
        )
    with store.connect() as conn, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM window_state_events")


def test_explicit_manifest_never_enumerates_or_reads_forbidden_canary(tmp_path: Path) -> None:
    allowed = tmp_path / "2024.csv"
    forbidden_2025 = tmp_path / "2025.csv"
    forbidden_2026 = tmp_path / "2026.csv"
    allowed.write_bytes(b"research")
    forbidden_2025.write_bytes(b"consumed-a")
    forbidden_2026.write_bytes(b"sealed-a")
    manifest = BoundedResearchManifest(
        FIREWALL_VERSION,
        "2024-12-31",
        (
            AllowlistedFile(
                "research",
                str(allowed),
                "2024-12-31",
                hashlib.sha256(b"research").hexdigest(),
            ),
        ),
    )
    before = decision_hash_without_sealed_data(manifest, {"family": "new"})
    forbidden_2025.write_bytes(b"consumed-b")
    forbidden_2026.write_bytes(b"sealed-b")
    after = decision_hash_without_sealed_data(manifest, {"family": "new"})
    firewall = SealedDataFirewall(manifest)
    assert firewall.read_bytes("research") == b"research"
    with pytest.raises(PermissionError, match="absent"):
        firewall.read_bytes("2025")
    audit = firewall.audit()
    assert before == after
    assert audit.directory_enumerations == 0
    assert audit.consumed_window_accesses == audit.sealed_window_accesses == 0
    assert audit.denied_attempts == ("2025",)
    assert audit.passed


def test_manifest_rejects_consumed_or_sealed_cutoff(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot reach"):
        BoundedResearchManifest(FIREWALL_VERSION, "2025-01-01", ()).validate()
    payload = tmp_path / "payload"
    payload.write_bytes(b"x")
    with pytest.raises(ValueError, match="exceeds"):
        BoundedResearchManifest(
            FIREWALL_VERSION,
            "2024-12-31",
            (AllowlistedFile("late", str(payload), "2025-01-01", "0" * 64),),
        ).validate()


def test_v27_m0_run_adds_no_trial_and_replays_offline(tmp_path: Path) -> None:
    config = load_v27_m0_config("configs/v2.7-m0-governance.json")
    report, artifacts = run_v27_m0_governance(
        "configs/v2.7-m0-governance.json",
        failure_store_path=tmp_path / "failure.sqlite3",
        output_dir=tmp_path / "out",
    )
    assert config.prior_inferential_trials == 48
    assert report.decision == "M0_GOVERNANCE_READY"
    assert report.new_inferential_trials == 0
    assert report.cumulative_inferential_trials == 48
    assert report.rejected_variant_decision == "STOP_FAMILY"
    assert report.changed_variant_decision == "STOP_FAMILY"
    assert report.distinct_mechanism_decision == "EXPLORE"
    assert report.window_states == (
        ("2025-validation", "CONSUMED_VALIDATION"),
        ("2026-final-test", "SEALED_FINAL_TEST"),
    )
    assert report.remote_model_requests == 0
    assert report.consumed_window_accesses == report.sealed_window_accesses == 0
    assert not report.live_trading_authorized
    replay = verify_v27_m0_replay(artifacts.replay_manifest_path)
    assert replay.passed
    assert replay.checked_artifacts == 3


def test_v27_m0_replay_detects_tamper(tmp_path: Path) -> None:
    _, artifacts = run_v27_m0_governance(
        "configs/v2.7-m0-governance.json",
        failure_store_path=tmp_path / "failure.sqlite3",
        output_dir=tmp_path / "out",
    )
    artifacts.markdown_en_path.write_text("tampered", encoding="utf-8")
    replay = verify_v27_m0_replay(artifacts.replay_manifest_path)
    assert not replay.passed
    assert replay.mismatches == (artifacts.markdown_en_path.name,)


def test_v27_cli_run_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    output = tmp_path / "out"
    store = tmp_path / "failure.sqlite3"
    registry = tmp_path / "registry.sqlite3"
    monkeypatch.setattr(
        "sys.argv",
        [
            "stephen-quant",
            "--db",
            str(registry),
            "v2-governance-reset",
            "--failure-store",
            str(store),
            "--output",
            str(output),
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["report"]["new_inferential_trials"] == 0
    monkeypatch.setattr(
        "sys.argv",
        [
            "stephen-quant",
            "--db",
            str(registry),
            "v2-governance-reset",
            "--mode",
            "replay",
            "--replay-manifest",
            str(output / "v2.7-m0-replay-manifest.json"),
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["passed"] is True
