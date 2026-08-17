from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FIREWALL_VERSION = "v2.7-information-firewall-1.0.0"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class AllowlistedFile:
    logical_id: str
    path: str
    available_through: str
    content_sha256: str

    def validate(self, cutoff: date) -> None:
        if not self.logical_id.strip() or not self.path.strip():
            raise ValueError("allowlisted file requires logical identity and explicit path")
        try:
            available = date.fromisoformat(self.available_through)
        except ValueError as exc:
            raise ValueError("allowlisted file availability must be an ISO date") from exc
        if available > cutoff:
            raise ValueError("allowlisted file exceeds the research cutoff")
        if len(self.content_sha256) != 64:
            raise ValueError("allowlisted file requires a SHA-256")

    def redacted_payload(self) -> dict[str, str]:
        return {
            "logical_id": self.logical_id,
            "available_through": self.available_through,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class BoundedResearchManifest:
    version: str
    research_cutoff: str
    files: tuple[AllowlistedFile, ...]

    def validate(self) -> None:
        if self.version != FIREWALL_VERSION:
            raise ValueError("unsupported information-firewall manifest")
        try:
            cutoff = date.fromisoformat(self.research_cutoff)
        except ValueError as exc:
            raise ValueError("research cutoff must be an ISO date") from exc
        if cutoff >= date(2025, 1, 1):
            raise ValueError("V2.7 research manifest cannot reach consumed or sealed windows")
        logical_ids = [item.logical_id for item in self.files]
        paths = [str(Path(item.path).resolve()) for item in self.files]
        if len(logical_ids) != len(set(logical_ids)) or len(paths) != len(set(paths)):
            raise ValueError("allowlisted logical IDs and paths must be unique")
        for item in self.files:
            item.validate(cutoff)

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(
            {
                "version": self.version,
                "research_cutoff": self.research_cutoff,
                "files": [item.redacted_payload() for item in self.files],
            }
        )


@dataclass(frozen=True)
class FirewallAudit:
    manifest_sha256: str
    opened_logical_ids: tuple[str, ...]
    hashed_logical_ids: tuple[str, ...]
    denied_attempts: tuple[str, ...]
    directory_enumerations: int
    consumed_window_accesses: int
    sealed_window_accesses: int

    @property
    def passed(self) -> bool:
        return (
            self.directory_enumerations == 0
            and self.consumed_window_accesses == 0
            and self.sealed_window_accesses == 0
        )


class SealedDataFirewall:
    """Read only explicit manifest entries; directory discovery is deliberately unsupported."""

    def __init__(self, manifest: BoundedResearchManifest) -> None:
        manifest.validate()
        self.manifest = manifest
        self._by_id = {item.logical_id: item for item in manifest.files}
        self._opened: list[str] = []
        self._hashed: list[str] = []
        self._denied: list[str] = []

    def read_bytes(self, logical_id: str) -> bytes:
        entry = self._by_id.get(logical_id)
        if entry is None:
            self._denied.append(logical_id)
            raise PermissionError("file is absent from the frozen research manifest")
        payload = Path(entry.path).read_bytes()
        self._opened.append(logical_id)
        digest = hashlib.sha256(payload).hexdigest()
        self._hashed.append(logical_id)
        if digest != entry.content_sha256:
            raise ValueError("allowlisted file content differs from the frozen SHA-256")
        return payload

    def audit(self) -> FirewallAudit:
        return FirewallAudit(
            self.manifest.sha256,
            tuple(self._opened),
            tuple(self._hashed),
            tuple(self._denied),
            directory_enumerations=0,
            consumed_window_accesses=0,
            sealed_window_accesses=0,
        )


def decision_hash_without_sealed_data(
    manifest: BoundedResearchManifest, governance_payload: dict[str, object]
) -> str:
    """Hash only redacted allowlist evidence and governance; no file or directory access occurs."""

    manifest.validate()
    return _sha(
        {
            "firewall_version": FIREWALL_VERSION,
            "manifest_sha256": manifest.sha256,
            "governance": governance_payload,
        }
    )
