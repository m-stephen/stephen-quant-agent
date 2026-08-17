from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import QmtDataError

SOURCE_COMPLETION_VERSION = "qd-source-completion-0.1.0"
_ALLOWED_STATES = {
    2022: "RESEARCH_ALLOWED_2022_2024",
    2023: "RESEARCH_ALLOWED_2022_2024",
    2024: "RESEARCH_ALLOWED_2022_2024",
    2025: "CONSUMED_2025_DATA_MAINTENANCE_ONLY",
    2026: "SEALED_2026_DATA_MAINTENANCE_ONLY",
}


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.resolve().read_bytes()
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise QmtDataError("completion input must be a JSON object")
    return value, _hash(raw)


@dataclass(frozen=True)
class SourceCompletionReport:
    version: str
    candidate_commit: str
    alphapai_years: tuple[int, ...]
    alphapai_manifest_hashes: tuple[str, ...]
    authoritative_manifest_hashes: tuple[str, ...]
    unresolved_quarantine_records: int
    industry_rows: int
    corporate_action_rows: int
    provenance_breaks: int
    state_violations: int
    formal_research_eligible: bool
    gate_pass: bool
    blockers: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))


def build_source_completion_report(config_path: Path) -> SourceCompletionReport:
    config, _ = _load(config_path)
    commit = str(config.get("candidate_commit", "")).strip().lower()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise QmtDataError("candidate_commit must be a full 40-character Git SHA")
    expected_years = tuple(int(year) for year in config.get("expected_years", ()))
    if expected_years != (2022, 2023, 2024, 2025, 2026):
        raise QmtDataError("expected_years must be exactly 2022 through 2026")
    entries = tuple(config.get("alphapai_manifests", ()))
    years = tuple(sorted(int(entry["year"]) for entry in entries))
    if years != expected_years or len(set(years)) != len(years):
        raise QmtDataError("exactly one AlphaPai manifest is required for every expected year")

    blockers: list[str] = []
    quarantine = provenance_breaks = state_violations = 0
    alphapai_hashes: list[str] = []
    for entry in sorted(entries, key=lambda row: int(row["year"])):
        year = int(entry["year"])
        manifest, digest = _load(Path(entry["path"]))
        alphapai_hashes.append(digest)
        if str(entry.get("state")) != _ALLOWED_STATES[year]:
            state_violations += 1
        if manifest.get("formal_research_eligible") is not False:
            state_violations += 1
        count = int(manifest.get("quarantined_source_records", -1))
        identities = manifest.get("quarantined_transient_id_hashes")
        if count < 0 or not isinstance(identities, list) or len(identities) != count:
            provenance_breaks += 1
        else:
            quarantine += count
        if manifest.get("inferential_trial_delta") != 0:
            state_violations += 1

    industry_rows = corporate_rows = 0
    authoritative_hashes: list[str] = []
    for raw_path in config.get("authoritative_manifests", ()):
        manifest, digest = _load(Path(raw_path))
        authoritative_hashes.append(digest)
        if manifest.get("formal_research_eligible") is not False \
                or manifest.get("inferential_trial_delta") != 0:
            state_violations += 1
        industry_rows += int(manifest.get("industry_rows", 0))
        corporate_rows += int(manifest.get("corporate_action_rows", 0))
        if not isinstance(manifest.get("files"), list) or not manifest["files"]:
            provenance_breaks += 1

    if quarantine:
        blockers.append(f"{quarantine} source records remain quarantined")
    if industry_rows <= 0:
        blockers.append("authoritative stock-level historical industry membership is absent")
    if corporate_rows <= 0:
        blockers.append("authoritative corporate-action PIT rows are absent")
    if provenance_breaks:
        blockers.append(f"{provenance_breaks} provenance contracts are broken")
    if state_violations:
        blockers.append(f"{state_violations} restricted-state contracts are violated")

    return SourceCompletionReport(
        version=SOURCE_COMPLETION_VERSION, candidate_commit=commit,
        alphapai_years=years, alphapai_manifest_hashes=tuple(alphapai_hashes),
        authoritative_manifest_hashes=tuple(authoritative_hashes),
        unresolved_quarantine_records=quarantine, industry_rows=industry_rows,
        corporate_action_rows=corporate_rows, provenance_breaks=provenance_breaks,
        state_violations=state_violations, formal_research_eligible=False,
        gate_pass=not blockers, blockers=tuple(blockers),
    )


def write_source_completion_report(report: SourceCompletionReport, output: Path) -> str:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = (report.to_json() + "\n").encode()
    with output.open("xb") as handle:
        handle.write(raw)
    return _hash(raw)
