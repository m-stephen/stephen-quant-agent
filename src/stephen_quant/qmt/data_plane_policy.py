from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .models import QmtDataError

DATA_PLANE_POLICY_VERSION = "qd-data-plane-policy-1.1.0-local-prototype"
RESEARCH_ALLOWED = "RESEARCH_ALLOWED_2022_2024"
CONSUMED_MAINTENANCE = "CONSUMED_2025_DATA_MAINTENANCE_ONLY"
SEALED_MAINTENANCE = "SEALED_2026_DATA_MAINTENANCE_ONLY"
ALLOWED_STATES = frozenset({RESEARCH_ALLOWED, CONSUMED_MAINTENANCE, SEALED_MAINTENANCE})

_MAINTENANCE_PURPOSES = frozenset({
    "collection", "pit_alignment", "revision_chain", "provenance_check",
    "schema_check", "quality_check", "snapshot_freeze",
})
_ALLOWED_OUTPUTS = frozenset({
    "manifest", "provenance", "schema_failures", "quality_failures",
    "revision_chain_diagnostics", "operation_status",
})
_APPROVAL_PATTERN = re.compile(
    r"https://github\.com/m-stephen/stephen-quant-agent/issues/\d+#issuecomment-\d+"
)
_MAINTENANCE_ENV_MARKERS = (
    "ALPHAPAI", "MAINTENANCE", "SEALED", "RESTRICTED", "DATA_ENCLAVE",
)


@dataclass(frozen=True)
class VerifiedGitHubApproval:
    reference: str
    approver_login: str
    approver_role: str
    approved: bool
    verified_at: str
    verifier: str


@dataclass(frozen=True)
class MaintenanceExecutionContext:
    access_subject: str
    current_time: str
    source_manifest_sha256: str
    source_files: tuple[str, ...]
    code_commit: str


@dataclass(frozen=True)
class DataMaintenanceAuthorization:
    state: str
    year: int
    access_subject: str
    approved_by: str
    approver_role: str
    approval_reference: str
    authorized_at: str
    expires_at: str
    purpose: str
    source_files: tuple[str, ...]
    source_manifest_sha256: str
    code_commit: str
    parser_version: str
    schema_version: str
    requested_outputs: tuple[str, ...]
    approval_verified_at: str
    approval_verifier: str


ApprovalVerifier = Callable[[str], VerifiedGitHubApproval]


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QmtDataError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise QmtDataError(f"{field} must include timezone")
    return parsed


def _sha256(value: str, field: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise QmtDataError(f"invalid {field}")
    return normalized


def _commit(value: str) -> str:
    normalized = value.lower()
    if len(normalized) != 40 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise QmtDataError("code_commit must be a full Git commit SHA")
    return normalized


def _safe_files(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise QmtDataError("authorization requires exact source_files")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise QmtDataError("source_files must contain non-empty relative paths")
        path = Path(item)
        if path.is_absolute() or ".." in path.parts or item.strip().lower() == "all":
            raise QmtDataError("source_files must be exact safe relative paths")
        result.append(path.as_posix())
    if len(set(result)) != len(result):
        raise QmtDataError("source_files contains duplicates")
    return tuple(sorted(result))


def validate_research_manifest_control(payload: dict[str, object]) -> None:
    if payload.get("plane") != "research" or payload.get("state") != RESEARCH_ALLOWED:
        raise QmtDataError("research plane accepts only RESEARCH_ALLOWED_2022_2024")


def validate_plane_storage_layout(
    research_root: str | Path,
    maintenance_root: str | Path,
    output_root: str | Path,
) -> None:
    roots = [Path(value).expanduser().resolve() for value in (research_root, maintenance_root, output_root)]
    for index, left in enumerate(roots):
        for right in roots[index + 1 :]:
            try:
                left.relative_to(right)
                overlap = True
            except ValueError:
                try:
                    right.relative_to(left)
                    overlap = True
                except ValueError:
                    overlap = False
            if overlap:
                raise QmtDataError("research, maintenance and output roots must be physically disjoint")


def validate_research_environment(environment: Mapping[str, str]) -> None:
    exposed = sorted(
        key for key, value in environment.items()
        if value and any(marker in key.upper() for marker in _MAINTENANCE_ENV_MARKERS)
    )
    if exposed:
        raise QmtDataError(f"research environment exposes maintenance credentials/config: {exposed}")


def validate_data_maintenance_authorization(
    payload: dict[str, object],
    *,
    context: MaintenanceExecutionContext,
    approval_verifier: ApprovalVerifier | None,
) -> DataMaintenanceAuthorization:
    if approval_verifier is None:
        raise QmtDataError("maintenance authorization requires a live GitHub approval verifier")
    if payload.get("plane") != "data_maintenance":
        raise QmtDataError("maintenance authorization requires data_maintenance plane")
    state = str(payload.get("state", ""))
    year = payload.get("year")
    expected = {2025: CONSUMED_MAINTENANCE, 2026: SEALED_MAINTENANCE}
    if not isinstance(year, int) or year not in expected or state != expected[year]:
        raise QmtDataError("maintenance state/year mismatch")
    purpose = str(payload.get("purpose", ""))
    if purpose not in _MAINTENANCE_PURPOSES:
        raise QmtDataError("maintenance purpose is not allowed")
    requested_outputs_raw = payload.get("requested_outputs")
    if not isinstance(requested_outputs_raw, list) or not requested_outputs_raw:
        raise QmtDataError("requested_outputs requires a non-empty allowlist")
    requested_outputs = tuple(sorted({str(value).strip().lower() for value in requested_outputs_raw}))
    unknown_outputs = set(requested_outputs) - _ALLOWED_OUTPUTS
    if unknown_outputs:
        raise QmtDataError(f"maintenance request contains non-allowlisted outputs: {sorted(unknown_outputs)}")
    required = (
        "access_subject", "approved_by", "approver_role", "approval_reference",
        "authorized_at", "expires_at", "source_manifest_sha256", "code_commit",
        "parser_version", "schema_version",
    )
    values = {field: str(payload.get(field, "")).strip() for field in required}
    if any(not value for value in values.values()):
        raise QmtDataError("maintenance authorization is incomplete")
    if not _APPROVAL_PATTERN.fullmatch(values["approval_reference"]):
        raise QmtDataError("approval_reference must be an exact repository Issue comment URL")
    if values["access_subject"] != context.access_subject:
        raise QmtDataError("current execution subject does not match authorization")
    authorized_at = _timestamp(values["authorized_at"], "authorized_at")
    expires_at = _timestamp(values["expires_at"], "expires_at")
    current_time = _timestamp(context.current_time, "current_time")
    if authorized_at > current_time or current_time > expires_at or expires_at <= authorized_at:
        raise QmtDataError("maintenance authorization is not currently valid")
    source_files = _safe_files(payload.get("source_files"))
    actual_files = tuple(sorted(Path(value).as_posix() for value in context.source_files))
    if source_files != actual_files:
        raise QmtDataError("actual source files do not match authorized source scope")
    manifest_sha = _sha256(values["source_manifest_sha256"], "source_manifest_sha256")
    if manifest_sha != _sha256(context.source_manifest_sha256, "context source_manifest_sha256"):
        raise QmtDataError("source manifest hash does not match authorization")
    code_commit = _commit(values["code_commit"])
    if code_commit != _commit(context.code_commit):
        raise QmtDataError("code commit does not match authorization")
    verified = approval_verifier(values["approval_reference"])
    if (
        not verified.approved
        or verified.reference != values["approval_reference"]
        or verified.approver_login != values["approved_by"]
        or verified.approver_role not in {"user", "repository_maintainer"}
        or verified.approver_role != values["approver_role"]
        or verified.verifier != "github-api"
    ):
        raise QmtDataError("GitHub approval verification failed")
    if values["approved_by"] == values["access_subject"]:
        raise QmtDataError("maintenance access cannot be self-approved")
    return DataMaintenanceAuthorization(
        state=state,
        year=year,
        access_subject=values["access_subject"],
        approved_by=values["approved_by"],
        approver_role=values["approver_role"],
        approval_reference=values["approval_reference"],
        authorized_at=authorized_at.isoformat(),
        expires_at=expires_at.isoformat(),
        purpose=purpose,
        source_files=source_files,
        source_manifest_sha256=manifest_sha,
        code_commit=code_commit,
        parser_version=values["parser_version"],
        schema_version=values["schema_version"],
        requested_outputs=requested_outputs,
        approval_verified_at=_timestamp(verified.verified_at, "approval_verified_at").isoformat(),
        approval_verifier=verified.verifier,
    )


def data_operations_ledger_record(
    authorization: DataMaintenanceAuthorization,
    *, output_manifest_sha256: str, accessed_at: str, result: str,
) -> dict[str, object]:
    if result not in {"success", "denied", "failed"}:
        raise QmtDataError("invalid data operation result")
    payload: dict[str, object] = {
        "ledger": "data_operations_ledger",
        "policy_version": DATA_PLANE_POLICY_VERSION,
        **asdict(authorization),
        "accessed_at": _timestamp(accessed_at, "accessed_at").isoformat(),
        "output_manifest_sha256": _sha256(output_manifest_sha256, "output_manifest_sha256"),
        "result": result,
        "inferential_trial_delta": 0,
        "research_outputs_generated": 0,
        "research_plane_exposure": 0,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"event_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), **payload}


def research_visible_control_metadata(
    *, state: str, authorization_present: bool, control_manifest_sha256: str,
) -> dict[str, object]:
    if state not in {CONSUMED_MAINTENANCE, SEALED_MAINTENANCE}:
        raise QmtDataError("restricted control metadata requires a restricted state")
    return {
        "state": state,
        "authorization_present": bool(authorization_present),
        "control_manifest_sha256": _sha256(control_manifest_sha256, "control_manifest_sha256"),
        "content_visible": False,
        "statistics_visible": False,
        "research_eligible": False,
    }


def validate_manifest_state_transition(source_state: str, target_state: str) -> None:
    if source_state not in ALLOWED_STATES or target_state not in ALLOWED_STATES:
        raise QmtDataError("unknown manifest state")
    if source_state != target_state:
        raise QmtDataError("cross-state manifest promotion is forbidden")
