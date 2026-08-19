from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime

AUTO_ALPHA_COURT_VERSION = "6.2.0"


def _canonical(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase SHA-256 value")


@dataclass(frozen=True)
class AlphaCourtThresholds:
    minimum_dsr: float = 0.95
    maximum_pbo: float = 0.05
    maximum_signal_placebo_p: float = 0.05
    maximum_return_placebo_p: float = 0.05
    minimum_positive_paths: int = 15
    minimum_total_paths: int = 20
    minimum_median_path_sharpe: float = 0.0
    minimum_standard_net_sharpe: float = 0.0
    minimum_double_cost_net_sharpe: float = -0.25
    minimum_capacity_cny: float = 3_000_000.0

    def validate(self) -> None:
        if self.minimum_dsr < 0.95:
            raise ValueError("Alpha Court DSR threshold cannot be weakened below 0.95")
        maxima = (
            self.maximum_pbo,
            self.maximum_signal_placebo_p,
            self.maximum_return_placebo_p,
        )
        if any(value > 0.05 or value < 0 for value in maxima):
            raise ValueError("Alpha Court PBO/placebo thresholds cannot exceed 0.05")
        if self.minimum_total_paths < 20 or self.minimum_positive_paths < 15:
            raise ValueError("Alpha Court path thresholds cannot be weakened")
        if self.minimum_positive_paths > self.minimum_total_paths:
            raise ValueError("positive paths cannot exceed total paths")
        if self.minimum_capacity_cny < 3_000_000:
            raise ValueError("Alpha Court capacity cannot be below CNY 3 million")


DEFAULT_ALPHA_COURT_THRESHOLDS = AlphaCourtThresholds()


@dataclass(frozen=True)
class FrozenCourtProtocol:
    candidate_semantic_identity: str
    snapshot_sha256: str
    code_commit_sha256: str
    cost_model_sha256: str
    cumulative_trial_count: int
    sealed_start: str
    sealed_end: str
    frozen_at: str
    thresholds: AlphaCourtThresholds = DEFAULT_ALPHA_COURT_THRESHOLDS

    def validate(self) -> None:
        for value, label in (
            (self.candidate_semantic_identity, "candidate identity"),
            (self.snapshot_sha256, "snapshot"),
            (self.code_commit_sha256, "code commit"),
            (self.cost_model_sha256, "cost model"),
        ):
            _sha(value, label)
        if self.cumulative_trial_count < 1:
            raise ValueError("Alpha Court requires the complete positive Trial count")
        if self.sealed_start > self.sealed_end:
            raise ValueError("sealed window is invalid")
        try:
            frozen = datetime.fromisoformat(self.frozen_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("frozen_at must be ISO-8601") from exc
        if frozen.tzinfo is None:
            raise ValueError("frozen_at must include timezone")
        self.thresholds.validate()

    @property
    def protocol_id(self) -> str:
        self.validate()
        return hashlib.sha256(_canonical(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class AlphaCourtEvidence:
    protocol_id: str
    candidate_semantic_identity: str
    snapshot_sha256: str
    evaluation_start: str
    evaluation_end: str
    dsr_probability: float
    pbo_probability: float
    signal_placebo_p: float
    return_placebo_p: float
    standard_net_sharpe: float
    double_cost_net_sharpe: float
    positive_paths: int
    total_paths: int
    median_path_sharpe: float
    capacity_cny: float
    skewness: float
    excess_kurtosis: float
    evidence_scope: str = "sealed_once"


@dataclass(frozen=True)
class AlphaCourtDecision:
    method_version: str
    protocol_id: str
    candidate_semantic_identity: str
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    decision: str
    inferential_trial_delta: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def adjudicate_alpha_court(
    protocol: FrozenCourtProtocol,
    evidence: AlphaCourtEvidence,
) -> AlphaCourtDecision:
    protocol.validate()
    thresholds = protocol.thresholds
    if evidence.protocol_id != protocol.protocol_id:
        raise ValueError("Alpha Court evidence is not bound to the frozen protocol")
    if evidence.candidate_semantic_identity != protocol.candidate_semantic_identity:
        raise ValueError("Alpha Court candidate identity mismatch")
    if evidence.snapshot_sha256 != protocol.snapshot_sha256:
        raise ValueError("Alpha Court snapshot mismatch")
    if (evidence.evaluation_start, evidence.evaluation_end) != (
        protocol.sealed_start,
        protocol.sealed_end,
    ):
        raise ValueError("Alpha Court evidence window differs from the sealed protocol")
    if evidence.evidence_scope != "sealed_once":
        raise ValueError("Alpha Court evidence must come from the one-time sealed scope")
    finite = (
        evidence.dsr_probability,
        evidence.pbo_probability,
        evidence.signal_placebo_p,
        evidence.return_placebo_p,
        evidence.standard_net_sharpe,
        evidence.double_cost_net_sharpe,
        evidence.median_path_sharpe,
        evidence.capacity_cny,
        evidence.skewness,
        evidence.excess_kurtosis,
    )
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in finite):
        raise ValueError("Alpha Court metrics must be finite")
    probabilities = (
        evidence.dsr_probability,
        evidence.pbo_probability,
        evidence.signal_placebo_p,
        evidence.return_placebo_p,
    )
    if any(not 0 <= value <= 1 for value in probabilities):
        raise ValueError("Alpha Court probabilities must be in [0, 1]")
    if evidence.positive_paths < 0 or evidence.total_paths < 0 or evidence.capacity_cny < 0:
        raise ValueError("Alpha Court path counts and capacity cannot be negative")
    gates = {
        "dsr": evidence.dsr_probability >= thresholds.minimum_dsr,
        "pbo": evidence.pbo_probability <= thresholds.maximum_pbo,
        "signal_placebo": evidence.signal_placebo_p <= thresholds.maximum_signal_placebo_p,
        "return_placebo": evidence.return_placebo_p <= thresholds.maximum_return_placebo_p,
        "standard_cost": evidence.standard_net_sharpe >= thresholds.minimum_standard_net_sharpe,
        "double_cost": evidence.double_cost_net_sharpe >= thresholds.minimum_double_cost_net_sharpe,
        "positive_paths": evidence.positive_paths >= thresholds.minimum_positive_paths,
        "total_paths": evidence.total_paths >= thresholds.minimum_total_paths,
        "median_path": evidence.median_path_sharpe >= thresholds.minimum_median_path_sharpe,
        "capacity": evidence.capacity_cny >= thresholds.minimum_capacity_cny,
        "path_consistency": 0 <= evidence.positive_paths <= evidence.total_paths,
    }
    passed = tuple(sorted(name for name, value in gates.items() if value))
    failed = tuple(sorted(name for name, value in gates.items() if not value))
    return AlphaCourtDecision(
        AUTO_ALPHA_COURT_VERSION,
        protocol.protocol_id,
        protocol.candidate_semantic_identity,
        passed,
        failed,
        "PASS" if not failed else "FAIL",
        0,
    )
