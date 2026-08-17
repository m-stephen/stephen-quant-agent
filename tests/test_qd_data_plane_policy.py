from __future__ import annotations

import json
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


@pytest.fixture(autouse=True)
def _github_api_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_comment(reference: str, token: str | None, pattern: object) -> dict[str, object]:
        return {
            "html_url": reference,
            "author_association": _AUTHOR_ASSOCIATION,
            "user": {"login": "m-stephen"},
            "updated_at": "2026-08-17T19:00:00+08:00",
            "body": "QD_MAINTENANCE_APPROVAL_V1 " + json.dumps(_APPROVED_RECORD),
        }

    monkeypatch.setattr(data_plane_policy, "_github_issue_comment", fake_comment)


def _authorization(year: int = 2026) -> dict[str, object]:
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
        "source_manifest_sha256": "a" * 64,
        "code_commit": "b" * 40,
        "parser_version": "parser-v1",
        "schema_version": "schema-v1",
        "requested_outputs": ["manifest", "provenance", "quality_failures"],
    }


def _context(year: int = 2026) -> MaintenanceExecutionContext:
    return MaintenanceExecutionContext(
        access_subject="isolated-data-maintainer",
        current_time="2026-08-17T19:00:00+08:00",
        source_manifest_sha256="a" * 64,
        source_files=(f"year={year}/announcements.jsonl",),
        code_commit="b" * 40,
    )


def _validate(payload: dict[str, object], year: int = 2026):
    global _APPROVED_RECORD
    baseline = _authorization(year)
    _APPROVED_RECORD = {
        "approved": True,
        "year": year,
        "source_files": baseline["source_files"],
        "purpose": baseline["purpose"],
        "source_manifest_sha256": baseline["source_manifest_sha256"],
        "code_commit": baseline["code_commit"],
        "parser_version": baseline["parser_version"],
        "schema_version": baseline["schema_version"],
        "requested_outputs": baseline["requested_outputs"],
    }
    return validate_data_maintenance_authorization(
        payload, context=_context(year)
    )


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
    global _AUTHOR_ASSOCIATION, _APPROVED_RECORD
    payload = _authorization()
    _ = _validate(payload)
    _APPROVED_RECORD = {**_APPROVED_RECORD, "purpose": "collection"}
    with pytest.raises(QmtDataError, match="verification failed"):
        validate_data_maintenance_authorization(payload, context=_context())
    _AUTHOR_ASSOCIATION = "NONE"
    try:
        with pytest.raises(QmtDataError, match="identity or repository role"):
            validate_data_maintenance_authorization(payload, context=_context())
    finally:
        _AUTHOR_ASSOCIATION = "OWNER"


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
    ],
)
def test_every_github_approved_scope_field_must_match(field_name: str, value: object) -> None:
    global _APPROVED_RECORD
    payload = _authorization()
    _ = _validate(payload)
    _APPROVED_RECORD = {**_APPROVED_RECORD, field_name: value}
    with pytest.raises(QmtDataError, match="verification failed"):
        validate_data_maintenance_authorization(payload, context=_context())


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
