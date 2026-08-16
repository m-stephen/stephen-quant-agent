from __future__ import annotations

import json
from dataclasses import asdict, dataclass

METHOD_VERSION = "alpha-court-1.0.0"


@dataclass(frozen=True)
class FalsificationLineage:
    factor_id: str
    factor_version: str
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str


@dataclass(frozen=True)
class PlaceboResult:
    method: str
    method_version: str
    seed: int
    repetitions: int
    observed_mean_rank_ic: float
    placebo_mean_rank_ics: tuple[float, ...]
    empirical_p_value: float


@dataclass(frozen=True)
class DeflatedSharpeResult:
    method_version: str
    observed_sharpe: float
    benchmark_sharpe: float
    probability: float
    observations: int
    recorded_trial_count: int
    sharpe_estimates_used: int
    sharpe_estimate_std: float
    skewness: float
    excess_kurtosis: float


@dataclass(frozen=True)
class PBOResult:
    method_version: str
    probability: float
    logits: tuple[float, ...]
    combinations: int
    paths: int
    configurations: int
    split_manifest_sha256: str


@dataclass(frozen=True)
class AuditThresholds:
    max_placebo_p_value: float = 0.05
    min_dsr_probability: float = 0.95
    max_pbo: float = 0.05


@dataclass(frozen=True)
class AuditDecision:
    passed: bool
    checks: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class AlphaCourtReport:
    method_version: str
    lineage: FalsificationLineage
    recorded_trial_count: int
    seeds: tuple[int, ...]
    thresholds: AuditThresholds
    signal_placebo: PlaceboResult
    return_placebo: PlaceboResult
    deflated_sharpe: DeflatedSharpeResult
    pbo: PBOResult
    decision: AuditDecision

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        status = "PASS" if self.decision.passed else "REJECT"
        lines = [
            f"# Alpha Court: {self.lineage.factor_id}@{self.lineage.factor_version}",
            "",
            f"**Decision: {status}**",
            "",
            "## Research lineage",
            "",
            f"- Snapshot: `{self.lineage.snapshot_id}`",
            f"- Experiment: `{self.lineage.experiment_id}`",
            f"- Trial: `{self.lineage.trial_id}`",
            f"- Code: `{self.lineage.code_version}`",
            f"- Recorded trials: {self.recorded_trial_count}",
            f"- Seeds: {', '.join(str(seed) for seed in self.seeds)}",
            f"- Method: `{self.method_version}`",
            "",
            "## Evidence",
            "",
            f"- Signal-shuffle p-value: {self.signal_placebo.empirical_p_value:.6f}",
            f"- Return-permutation p-value: {self.return_placebo.empirical_p_value:.6f}",
            f"- Deflated Sharpe probability: {self.deflated_sharpe.probability:.6f}",
            f"- PBO: {self.pbo.probability:.6f}",
            f"- CPCV manifest: `{self.pbo.split_manifest_sha256}`",
            "",
            "## Checks",
            "",
        ]
        lines.extend(f"- {'PASS' if passed else 'FAIL'} — {name}" for name, passed in self.decision.checks)
        return "\n".join(lines) + "\n"


class FalsificationError(ValueError):
    """Raised when falsification evidence is incomplete or invalid."""
