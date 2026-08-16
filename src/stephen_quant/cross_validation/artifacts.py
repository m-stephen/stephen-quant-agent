from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.integrity.audit import AuditFinding

from .models import SplitManifest


@dataclass(frozen=True)
class SplitArtifacts:
    manifest_path: Path
    audit_path: Path
    manifest_sha256: str
    audit_sha256: str


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_split_artifacts(
    manifest: SplitManifest,
    findings: tuple[AuditFinding, ...],
    output_dir: str | Path,
) -> SplitArtifacts:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "cpcv-manifest.json"
    audit_path = directory / "cpcv-audit.json"
    manifest_content = manifest.to_json() + "\n"
    audit_content = json.dumps(
        [asdict(finding) for finding in findings],
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
    return SplitArtifacts(
        manifest_path=manifest_path,
        audit_path=audit_path,
        manifest_sha256=_write(manifest_path, manifest_content),
        audit_sha256=_write(audit_path, audit_content),
    )
