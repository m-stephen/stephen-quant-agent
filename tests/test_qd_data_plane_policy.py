from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.qmt import data_plane_policy
from stephen_quant.qmt.data_plane_policy import (
    CONSUMED_MAINTENANCE,
    SEALED_MAINTENANCE,
    MaintenanceExecutionContext,
    data_operations_ledger_record,
    research_visible_control_metadata,
    validate_data_maintenance_authorization,
    validate_manifest_state_transition,
    validate_plane_storage_layout,
    validate_research_environment,
    validate_research_manifest_control,
)
from stephen_quant.qmt.models import QmtDataError

APPROVAL = "https://github.com/m-stephen/stephen-quant-agent/issues/85#issuecomment-100"
_APPROVED_RECORD: dict[str, object] = {}
_AUTHOR_ASSOCIATION = "OWNER"
_AUTHOR_LOGIN = "m-stephen"
_LEDGER_DIR = Path("unused")


def _manifest_bytes(year: int) -> bytes:
    state = CONSUMED_MAINTENANCE if year == 2025 else SEALED_MAINTENANCE
    return json.dumps({
        "version": 1,
        "plane": "data_maintenance",
        "state": state,
        "year": year,
        "source_type": "local+alphapai",
        "files": [{
            "path": f"year={year}/announcements.jsonl",
            "partition": f"{year}-08",
        }],
    }, sort_keys=True).encode("utf-8")


@pytest.fixture(autouse=True)
def _github_api_comment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    global _LEDGER_DIR
    _LEDGER_DIR = tmp_path / "operations-ledger"
    def fake_comment(reference: str, token: str | None, pattern: object) -> dict[str, object]:
        return {
            "html_url": reference,
            "author_association": _AUTHOR_ASSOCIATION,
            "user": {"login": _AUTHOR_LOGIN},
            "id": 100,
            "updated_at": "2026-08-17T19:00:00+08:00",
            "body": "QD_MAINTENANCE_APPROVAL_V1 " + json.dumps(_APPROVED_RECORD),
        }

    monkeypatch.setattr(data_plane_policy, "_github_issue_comment", fake_comment)


def _authorization(year: int = 2026) -> dict[str, object]:
    manifest_sha = hashlib.sha256(_manifest_bytes(year)).hexdigest()
    return {
        "plane": "data_maintenance",
        "state": CONSUMED_MAINTENANCE if year == 2025 else SEALED_MAINTENANCE,
        "year": year,
        "access_subject": "isolated-data-maintainer",
        "approved_by": "m-stephen",
        "approver_role": "repository_maintainer",
        "approval_reference": APPROVAL,
        "authorized_at": "2026-08-17T18:00:00+08:00",
        "expires_at": "2026-08-17T20:00:00+08:00",
        "purpose": "pit_alignment",
        "source_files": [f"year={year}/announcements.jsonl"],
        "source_manifest_sha256": manifest_sha,
        "code_commit": "b" * 40,
        "parser_version": "parser-v1",
        "schema_version": "schema-v1",
        "requested_outputs": ["manifest", "provenance", "quality_failures"],
        "operation_id": "operation-20260817-0001",
        "source_type": "local+alphapai",
    }


def _context(year: int = 2026) -> MaintenanceExecutionContext:
    manifest = _manifest_bytes(year)
    return MaintenanceExecutionContext(
        access_subject="isolated-data-maintainer",
        current_time="2026-08-17T19:00:00+08:00",
        source_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        source_files=(f"year={year}/announcements.jsonl",),
        code_commit="b" * 40,
        source_manifest_bytes=manifest,
    )


def _validate(payload: dict[str, object], year: int = 2026):
    _set_approved(_authorization(year))
    return validate_data_maintenance_authorization(
        payload, context=_context(year), operations_ledger_dir=_LEDGER_DIR
    )


def _set_approved(baseline: dict[str, object]) -> None:
    global _APPROVED_RECORD
    _APPROVED_RECORD = {
        "approved": True,
        "year": baseline["year"],
        "source_files": baseline["source_files"],
        "purpose": baseline["purpose"],
        "source_manifest_sha256": baseline["source_manifest_sha256"],
        "code_commit": baseline["code_commit"],
        "parser_version": baseline["parser_version"],
        "schema_version": baseline["schema_version"],
        "requested_outputs": baseline["requested_outputs"],
        "operation_id": baseline["operation_id"],
        "source_type": baseline["source_type"],
    }


def test_research_plane_rejects_restricted_states() -> None:
    for state in (CONSUMED_MAINTENANCE, SEALED_MAINTENANCE):
        with pytest.raises(QmtDataError, match="research plane"):
            validate_research_manifest_control({"plane": "research", "state": state})


def test_maintenance_requires_live_verified_exact_issue_85_approval() -> None:
    assert _validate(_authorization()).state == SEALED_MAINTENANCE
    payload = _authorization()
    payload["approval_reference"] = (
        "https://github.com/m-stephen/stephen-quant-agent/issues/75#issuecomment-100"
    )
    with pytest.raises(QmtDataError, match="exact repository Issue comment"):
        _validate(payload)


@pytest.mark.parametrize("output", ["IC", "sharpe_ratio", "information_coefficient"])
def test_maintenance_rejects_research_output_names_and_synonyms(output: str) -> None:
    payload = _authorization(2025)
    payload["requested_outputs"] = ["provenance", output]
    with pytest.raises(QmtDataError, match="non-allowlisted outputs"):
        _validate(payload, 2025)


def test_maintenance_rejects_scope_hash_commit_identity_and_time_mismatch() -> None:
    mutations = (
        ("source_files", ["all"]),
        ("source_manifest_sha256", "c" * 64),
        ("code_commit", "d" * 40),
        ("access_subject", "another-agent"),
        ("authorized_at", "2026-08-18T18:00:00+08:00"),
        ("expires_at", "2026-08-17T18:30:00+08:00"),
    )
    for key, value in mutations:
        payload = _authorization()
        payload[key] = value
        with pytest.raises(QmtDataError):
            _validate(payload)


def test_github_comment_scope_and_repository_role_are_bound() -> None:
    global _AUTHOR_ASSOCIATION, _AUTHOR_LOGIN, _APPROVED_RECORD
    payload = _authorization()
    _ = _validate(payload)
    _APPROVED_RECORD = {**_APPROVED_RECORD, "purpose": "collection"}
    with pytest.raises(QmtDataError, match="verification failed"):
        validate_data_maintenance_authorization(
            payload, context=_context(), operations_ledger_dir=_LEDGER_DIR
        )
    _AUTHOR_ASSOCIATION = "NONE"
    try:
        with pytest.raises(QmtDataError, match="identity or repository role"):
            validate_data_maintenance_authorization(
                payload, context=_context(), operations_ledger_dir=_LEDGER_DIR
            )
    finally:
        _AUTHOR_ASSOCIATION = "OWNER"
    _AUTHOR_LOGIN = "attacker"
    try:
        with pytest.raises(QmtDataError, match="identity or repository role"):
            validate_data_maintenance_authorization(
                payload, context=_context(), operations_ledger_dir=_LEDGER_DIR
            )
    finally:
        _AUTHOR_LOGIN = "m-stephen"


def test_manifest_partition_year_is_semantically_bound_to_authorization() -> None:
    payload = _authorization(2025)
    malicious_manifest = json.dumps({
        "version": 1,
        "plane": "data_maintenance",
        "state": CONSUMED_MAINTENANCE,
        "year": 2025,
        "source_type": "local+alphapai",
        "files": [{
            "path": "year=2025/announcements.jsonl",
            "partition": "2026-01",
        }],
    }, sort_keys=True).encode("utf-8")
    malicious_hash = hashlib.sha256(malicious_manifest).hexdigest()
    payload["source_manifest_sha256"] = malicious_hash
    _set_approved(payload)
    context = replace(
        _context(2025),
        source_manifest_sha256=malicious_hash,
        source_manifest_bytes=malicious_manifest,
    )
    with pytest.raises(QmtDataError, match="partition does not match"):
        validate_data_maintenance_authorization(
            payload, context=context, operations_ledger_dir=_LEDGER_DIR
        )


def test_operation_id_is_consumed_atomically_and_cannot_be_replayed() -> None:
    payload = _authorization(2026)
    _ = _validate(payload)
    _set_approved(payload)
    with pytest.raises(QmtDataError, match="already been consumed"):
        validate_data_maintenance_authorization(
            payload, context=_context(), operations_ledger_dir=_LEDGER_DIR
        )
    records = list(_LEDGER_DIR.glob("authorization-consumption-*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["approval_comment_id"] == 100
    assert record["approval_comment_updated_at"]
    assert len(record["approval_payload_sha256"]) == 64


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("year", 2025),
        ("source_files", ["year=2026/other.jsonl"]),
        ("purpose", "collection"),
        ("source_manifest_sha256", "f" * 64),
        ("code_commit", "e" * 40),
        ("parser_version", "parser-v2"),
        ("schema_version", "schema-v2"),
        ("requested_outputs", ["manifest"]),
        ("operation_id", "operation-20260817-other"),
        ("source_type", "alphapai"),
    ],
)
def test_every_github_approved_scope_field_must_match(field_name: str, value: object) -> None:
    global _APPROVED_RECORD
    payload = _authorization()
    _ = _validate(payload)
    _APPROVED_RECORD = {**_APPROVED_RECORD, field_name: value}
    with pytest.raises(QmtDataError, match="verification failed"):
        validate_data_maintenance_authorization(
            payload, context=_context(), operations_ledger_dir=_LEDGER_DIR
        )


def test_storage_roots_and_research_environment_are_physically_isolated(tmp_path: Path) -> None:
    with pytest.raises(QmtDataError, match="physically disjoint"):
        validate_plane_storage_layout(
            tmp_path / "research", tmp_path / "maintenance", tmp_path / "research" / "output"
        )
    validate_plane_storage_layout(
        tmp_path / "research", tmp_path / "maintenance", tmp_path / "output"
    )
    with pytest.raises(QmtDataError, match="maintenance credentials"):
        validate_research_environment({"ALPHAPAI_MAINTENANCE_TOKEN": "secret"})
    validate_research_environment({"PATH": "safe"})


def test_ledger_and_research_control_metadata_are_non_inferential() -> None:
    authorization = _validate(_authorization(2025), 2025)
    record = data_operations_ledger_record(
        authorization, output_manifest_sha256="c" * 64,
        accessed_at="2026-08-17T19:05:00+08:00", result="success",
    )
    assert record["inferential_trial_delta"] == 0
    assert record["research_outputs_generated"] == 0
    view = research_visible_control_metadata(
        state=SEALED_MAINTENANCE, authorization_present=True,
        control_manifest_sha256="c" * 64,
    )
    assert view["content_visible"] is False
    assert view["statistics_visible"] is False
    with pytest.raises(QmtDataError, match="cross-state"):
        validate_manifest_state_transition(SEALED_MAINTENANCE, "RESEARCH_ALLOWED_2022_2024")
