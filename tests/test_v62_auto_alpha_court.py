from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.discovery.alpha_court_v2 import (
    AlphaCourtEvidence,
    AlphaCourtThresholds,
    FrozenCourtProtocol,
    adjudicate_alpha_court,
)
from stephen_quant.workflows.v62_auto_alpha_court import run_v62_auto_alpha_court


def _protocol(**overrides) -> FrozenCourtProtocol:
    values = {
        "candidate_semantic_identity": "1" * 64,
        "snapshot_sha256": "2" * 64,
        "code_commit_sha256": "3" * 64,
        "cost_model_sha256": "4" * 64,
        "cumulative_trial_count": 1500,
        "sealed_start": "2027-01-01",
        "sealed_end": "2027-06-30",
        "frozen_at": "2026-12-31T00:00:00Z",
    }
    values.update(overrides)
    return FrozenCourtProtocol(**values)


def _evidence(protocol: FrozenCourtProtocol, **overrides) -> AlphaCourtEvidence:
    values = {
        "protocol_id": protocol.protocol_id,
        "candidate_semantic_identity": protocol.candidate_semantic_identity,
        "snapshot_sha256": protocol.snapshot_sha256,
        "evaluation_start": protocol.sealed_start,
        "evaluation_end": protocol.sealed_end,
        "dsr_probability": 0.98,
        "pbo_probability": 0.02,
        "signal_placebo_p": 0.01,
        "return_placebo_p": 0.02,
        "standard_net_sharpe": 0.8,
        "double_cost_net_sharpe": 0.3,
        "positive_paths": 18,
        "total_paths": 20,
        "median_path_sharpe": 0.3,
        "capacity_cny": 10_000_000,
        "skewness": 0.1,
        "excess_kurtosis": 1.0,
    }
    values.update(overrides)
    return AlphaCourtEvidence(**values)


def test_v62_pass_requires_every_frozen_gate() -> None:
    protocol = _protocol()
    decision = adjudicate_alpha_court(protocol, _evidence(protocol))
    assert decision.decision == "PASS"
    assert not decision.failed_gates
    assert decision.inferential_trial_delta == 0


def test_v62_any_failed_gate_fails_entire_court() -> None:
    protocol = _protocol()
    decision = adjudicate_alpha_court(
        protocol, _evidence(protocol, dsr_probability=0.94, double_cost_net_sharpe=-0.5)
    )
    assert decision.decision == "FAIL"
    assert set(decision.failed_gates) == {"double_cost", "dsr"}


def test_v62_thresholds_cannot_be_weakened() -> None:
    with pytest.raises(ValueError, match="DSR"):
        _protocol(thresholds=AlphaCourtThresholds(minimum_dsr=0.90)).validate()
    with pytest.raises(ValueError, match="0.05"):
        _protocol(thresholds=AlphaCourtThresholds(maximum_pbo=0.10)).validate()


def test_v62_evidence_must_match_frozen_protocol() -> None:
    protocol = _protocol()
    with pytest.raises(ValueError, match="not bound"):
        adjudicate_alpha_court(protocol, replace(_evidence(protocol), protocol_id="f" * 64))


def test_v62_final_or_research_scope_cannot_replace_sealed_once() -> None:
    protocol = _protocol()
    with pytest.raises(ValueError, match="one-time sealed"):
        adjudicate_alpha_court(protocol, _evidence(protocol, evidence_scope="research_only"))


def test_v62_protocol_id_changes_with_trial_count() -> None:
    protocol = _protocol()
    assert protocol.protocol_id != replace(protocol, cumulative_trial_count=1501).protocol_id


def test_v62_planning_report_is_deterministic_and_does_not_claim_pass(tmp_path) -> None:
    first = run_v62_auto_alpha_court(tmp_path / "first")
    second = run_v62_auto_alpha_court(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_FROZEN_PROTOCOL"
    assert first.adjudication is None
    assert first.inferential_trial_delta == 0
