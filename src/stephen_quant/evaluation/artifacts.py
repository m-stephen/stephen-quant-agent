from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import AlphaCard


@dataclass(frozen=True)
class AlphaCardArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def _write_text(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_alpha_card(card: AlphaCard, output_dir: str | Path) -> AlphaCardArtifacts:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{card.lineage.factor_id}-{card.lineage.factor_version}-alpha-card"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    return AlphaCardArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write_text(json_path, card.to_json() + "\n"),
        markdown_sha256=_write_text(markdown_path, card.to_markdown()),
    )
