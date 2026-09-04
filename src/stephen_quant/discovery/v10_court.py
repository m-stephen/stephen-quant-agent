from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from .alpha_court_v2 import (
    AlphaCourtDecision,
    AlphaCourtEvidence,
    FrozenCourtProtocol,
    adjudicate_alpha_court,
)

V10_COURT_VERSION = "10.0.0"


@dataclass(frozen=True)
class V10PathEvidence:
    cpcv_audited: bool
    purge_overlap_count: int
    embargo_overlap_count: int
    walk_forward_periods: int
    standard_cost_total_return: float
    double_cost_total_return: float
    maximum_drawdown: float
    return_concentration: float
    minute_daily_return_gap: float
    annual_returns: tuple[tuple[str, float], ...]
    regime_returns: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class V10CourtDecision:
    method_version: str
    statistical_decision: AlphaCourtDecision
    path_passed_gates: tuple[str, ...]
    path_failed_gates: tuple[str, ...]
    decision: str
    evidence_sha256: str


def adjudicate_v10_court(
    protocol: FrozenCourtProtocol,
    statistical: AlphaCourtEvidence,
    path: V10PathEvidence,
) -> V10CourtDecision:
    numeric = (
        path.standard_cost_total_return,
        path.double_cost_total_return,
        path.maximum_drawdown,
        path.return_concentration,
        path.minute_daily_return_gap,
        *(value for _, value in path.annual_returns),
        *(value for _, value in path.regime_returns),
    )
    if any(not math.isfinite(value) for value in numeric):
        raise ValueError("V10 path evidence must be finite")
    if len(path.annual_returns) < 3 or len(path.regime_returns) < 3:
        raise ValueError("V10 requires at least three years and three market regimes")
    statistical_decision = adjudicate_alpha_court(protocol, statistical)
    gates = {
        "cpcv_audited": path.cpcv_audited,
        "purge_clean": path.purge_overlap_count == 0,
        "embargo_clean": path.embargo_overlap_count == 0,
        "walk_forward": path.walk_forward_periods >= 12,
        "standard_cost_positive": path.standard_cost_total_return > 0,
        "double_cost_positive": path.double_cost_total_return > 0,
        "maximum_drawdown": path.maximum_drawdown >= -0.35,
        "return_concentration": 0 <= path.return_concentration <= 0.50,
        "minute_daily_reconciliation": abs(path.minute_daily_return_gap) <= 0.05,
        "annual_breadth": sum(value > 0 for _, value in path.annual_returns) >= 2,
        "regime_breadth": sum(value > 0 for _, value in path.regime_returns) >= 2,
    }
    passed = tuple(sorted(name for name, value in gates.items() if value))
    failed = tuple(sorted(name for name, value in gates.items() if not value))
    evidence_hash = hashlib.sha256(
        json.dumps(
            {"protocol_id": protocol.protocol_id, "statistical": asdict(statistical), "path": asdict(path)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    decision = "PASS" if statistical_decision.decision == "PASS" and not failed else "NO_RELIABLE_ALPHA"
    return V10CourtDecision(V10_COURT_VERSION, statistical_decision, passed, failed, decision, evidence_hash)
