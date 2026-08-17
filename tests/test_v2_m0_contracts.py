from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.discovery import flow_stress_generation_plan
from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.snapshot import build_snapshot_manifest
from stephen_quant.v2 import (
    REPLAY_MANIFEST_VERSION,
    FrozenInteraction,
    ReferenceLibraryRecord,
    ReplayManifest,
    audit_replay_manifest,
    migrate_v1_factor_schema,
)


def _registry(tmp_path: Path) -> tuple[ExperimentRegistry, str, str, str, str]:
    source = tmp_path / "source"
    source.mkdir(parents=True)
    (source / "fixture.csv").write_text("frozen\n", encoding="utf-8")
    manifest = build_snapshot_manifest(source)
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(manifest)
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="V2 M0 fixture",
            hypothesis="compatible contracts preserve V1 provenance",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    trial_id, _ = registry.create_trial(
        TrialSpec(
            experiment_id=experiment_id,
            model_name="v2_m0_fixture",
            factor_set="flow_price_divergence",
            hyperparams="{}",
            seed=42,
            train_start="2022-01-04",
            train_end="2024-12-31",
            validation_start="2025-01-03",
            validation_end="2025-12-31",
            test_start="2026-01-05",
            test_end="2026-08-14",
        )
    )
    return registry, snapshot_id, manifest.snapshot_sha256, experiment_id, trial_id


def _schema():
    return next(
        template.render(window=60, horizon="20d")
        for template in flow_stress_generation_plan().templates
        if template.template_id == "flow_price_divergence_parent"
    )


def _payload(value: dict[str, object]) -> tuple[str, str]:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
    return encoded, hashlib.sha256(encoded.encode()).hexdigest()


def test_v1_factor_migrates_losslessly_with_deterministic_hierarchical_ids() -> None:
    schema = _schema()
    first = migrate_v1_factor_schema(
        schema,
        dataset_snapshot_id="snap_fixture",
        controls=("price_reversal", "log_adv"),
        evidence_refs=("V1.8.20", "V1.8.21"),
    )
    second = migrate_v1_factor_schema(
        schema,
        dataset_snapshot_id="snap_fixture",
        controls=("price_reversal", "log_adv"),
        evidence_refs=("V1.8.20", "V1.8.21"),
    )

    assert first.to_v1().to_json() == schema.to_json()
    assert first.legacy_fingerprint == schema.fingerprint
    assert first.ids == second.ids
    assert len(set(first.ids.__dict__.values())) == 4
    deployment = replace(first, test_stage="deployment_simulation")
    assert deployment.ids.hypothesis_id == first.ids.hypothesis_id
    assert deployment.ids.expression_structure_id == first.ids.expression_structure_id
    assert deployment.ids.parameter_variant_id == first.ids.parameter_variant_id
    assert deployment.ids.test_stage_id != first.ids.test_stage_id


def test_search_and_inferential_ledgers_are_distinct_and_append_only(tmp_path: Path) -> None:
    registry, _, _, experiment_id, trial_id = _registry(tmp_path)
    proposal_json, proposal_sha = _payload({"hypothesis": "text-only proposal"})
    proposal_id, proposal_number = registry.record_search_ledger_entry(
        experiment_id=experiment_id,
        entry_type="proposal",
        subject_id="hyp_fixture",
        payload_json=proposal_json,
        payload_sha256=proposal_sha,
        empirical_exposure=False,
    )
    empirical_json, empirical_sha = _payload({"decision": "ranked using RankIC"})
    empirical_id, empirical_number = registry.record_search_ledger_entry(
        experiment_id=experiment_id,
        entry_type="empirical_ranking",
        subject_id="variant_fixture",
        parent_entry_id=proposal_id,
        payload_json=empirical_json,
        payload_sha256=empirical_sha,
        empirical_exposure=True,
        inferential_trial_id=trial_id,
    )

    assert (proposal_number, empirical_number) == (1, 2)
    assert registry.search_ledger_count(experiment_id) == 2
    entries = registry.search_ledger_entries(experiment_id)
    assert entries[0]["inferential_trial_id"] is None
    assert entries[1]["inferential_trial_id"] == trial_id
    assert registry.trial_count(experiment_id) == 1

    with pytest.raises(ValueError, match="must link exactly one"):
        registry.record_search_ledger_entry(
            experiment_id=experiment_id,
            entry_type="invalid_empirical",
            subject_id="variant_fixture",
            payload_json=empirical_json,
            payload_sha256=empirical_sha,
            empirical_exposure=True,
        )
    with pytest.raises(ValueError, match="payload and SHA-256"):
        registry.record_search_ledger_entry(
            experiment_id=experiment_id,
            entry_type="tampered",
            subject_id="hyp_fixture",
            payload_json=proposal_json,
            payload_sha256="0" * 64,
            empirical_exposure=False,
        )
    with registry.connect() as conn, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        conn.execute(
            "UPDATE search_ledger_entries SET subject_id = 'changed' WHERE entry_id = ?",
            (proposal_id,),
        )
    with registry.connect() as conn, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        conn.execute("DELETE FROM trials WHERE trial_id = ?", (trial_id,))
    assert empirical_id


def test_replay_manifest_links_frozen_v1_and_v2_provenance(tmp_path: Path) -> None:
    registry, snapshot_id, snapshot_sha, experiment_id, trial_id = _registry(tmp_path)
    contract = migrate_v1_factor_schema(
        _schema(),
        dataset_snapshot_id=snapshot_id,
        controls=("price_reversal", "log_adv"),
        evidence_refs=("V1.8.20", "V1.8.21"),
    )
    search_json, search_sha = _payload({"contract": contract.ids.parameter_variant_id})
    search_id, _ = registry.record_search_ledger_entry(
        experiment_id=experiment_id,
        entry_type="empirical_migration_fixture",
        subject_id=contract.ids.parameter_variant_id,
        payload_json=search_json,
        payload_sha256=search_sha,
        empirical_exposure=True,
        inferential_trial_id=trial_id,
    )
    interaction = FrozenInteraction(
        provider="fixture-provider",
        model="fixture-model",
        model_version="1",
        prompt_version="v2-m0",
        tool_versions=("safe-dsl-1",),
        raw_input="untrusted research text",
        raw_output='{"hypothesis":"fixture"}',
        tool_calls_json="[]",
        fetched_at="2026-08-17T13:00:00+08:00",
    )
    reference = ReferenceLibraryRecord(
        library_id="reference_v1821",
        version="1.0.0",
        portfolio_mapping="exclude_bottom_decile",
        source_experiment_id="exp_9f69d4068df04559",
        source_snapshot_id="snap_eb6b8b61030a338f",
        config_sha256="a8b671726c1fee3df614fb4099c855c186357151216767c4150efb0406975355",
        research_only=True,
        validated_alpha=False,
    )
    manifest = ReplayManifest(
        manifest_version=REPLAY_MANIFEST_VERSION,
        code_commit="fixture-commit",
        dataset_snapshot_id=snapshot_id,
        dataset_snapshot_sha256=snapshot_sha,
        experiment_id=experiment_id,
        factor_contract=contract,
        reference_library=reference,
        config_json='{"seed":42}',
        seed=42,
        search_ledger_entry_ids=(search_id,),
        inferential_trial_ids=(trial_id,),
        frozen_interactions=(interaction,),
        sealed_windows=("validation:2025", "final-test:2026"),
    )

    first_hash = manifest.manifest_sha256
    assert first_hash == manifest.manifest_sha256
    assert len(first_hash) == 64
    audit = audit_replay_manifest(registry, manifest)
    assert audit.passed is True
    assert audit.sealed_window_accesses == 0
    changed = replace(
        manifest,
        frozen_interactions=(replace(interaction, raw_output='{"hypothesis":"changed"}'),),
    )
    assert changed.manifest_sha256 != first_hash


def test_research_reference_cannot_claim_validated_alpha() -> None:
    with pytest.raises(ValueError, match="cannot be labelled validated alpha"):
        ReferenceLibraryRecord(
            library_id="invalid",
            version="1.0.0",
            portfolio_mapping="exclude_bottom_decile",
            source_experiment_id="exp_fixture",
            source_snapshot_id="snap_fixture",
            config_sha256="a" * 64,
            research_only=True,
            validated_alpha=True,
        ).validate()
