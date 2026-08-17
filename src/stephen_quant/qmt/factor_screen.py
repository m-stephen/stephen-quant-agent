from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path

from stephen_quant.evaluation import EvaluationError, spearman_correlation
from stephen_quant.factors import FactorDefinition

from .models import QmtDailyBar, QmtDataError
from .observations import build_qmt_factor_observations

FACTOR_SCREEN_VERSION = "qd-factor-redundancy-screen-1.0.0"


@dataclass(frozen=True)
class FactorCorrelationPair:
    left_factor: str
    right_factor: str
    mean_rank_correlation: float | None
    dates: int


@dataclass(frozen=True)
class FactorRedundancyScreen:
    method_version: str
    source_snapshot_sha256: str
    screen_start: str
    screen_end: str
    instruments: int
    factor_keys: tuple[str, ...]
    high_correlation_threshold: float
    pairs: tuple[FactorCorrelationPair, ...]
    high_correlation_pairs: tuple[FactorCorrelationPair, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# QD factor redundancy screen",
            "",
            f"- Method: `{self.method_version}`",
            f"- Source snapshot: `{self.source_snapshot_sha256}`",
            f"- Window: {self.screen_start} to {self.screen_end}",
            f"- Instruments: {self.instruments}",
            f"- Factors: {len(self.factor_keys)}",
            f"- High-correlation threshold: {self.high_correlation_threshold:.2f}",
            f"- High-correlation pairs: {len(self.high_correlation_pairs)}",
            "",
            "| Left | Right | Mean rank correlation | Dates |",
            "|---|---|---:|---:|",
        ]
        pairs = self.high_correlation_pairs or self.pairs
        lines.extend(
            f"| `{pair.left_factor}` | `{pair.right_factor}` | "
            f"{pair.mean_rank_correlation if pair.mean_rank_correlation is not None else 'N/A'} "
            f"| {pair.dates} |"
            for pair in pairs
        )
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class FactorScreenArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def screen_factor_redundancy(
    bars: tuple[QmtDailyBar, ...],
    definitions: tuple[FactorDefinition, ...],
    *,
    source_snapshot_sha256: str,
    screen_start: str,
    screen_end: str,
    high_correlation_threshold: float = 0.8,
) -> FactorRedundancyScreen:
    if not 0 < high_correlation_threshold <= 1:
        raise QmtDataError("high_correlation_threshold must be in (0, 1]")
    if len(definitions) < 2:
        raise QmtDataError("factor redundancy screen requires at least two definitions")
    instruments = len({bar.instrument for bar in bars})
    if instruments < 3:
        raise QmtDataError("factor redundancy screen requires at least three instruments")

    values: dict[str, dict[tuple[str, str], float]] = {}
    for definition in definitions:
        observations = build_qmt_factor_observations(
            bars,
            definition,
            test_start=screen_start,
            test_end=screen_end,
        )
        values[definition.key] = {
            (row.execution_at, row.instrument): definition.direction * row.signal
            for row in observations
        }

    pairs: list[FactorCorrelationPair] = []
    for left, right in combinations(sorted(values), 2):
        common = sorted(set(values[left]) & set(values[right]))
        by_date: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for timestamp, instrument in common:
            by_date[timestamp].append(
                (values[left][(timestamp, instrument)], values[right][(timestamp, instrument)])
            )
        correlations: list[float] = []
        for rows in by_date.values():
            if len(rows) < 3:
                continue
            try:
                correlations.append(
                    spearman_correlation(
                        [row[0] for row in rows], [row[1] for row in rows]
                    )
                )
            except EvaluationError:
                continue
        mean = sum(correlations) / len(correlations) if correlations else None
        pairs.append(
            FactorCorrelationPair(
                left_factor=left,
                right_factor=right,
                mean_rank_correlation=mean,
                dates=len(correlations),
            )
        )
    high = tuple(
        pair
        for pair in pairs
        if pair.mean_rank_correlation is not None
        and abs(pair.mean_rank_correlation) >= high_correlation_threshold
    )
    return FactorRedundancyScreen(
        method_version=FACTOR_SCREEN_VERSION,
        source_snapshot_sha256=source_snapshot_sha256,
        screen_start=screen_start,
        screen_end=screen_end,
        instruments=instruments,
        factor_keys=tuple(sorted(values)),
        high_correlation_threshold=high_correlation_threshold,
        pairs=tuple(pairs),
        high_correlation_pairs=high,
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_factor_redundancy_screen(
    screen: FactorRedundancyScreen, output_dir: str | Path
) -> FactorScreenArtifacts:
    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "factor-redundancy-screen.json"
    markdown_path = directory / "factor-redundancy-screen.md"
    json_content = screen.to_json() + "\n"
    markdown_content = screen.to_markdown()
    return FactorScreenArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
    )
