from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .models import QmtDataError
from .pit_staging import CorporateActionPIT, validate_corporate_actions, write_pit_bundle

CORPORATE_ACTION_MAINTENANCE_VERSION = "corporate-action-maintenance-0.1.0"


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if path == root or not path.is_relative_to(root):
        raise QmtDataError("manifest path escapes operation directory")
    return path


@dataclass(frozen=True)
class CorporateActionMergeResult:
    rows: int
    operation_manifests: int
    bundle_sha256: str
    manifest_sha256: str
    output_dir: Path


def merge_corporate_action_operations(config_path: Path) -> CorporateActionMergeResult:
    config = json.loads(config_path.resolve().read_text(encoding="utf-8"))
    expected = tuple(config["expected_partitions"])
    operations = tuple(config["operations"])
    actual = tuple(sorted(str(row["partition"]) for row in operations))
    if actual != tuple(sorted(expected)) or len(set(actual)) != len(expected):
        raise QmtDataError("operations must cover every expected partition exactly once")
    output_root = Path(config["output_dir"]).resolve()
    operation_id = str(config["operation_id"]).strip()
    if not operation_id or Path(operation_id).name != operation_id:
        raise QmtDataError("operation_id must be one safe path component")

    rows: list[CorporateActionPIT] = []
    source_manifests: list[dict[str, object]] = []
    for entry in sorted(operations, key=lambda row: str(row["partition"])):
        root = Path(entry["operation_dir"]).resolve()
        manifest_path = root / "manifest.json"
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8-sig"))
        if manifest.get("quarantined_records") != 0 \
                or manifest.get("quarantined_identity_hashes") != []:
            raise QmtDataError("source operation contains quarantined records")
        if manifest.get("formal_research_eligible") is not False \
                or manifest.get("inferential_trial_delta") != 0:
            raise QmtDataError("source operation violates maintenance-only state")
        for file_row in manifest.get("files", []):
            path = _safe_file(root, str(file_row["path"]))
            raw = path.read_bytes()
            if len(raw) != int(file_row["size"]) or _digest(raw) != file_row["sha256"]:
                raise QmtDataError("source operation file evidence mismatch")
        bundle_path = root / "corporate-actions.json"
        values = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
        if len(values) != int(manifest["accepted_rows"]):
            raise QmtDataError("normalized row count does not match source manifest")
        rows.extend(CorporateActionPIT(**value) for value in values)
        source_manifests.append({
            "partition": entry["partition"], "operation_id": manifest["operation_id"],
            "manifest_size": len(manifest_raw), "manifest_sha256": _digest(manifest_raw),
            "accepted_rows": manifest["accepted_rows"],
        })

    unique: dict[tuple[str, str, str], CorporateActionPIT] = {}
    for row in rows:
        key = (row.code.upper(), row.event_type, row.revision_id)
        existing = unique.get(key)
        if existing is not None and existing != row:
            raise QmtDataError("conflicting duplicate corporate-action revision")
        unique[key] = row
    chains: dict[tuple[str, str, str], list[CorporateActionPIT]] = {}
    for row in unique.values():
        chains.setdefault((row.code.upper(), row.event_type, row.effective_date), []).append(row)
    chained: list[CorporateActionPIT] = []
    for chain in chains.values():
        ordered = sorted(chain, key=lambda row: (
            datetime.fromisoformat(row.available_at), row.revision_id
        ))
        for index, row in enumerate(ordered):
            chained.append(replace(
                row, supersedes_revision_id=None if index == 0 else ordered[index - 1].revision_id
            ))
    normalized = validate_corporate_actions(tuple(chained))
    operation_dir = output_root / operation_id
    operation_dir.mkdir(parents=True, exist_ok=False)
    bundle_hash = write_pit_bundle(
        financial=(), industry=(), corporate_actions=normalized,
        output=operation_dir / "pit-bundle.json",
    )
    manifest = {
        "schema_version": CORPORATE_ACTION_MAINTENANCE_VERSION,
        "operation_id": operation_id, "partitions": list(expected),
        "operation_manifests": source_manifests, "corporate_action_rows": len(normalized),
        "duplicate_revisions_removed": len(rows) - len(normalized),
        "quarantined_records": 0, "provenance_breaks": 0,
        "bundle_sha256": bundle_hash, "inferential_trial_delta": 0,
        "formal_research_eligible": False,
    }
    raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")) + "\n").encode()
    manifest_hash = _digest(raw)
    (operation_dir / "corporate-action-manifest.json").write_bytes(raw)
    return CorporateActionMergeResult(
        rows=len(normalized), operation_manifests=len(source_manifests),
        bundle_sha256=bundle_hash, manifest_sha256=manifest_hash,
        output_dir=operation_dir,
    )
