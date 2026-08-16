from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import FactorResearchReport


@dataclass(frozen=True)
class ResearchAgentArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode()).hexdigest()


def write_research_report(
    report: FactorResearchReport, output_dir: str | Path
) -> ResearchAgentArtifacts:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{report.trial_id}-factor-research"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    return ResearchAgentArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, report.to_json() + "\n"),
        markdown_sha256=_write(markdown_path, report.to_markdown()),
    )
