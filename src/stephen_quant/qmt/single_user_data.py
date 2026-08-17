from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import QmtDataError

SINGLE_USER_DATA_VERSION = "qd-single-user-integrity-0.1.0"
MANIFEST_VERSION = 1
PARSER_VERSION = "raw-byte-inventory-v1"
SCHEMA_VERSION = "single-user-maintenance-manifest-v1"
_STATES = {
    2025: "CONSUMED_2025_DATA_MAINTENANCE_ONLY",
    2026: "SEALED_2026_DATA_MAINTENANCE_ONLY",
}
_PURPOSES = frozenset({"pit-maintenance", "provenance-check", "schema-check", "quality-check"})
_PARTITION = re.compile(r"(?<!\d)(20\d{2})(?:[-_]?([01]\d)(?:[-_]?([0-3]\d))?)?(?!\d)")


@dataclass(frozen=True)
class LocalDataResult:
    event_id: str
    operation: str
    status: str
    year: int
    manifest_sha256: str
    operation_id: str | None
    summary_en: str
    summary_zh: str
    inferential_trial_delta: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise QmtDataError("manifest path must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise QmtDataError("manifest path must remain below the configured data root")
    return path.as_posix()


def _partition(relative: str, year: int) -> str | None:
    matches = [match for match in _PARTITION.finditer(relative) if int(match.group(1)) == year]
    if not matches:
        return None
    match = max(matches, key=lambda item: len(item.group(0)))
    month, day = match.group(2), match.group(3)
    return f"{year:04d}" + (f"-{month}" if month else "") + (f"-{day}" if day else "")


def _file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise QmtDataError("source file I/O failed") from exc
    return digest.hexdigest(), size


def _protect_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    try:
        resolved.chmod(0o700)
    except OSError as exc:
        raise QmtDataError("cannot protect local control directory") from exc
    return resolved


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise QmtDataError("event or operation has already been recorded") from exc
    except OSError as exc:
        raise QmtDataError("cannot write local control record") from exc


def _ledger_event(ledger_dir: Path, payload: dict[str, object]) -> str:
    event = {
        "profile_version": SINGLE_USER_DATA_VERSION,
        "event_id": _hash(payload),
        "inferential_trial_delta": 0,
        **payload,
    }
    directory = _protect_directory(ledger_dir / "events")
    target = directory / f"{event['event_id']}.json"
    if target.exists():
        return str(event["event_id"])
    _write_json_exclusive(target, event)
    return str(event["event_id"])


def _manifest_payload(raw: bytes) -> tuple[dict[str, object], str]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QmtDataError("manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise QmtDataError("manifest must be a JSON object")
    recorded = payload.pop("manifest_sha256", None)
    calculated = _hash(payload)
    if recorded != calculated:
        raise QmtDataError("manifest SHA-256 does not match its canonical content")
    if payload.get("version") != MANIFEST_VERSION or payload.get("plane") != "data_maintenance":
        raise QmtDataError("unsupported maintenance manifest")
    year = payload.get("year")
    if not isinstance(year, int) or payload.get("state") != _STATES.get(year):
        raise QmtDataError("manifest year/state mismatch")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise QmtDataError("manifest requires files")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise QmtDataError("manifest file entry must be an object")
        relative = _safe_relative(entry.get("path"))
        if relative in seen:
            raise QmtDataError("manifest contains duplicate paths")
        seen.add(relative)
        partition = entry.get("partition")
        if not isinstance(partition, str) or not partition.startswith(str(year)):
            raise QmtDataError("manifest partition does not match year")
        digest = str(entry.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise QmtDataError("manifest file SHA-256 is invalid")
        if not isinstance(entry.get("size_bytes"), int) or int(entry["size_bytes"]) < 0:
            raise QmtDataError("manifest file size is invalid")
    return payload, calculated


def _inventory_local_data_impl(
    data_root: str | Path,
    manifest_dir: str | Path,
    ledger_dir: str | Path,
    *,
    year: int,
    source_type: str = "local",
    code_commit: str,
) -> tuple[LocalDataResult, Path]:
    if year not in _STATES:
        raise QmtDataError("inventory year must be 2025 or 2026")
    root = Path(data_root).expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise QmtDataError("inventory root must be a real directory")
    started = _utc_now()
    entries: list[dict[str, object]] = []
    try:
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            for name in tuple(directories):
                if (current_path / name).is_symlink():
                    raise QmtDataError("inventory rejects symbolic-link directories")
            for name in sorted(filenames):
                source = current_path / name
                if source.is_symlink():
                    raise QmtDataError("inventory rejects symbolic-link files")
                resolved = source.resolve()
                try:
                    relative = resolved.relative_to(root).as_posix()
                except ValueError as exc:
                    raise QmtDataError("inventory path escapes configured root") from exc
                partition = _partition(relative, year)
                if partition is None:
                    continue
                digest, size = _file_sha256(resolved)
                entries.append({
                    "path": relative,
                    "partition": partition,
                    "sha256": digest,
                    "size_bytes": size,
                })
    except OSError as exc:
        raise QmtDataError("inventory directory scan failed") from exc
    if not entries:
        raise QmtDataError("inventory found no files for requested year")
    payload: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "plane": "data_maintenance",
        "state": _STATES[year],
        "year": year,
        "source_type": source_type,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "files": sorted(entries, key=lambda item: str(item["path"])),
    }
    manifest_sha = _hash(payload)
    document = {**payload, "manifest_sha256": manifest_sha}
    output_dir = _protect_directory(Path(manifest_dir))
    output = output_dir / f"maintenance-{year}-{manifest_sha}.json"
    if output.exists():
        existing_payload, existing_sha = _manifest_payload(output.read_bytes())
        if existing_sha != manifest_sha or existing_payload != payload:
            raise QmtDataError("existing manifest conflicts with deterministic inventory")
    else:
        _write_json_exclusive(output, document)
    finished = _utc_now()
    event_payload = {
        "operation": "inventory",
        "status": "success",
        "started_at": started.isoformat(),
        "completed_at": finished.isoformat(),
        "subject": getpass.getuser(),
        "year": year,
        "purpose": "manifest-inventory",
        "manifest_sha256": manifest_sha,
        "code_commit": code_commit,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "source_scope": [entry["path"] for entry in payload["files"]],
        "requested_outputs": ["manifest", "operation_status"],
    }
    event_id = _ledger_event(Path(ledger_dir), event_payload)
    return LocalDataResult(
        event_id, "inventory", "success", year, manifest_sha, None,
        "Deterministic raw-byte manifest created.", "已生成确定性原始字节清单。",
    ), output


def _create_local_unlock_impl(
    manifest_path: str | Path,
    ledger_dir: str | Path,
    *,
    year: int,
    purpose: str,
    expires_in_seconds: int,
    code_commit: str,
    allow_sealed_2026: bool = False,
) -> LocalDataResult:
    if purpose not in _PURPOSES:
        raise QmtDataError("local unlock purpose is not allowed")
    if expires_in_seconds <= 0 or expires_in_seconds > 86_400:
        raise QmtDataError("unlock expiry must be between 1 second and 24 hours")
    payload, manifest_sha = _manifest_payload(Path(manifest_path).read_bytes())
    if payload["year"] != year:
        raise QmtDataError("unlock year does not match manifest")
    if year == 2026 and not allow_sealed_2026:
        raise QmtDataError("2026 remains sealed without an explicit sealed-year flag")
    operation_id = uuid.uuid4().hex
    created = _utc_now()
    unlock = {
        "version": 1,
        "profile_version": SINGLE_USER_DATA_VERSION,
        "operation_id": operation_id,
        "subject": getpass.getuser(),
        "year": year,
        "state": _STATES[year],
        "purpose": purpose,
        "manifest_sha256": manifest_sha,
        "code_commit": code_commit,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "requested_outputs": ["manifest", "provenance", "operation_status"],
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(seconds=expires_in_seconds)).isoformat(),
    }
    directory = _protect_directory(Path(ledger_dir) / "unlocks")
    _write_json_exclusive(directory / f"{operation_id}.json", unlock)
    event_id = _ledger_event(Path(ledger_dir), {
        **unlock, "operation": "unlock", "status": "success", "event_time": created.isoformat()
    })
    return LocalDataResult(
        event_id, "unlock", "success", year, manifest_sha, operation_id,
        "Short-lived local unlock created.", "已创建短期本机解锁。",
    )


def _finalize(path: Path, record: dict[str, object], status: str) -> None:
    completed = {**record, "status": status, "completed_at": _utc_now().isoformat()}
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    _write_json_exclusive(temporary, completed)
    try:
        os.replace(temporary, path)
    except OSError as exc:
        raise QmtDataError("cannot finalize maintenance operation") from exc


def _maintain_local_data_impl(
    data_root: str | Path,
    manifest_path: str | Path,
    ledger_dir: str | Path,
    *,
    operation_id: str,
    code_commit: str,
) -> LocalDataResult:
    manifest, manifest_sha = _manifest_payload(Path(manifest_path).read_bytes())
    ledger = Path(ledger_dir)
    unlock_path = ledger / "unlocks" / f"{operation_id}.json"
    try:
        unlock = json.loads(unlock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QmtDataError("valid local unlock is required before maintenance") from exc
    now = _utc_now()
    try:
        expires = datetime.fromisoformat(str(unlock["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise QmtDataError("local unlock expiry is invalid") from exc
    if (
        expires.tzinfo is None
        or now > expires
        or unlock.get("year") != manifest.get("year")
        or unlock.get("state") != manifest.get("state")
        or unlock.get("manifest_sha256") != manifest_sha
        or unlock.get("code_commit") != code_commit
        or unlock.get("operation_id") != operation_id
    ):
        raise QmtDataError("local unlock does not match this maintenance request")
    operations = _protect_directory(ledger / "operations")
    operation_path = operations / f"{operation_id}.json"
    reserved = {
        "profile_version": SINGLE_USER_DATA_VERSION,
        "operation": "maintain",
        "operation_id": operation_id,
        "subject": unlock["subject"],
        "year": manifest["year"],
        "purpose": unlock["purpose"],
        "manifest_sha256": manifest_sha,
        "code_commit": code_commit,
        "parser_version": manifest["parser_version"],
        "schema_version": manifest["schema_version"],
        "source_scope": [entry["path"] for entry in manifest["files"]],
        "requested_outputs": unlock["requested_outputs"],
        "inferential_trial_delta": 0,
        "status": "reserved",
        "reserved_at": now.isoformat(),
    }
    _write_json_exclusive(operation_path, reserved)
    root = Path(data_root).expanduser().resolve()
    try:
        if not root.is_dir() or root.is_symlink():
            raise QmtDataError("configured data root is invalid")
        for entry in manifest["files"]:
            relative = _safe_relative(entry["path"])
            source = (root / relative).resolve()
            try:
                source.relative_to(root)
            except ValueError as exc:
                raise QmtDataError("maintenance source path escapes configured root") from exc
            if source.is_symlink():
                raise QmtDataError("maintenance rejects symbolic-link files")
            digest, size = _file_sha256(source)
            if size != entry["size_bytes"]:
                raise QmtDataError("maintenance source size does not match manifest")
            if digest != entry["sha256"]:
                raise QmtDataError("maintenance source SHA-256 does not match manifest")
    except (QmtDataError, OSError):
        _finalize(operation_path, reserved, "failed")
        raise
    _finalize(operation_path, reserved, "success")
    event_id = _ledger_event(ledger, {
        **reserved, "status": "success", "completed_at": _utc_now().isoformat()
    })
    return LocalDataResult(
        event_id, "maintain", "success", int(manifest["year"]), manifest_sha, operation_id,
        "Manifest-bound maintenance verification succeeded.",
        "基于冻结清单的数据维护验证成功。",
    )


def _best_effort_manifest_identity(manifest_path: str | Path) -> tuple[int, str]:
    try:
        payload, manifest_sha = _manifest_payload(Path(manifest_path).read_bytes())
        return int(payload["year"]), manifest_sha
    except (OSError, QmtDataError, KeyError, TypeError, ValueError):
        return 0, ""


def inventory_local_data(
    data_root: str | Path,
    manifest_dir: str | Path,
    ledger_dir: str | Path,
    *,
    year: int,
    source_type: str = "local",
    code_commit: str,
) -> tuple[LocalDataResult, Path]:
    try:
        return _inventory_local_data_impl(
            data_root, manifest_dir, ledger_dir, year=year,
            source_type=source_type, code_commit=code_commit,
        )
    except QmtDataError:
        _ledger_event(Path(ledger_dir), {
            "operation": "inventory",
            "status": "failed",
            "event_time": _utc_now().isoformat(),
            "subject": getpass.getuser(),
            "year": year,
            "purpose": "manifest-inventory",
            "manifest_sha256": "",
            "code_commit": code_commit,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "source_scope": [],
            "requested_outputs": ["manifest", "operation_status"],
        })
        raise


def create_local_unlock(
    manifest_path: str | Path,
    ledger_dir: str | Path,
    *,
    year: int,
    purpose: str,
    expires_in_seconds: int,
    code_commit: str,
    allow_sealed_2026: bool = False,
) -> LocalDataResult:
    try:
        return _create_local_unlock_impl(
            manifest_path, ledger_dir, year=year, purpose=purpose,
            expires_in_seconds=expires_in_seconds, code_commit=code_commit,
            allow_sealed_2026=allow_sealed_2026,
        )
    except (OSError, QmtDataError) as exc:
        manifest_year, manifest_sha = _best_effort_manifest_identity(manifest_path)
        _ledger_event(Path(ledger_dir), {
            "operation": "unlock",
            "status": "denied",
            "event_time": _utc_now().isoformat(),
            "subject": getpass.getuser(),
            "year": manifest_year or year,
            "purpose": purpose,
            "manifest_sha256": manifest_sha,
            "code_commit": code_commit,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "source_scope": [],
            "requested_outputs": ["operation_status"],
        })
        if isinstance(exc, QmtDataError):
            raise
        raise QmtDataError("unlock manifest I/O failed") from exc


def maintain_local_data(
    data_root: str | Path,
    manifest_path: str | Path,
    ledger_dir: str | Path,
    *,
    operation_id: str,
    code_commit: str,
) -> LocalDataResult:
    try:
        return _maintain_local_data_impl(
            data_root, manifest_path, ledger_dir,
            operation_id=operation_id, code_commit=code_commit,
        )
    except (OSError, QmtDataError) as exc:
        year, manifest_sha = _best_effort_manifest_identity(manifest_path)
        _ledger_event(Path(ledger_dir), {
            "operation": "maintain",
            "status": "denied",
            "event_time": _utc_now().isoformat(),
            "operation_id": operation_id,
            "subject": getpass.getuser(),
            "year": year,
            "purpose": "local-maintenance",
            "manifest_sha256": manifest_sha,
            "code_commit": code_commit,
            "parser_version": PARSER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "source_scope": [],
            "requested_outputs": ["operation_status"],
        })
        if isinstance(exc, QmtDataError):
            raise
        raise QmtDataError("maintenance control I/O failed") from exc
