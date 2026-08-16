from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvaluationObservation:
    """One point-in-time factor observation paired with one forward label."""

    timestamp: str
    instrument: str
    factor_value: float
    factor_available_at: str
    label_start_at: str
    label_end_at: str
    forward_return: float
    horizon: str
    subperiod: str
    regime: str


@dataclass(frozen=True)
class EvaluationLineage:
    factor_id: str
    factor_version: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str


@dataclass(frozen=True)
class MetricSummary:
    horizon: str
    observations: int
    dates: int
    mean_ic: float
    mean_rank_ic: float
    icir: float | None
    rank_icir: float | None
    ic_hit_rate: float
    rank_ic_hit_rate: float


@dataclass(frozen=True)
class GroupSummary:
    group: str
    observations: int
    dates: int
    mean_rank_ic: float


@dataclass(frozen=True)
class CorrelationSummary:
    factor_id: str
    dates: int
    mean_rank_correlation: float


@dataclass(frozen=True)
class AlphaCard:
    lineage: EvaluationLineage
    primary_horizon: str
    horizon_metrics: tuple[MetricSummary, ...]
    subperiods: tuple[GroupSummary, ...]
    regimes: tuple[GroupSummary, ...]
    turnover: float
    correlations: tuple[CorrelationSummary, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @staticmethod
    def _format(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.6f}"

    def to_markdown(self) -> str:
        lines = [
            f"# Alpha Card: {self.lineage.factor_id}@{self.lineage.factor_version}",
            "",
            "## Lineage",
            "",
            f"- Snapshot: `{self.lineage.snapshot_id}`",
            f"- Experiment: `{self.lineage.experiment_id}`",
            f"- Trial: `{self.lineage.trial_id}`",
            f"- Code: `{self.lineage.code_version}`",
            f"- Primary horizon: `{self.primary_horizon}`",
            "",
            "## Horizon metrics",
            "",
            "| Horizon | Obs | Dates | IC | RankIC | ICIR | RankICIR | IC hit | RankIC hit |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for metric in self.horizon_metrics:
            lines.append(
                "| "
                f"{metric.horizon} | {metric.observations} | {metric.dates} | "
                f"{metric.mean_ic:.6f} | {metric.mean_rank_ic:.6f} | "
                f"{self._format(metric.icir)} | {self._format(metric.rank_icir)} | "
                f"{metric.ic_hit_rate:.2%} | {metric.rank_ic_hit_rate:.2%} |"
            )

        lines.extend(["", "## Stability", "", "### Subperiods", ""])
        lines.extend(
            f"- {item.group}: RankIC {item.mean_rank_ic:.6f} "
            f"({item.dates} dates, {item.observations} observations)"
            for item in self.subperiods
        )
        lines.extend(["", "### Regimes", ""])
        lines.extend(
            f"- {item.group}: RankIC {item.mean_rank_ic:.6f} "
            f"({item.dates} dates, {item.observations} observations)"
            for item in self.regimes
        )
        lines.extend(["", "## Diagnostics", "", f"- Rank turnover: {self.turnover:.6f}"])
        if self.correlations:
            lines.append("- Existing-factor rank correlations:")
            lines.extend(
                f"  - {item.factor_id}: {item.mean_rank_correlation:.6f} ({item.dates} dates)"
                for item in self.correlations
            )
        else:
            lines.append("- Existing-factor rank correlations: none supplied")
        return "\n".join(lines) + "\n"


class EvaluationError(ValueError):
    """Raised when evaluation evidence is invalid or insufficient."""
