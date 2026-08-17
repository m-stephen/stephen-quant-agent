from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from stephen_quant.baseline import BaselineObservation
from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.falsification import PlaceboResult, run_placebo

PLACEBO_AUDIT_VERSION = "qd-cross-sectional-placebo-audit-1.0.0"


@dataclass(frozen=True)
class QdPlaceboAudit:
    method_version: str
    horizon: str
    observations: int
    dates: int
    signal_shuffle: PlaceboResult
    return_permutation: PlaceboResult
    max_p_value: float
    passed: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        return "\n".join(
            (
                "# QD placebo audit",
                "",
                f"**Decision: {'PASS' if self.passed else 'REJECT'}**",
                "",
                f"- Method: `{self.method_version}`",
                f"- Horizon: {self.horizon}",
                f"- Observations: {self.observations}",
                f"- Dates: {self.dates}",
                f"- Signal-shuffle p-value: {self.signal_shuffle.empirical_p_value:.6f}",
                f"- Return-permutation p-value: {self.return_permutation.empirical_p_value:.6f}",
                f"- Maximum accepted p-value: {self.max_p_value:.6f}",
                "",
            )
        )


@dataclass(frozen=True)
class QdPlaceboArtifacts:
    json_path: Path
    markdown_path: Path
    json_sha256: str
    markdown_sha256: str


def run_qd_placebo_audit(
    observations: tuple[BaselineObservation, ...],
    *,
    direction: int,
    repetitions: int,
    seed: int,
    max_p_value: float = 0.05,
) -> QdPlaceboAudit:
    rows = tuple(
        EvaluationObservation(
            timestamp=row.signal_at,
            instrument=row.instrument,
            factor_value=row.signal,
            factor_available_at=row.signal_available_at,
            label_start_at=row.execution_at,
            label_end_at=row.return_end_at,
            forward_return=row.forward_return,
            horizon="next_open",
            subperiod=row.execution_at[:4],
            regime="unclassified",
        )
        for row in observations
    )
    signal = run_placebo(
        rows,
        horizon="next_open",
        direction=direction,
        method="signal_shuffle",
        seed=seed,
        repetitions=repetitions,
    )
    returns = run_placebo(
        rows,
        horizon="next_open",
        direction=direction,
        method="return_permutation",
        seed=seed + 1,
        repetitions=repetitions,
    )
    passed = (
        signal.empirical_p_value <= max_p_value
        and returns.empirical_p_value <= max_p_value
    )
    return QdPlaceboAudit(
        method_version=PLACEBO_AUDIT_VERSION,
        horizon="next_open",
        observations=len(rows),
        dates=len({row.timestamp for row in rows}),
        signal_shuffle=signal,
        return_permutation=returns,
        max_p_value=max_p_value,
        passed=passed,
    )


def _write(path: Path, content: str) -> str:
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_qd_placebo_audit(
    audit: QdPlaceboAudit, output_dir: str | Path
) -> QdPlaceboArtifacts:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "placebo-audit.json"
    markdown_path = directory / "placebo-audit.md"
    json_content = audit.to_json() + "\n"
    markdown_content = audit.to_markdown()
    return QdPlaceboArtifacts(
        json_path=json_path,
        markdown_path=markdown_path,
        json_sha256=_write(json_path, json_content),
        markdown_sha256=_write(markdown_path, markdown_content),
    )
