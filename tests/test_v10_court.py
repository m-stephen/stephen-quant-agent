from __future__ import annotations

from dataclasses import replace

from stephen_quant.discovery.alpha_court_v2 import (
    AlphaCourtEvidence,
    FrozenCourtProtocol,
)
from stephen_quant.discovery.v10_court import V10PathEvidence, adjudicate_v10_court


def _protocol() -> FrozenCourtProtocol:
    return FrozenCourtProtocol(
        candidate_semantic_identity="1" * 64,
        snapshot_sha256="2" * 64,
        code_commit_sha256="3" * 64,
        cost_model_sha256="4" * 64,
        cumulative_trial_count=700,
        sealed_start="2025-01-01",
        sealed_end="2026-08-16",
        frozen_at="2026-09-04T00:00:00+00:00",
    )


def _statistical(protocol: FrozenCourtProtocol) -> AlphaCourtEvidence:
    return AlphaCourtEvidence(
        protocol.protocol_id,
        protocol.candidate_semantic_identity,
        protocol.snapshot_sha256,
        protocol.sealed_start,
        protocol.sealed_end,
        0.99,
        0.01,
        0.01,
        0.01,
        1.0,
        0.5,
        18,
        24,
        0.4,
        5_000_000,
        0.0,
        0.0,
    )


def _path() -> V10PathEvidence:
    return V10PathEvidence(
        True,
        0,
        0,
        24,
        0.25,
        0.12,
        -0.20,
        0.30,
        0.01,
        (("2022", 0.10), ("2023", -0.02), ("2024", 0.12)),
        (("bull", 0.12), ("bear", 0.03), ("sideways", -0.01)),
    )


def test_v10_court_passes_only_complete_evidence() -> None:
    protocol = _protocol()
    result = adjudicate_v10_court(protocol, _statistical(protocol), _path())
    assert result.decision == "PASS"
    assert not result.path_failed_gates


def test_v10_court_fails_closed_without_cost_and_reconciliation() -> None:
    protocol = _protocol()
    path = replace(_path(), double_cost_total_return=-0.01, minute_daily_return_gap=0.08)
    result = adjudicate_v10_court(protocol, _statistical(protocol), path)
    assert result.decision == "NO_RELIABLE_ALPHA"
    assert {"double_cost_positive", "minute_daily_reconciliation"} <= set(result.path_failed_gates)
