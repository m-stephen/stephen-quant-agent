from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import QmtDataError
from .pit_staging import (
    PIT_STAGING_VERSION,
    CorporateActionPIT,
    IndustryMembershipPIT,
    validate_corporate_actions,
    validate_industry_memberships,
    write_pit_bundle,
)

AUTHORITATIVE_SOURCE_VERSION = "qd-authoritative-source-0.1.0"


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_id(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise QmtDataError(f"{field} must be 64 hexadecimal characters")
    return normalized


def _safe_operation_id(value: str) -> str:
    normalized = str(value).strip()
    if not normalized or normalized in {".", ".."} or Path(normalized).name != normalized:
        raise QmtDataError("operation_id must be one safe path component")
    return normalized


def _read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise QmtDataError(f"JSONL row {line_number} must be an object")
        rows.append(value)
    return tuple(rows)


@dataclass(frozen=True)
class VerifiedSourceDocument:
    source_document_id: str
    source_type: str
    source_hash: str
    size: int


@dataclass(frozen=True)
class AuthoritativeSourceResult:
    operation_id: str
    bundle_sha256: str
    manifest_sha256: str
    industry_rows: int
    corporate_action_rows: int
    announcement_links: int
    output_dir: Path


def build_authoritative_source_bundle(config_path: Path) -> AuthoritativeSourceResult:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    operation_id = _safe_operation_id(config["operation_id"])
    output_root = Path(config["output_dir"]).resolve()

    document_paths = {
        str(source_id).strip(): Path(path).resolve()
        for source_id, path in config.get("document_files", {}).items()
    }
    if not document_paths:
        raise QmtDataError("at least one source document is required")
    if any(not source_id for source_id in document_paths):
        raise QmtDataError("source_document_id cannot be empty")
    if len(document_paths) != len(config.get("document_files", {})):
        raise QmtDataError("duplicate source_document_id")

    source_types = {str(key): str(value).strip() for key, value in config["source_types"].items()}
    allowed_types = {"sse_announcement", "szse_announcement", "licensed_industry_source"}
    if set(document_paths) != set(source_types):
        raise QmtDataError("source_types must cover exactly all source documents")
    if any(value not in allowed_types for value in source_types.values()):
        raise QmtDataError("unsupported authoritative source_type")

    industry_path = Path(config["industry_records"]).resolve() \
        if config.get("industry_records") else None
    corporate_path = Path(config["corporate_action_records"]).resolve() \
        if config.get("corporate_action_records") else None
    record_paths = tuple(path for path in (industry_path, corporate_path) if path is not None)
    all_sources = tuple(document_paths.values()) + record_paths
    if any(output_root == path.parent or output_root.is_relative_to(path.parent)
           for path in all_sources):
        raise QmtDataError("output_dir must be physically disjoint from all source directories")

    verified: dict[str, VerifiedSourceDocument] = {}
    file_manifest: list[dict[str, object]] = []
    for source_id, path in sorted(document_paths.items()):
        raw = path.read_bytes()
        if not raw:
            raise QmtDataError("source document cannot be empty")
        digest = _sha256_bytes(raw)
        verified[source_id] = VerifiedSourceDocument(
            source_document_id=source_id,
            source_type=source_types[source_id],
            source_hash=digest,
            size=len(raw),
        )
        file_manifest.append({
            "role": "source_document", "source_document_id": source_id,
            "source_type": source_types[source_id], "size": len(raw), "sha256": digest,
        })

    def bind_document(row: dict[str, Any]) -> dict[str, Any]:
        source_id = str(row.get("source_document_id", "")).strip()
        document = verified.get(source_id)
        if document is None:
            raise QmtDataError("PIT row has no verified source document")
        supplied_hash = row.get("source_hash")
        if supplied_hash is not None and _sha256_id(supplied_hash, "source_hash") != document.source_hash:
            raise QmtDataError("declared source_hash does not match source document bytes")
        bound = dict(row)
        bound["source_hash"] = document.source_hash
        return bound

    industry_raw = _read_jsonl(industry_path) if industry_path else ()
    corporate_raw = _read_jsonl(corporate_path) if corporate_path else ()
    industry = validate_industry_memberships(tuple(
        IndustryMembershipPIT(**bind_document(row)) for row in industry_raw
    ))
    corporate = validate_corporate_actions(tuple(
        CorporateActionPIT(**bind_document(row)) for row in corporate_raw
    ))

    links: dict[str, dict[str, str]] = {}
    for raw_hash, source_id_value in config.get("announcement_document_links", {}).items():
        transient_hash = _sha256_id(raw_hash, "transient-ID hash")
        source_id = str(source_id_value).strip()
        document = verified.get(source_id)
        if document is None or document.source_type not in {"sse_announcement", "szse_announcement"}:
            raise QmtDataError("announcement link must reference a verified exchange document")
        links[transient_hash] = {
            "source_document_id": source_id,
            "source_hash": document.source_hash,
        }

    operation_dir = output_root / operation_id
    operation_dir.mkdir(parents=True, exist_ok=False)
    bundle_hash = write_pit_bundle(
        financial=(), industry=industry, corporate_actions=corporate,
        output=operation_dir / "pit-bundle.json",
    )
    links_raw = (json.dumps(links, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (operation_dir / "announcement-document-links.json").write_bytes(links_raw)

    for role, path in (("industry_records", industry_path),
                       ("corporate_action_records", corporate_path)):
        if path is not None:
            raw = path.read_bytes()
            file_manifest.append({"role": role, "size": len(raw), "sha256": _sha256_bytes(raw)})
    manifest = {
        "schema_version": AUTHORITATIVE_SOURCE_VERSION,
        "pit_schema_version": PIT_STAGING_VERSION,
        "operation_id": operation_id,
        "bundle_sha256": bundle_hash,
        "formal_research_eligible": False,
        "inferential_trial_delta": 0,
        "industry_rows": len(industry),
        "corporate_action_rows": len(corporate),
        "announcement_links": len(links),
        "announcement_link_set_sha256": _sha256_bytes(links_raw),
        "files": sorted(file_manifest, key=lambda row: (
            str(row["role"]), str(row.get("source_document_id", ""))
        )),
    }
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n").encode()
    manifest_hash = _sha256_bytes(manifest_raw)
    (operation_dir / "authoritative-source-manifest.json").write_bytes(manifest_raw)
    evidence = {
        "operation_id": operation_id,
        "status": "success",
        "manifest_sha256": manifest_hash,
        "bundle_sha256": bundle_hash,
        "source_documents": [asdict(row) for row in sorted(
            verified.values(), key=lambda row: row.source_document_id
        )],
        "inferential_trial_delta": 0,
        "formal_research_eligible": False,
    }
    (operation_dir / "operation-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8", newline="\n",
    )
    return AuthoritativeSourceResult(
        operation_id=operation_id, bundle_sha256=bundle_hash,
        manifest_sha256=manifest_hash, industry_rows=len(industry),
        corporate_action_rows=len(corporate), announcement_links=len(links),
        output_dir=operation_dir,
    )
