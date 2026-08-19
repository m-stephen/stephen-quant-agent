from __future__ import annotations

from datetime import date, timedelta

import pytest

from stephen_quant.discovery.forward_shadow_v2 import (
    ForwardShadowObservation,
    ForwardShadowProtocol,
    append_forward_observation,
    replay_forward_ledger,
    summarize_forward_shadow,
)
from stephen_quant.workflows.v63_forward_shadow import run_v63_forward_shadow


def _protocol(**overrides) -> ForwardShadowProtocol:
    values = {
        "candidate_semantic_identity": "1" * 64,
        "frozen_through": "2026-08-16",
        "required_sources": ("qd_auction", "qd_daily", "qd_fund_flow"),
        "cost_model_sha256": "2" * 64,
        "portfolio_config_sha256": "3" * 64,
    }
    values.update(overrides)
    return ForwardShadowProtocol(**values)


def _observation(protocol: ForwardShadowProtocol, session: str, value: float = 0.001):
    return ForwardShadowObservation(
        protocol.protocol_id,
        session,
        tuple((source, f"{index:064x}") for index, source in enumerate(sorted(protocol.required_sources), 4)),
        value,
        value - 0.0002,
        f"{session}T16:00:00Z",
    )


def test_v63_requires_25_genuinely_new_sessions(tmp_path) -> None:
    protocol = _protocol()
    path = tmp_path / "forward.jsonl"
    start = date(2026, 8, 17)
    for offset in range(24):
        session = (start + timedelta(days=offset)).isoformat()
        append_forward_observation(path, protocol, _observation(protocol, session))
    waiting = summarize_forward_shadow(path, protocol)
    assert waiting.decision == "WAITING_FOR_FORWARD_DATA"
    assert waiting.standard_cumulative_excess is None
    session = (start + timedelta(days=24)).isoformat()
    append_forward_observation(path, protocol, _observation(protocol, session))
    ready = summarize_forward_shadow(path, protocol)
    assert ready.decision == "FORWARD_EVIDENCE_READY"
    assert ready.sessions == 25


def test_v63_rejects_frozen_or_duplicate_session(tmp_path) -> None:
    protocol = _protocol()
    path = tmp_path / "forward.jsonl"
    with pytest.raises(ValueError, match="strictly after"):
        append_forward_observation(path, protocol, _observation(protocol, "2026-08-16"))
    observation = _observation(protocol, "2026-08-17")
    append_forward_observation(path, protocol, observation)
    with pytest.raises(ValueError, match="duplicate or out of order"):
        append_forward_observation(path, protocol, observation)


def test_v63_requires_all_sources_and_protocol_binding(tmp_path) -> None:
    protocol = _protocol()
    observation = _observation(protocol, "2026-08-17")
    with pytest.raises(ValueError, match="every required source"):
        append_forward_observation(
            tmp_path / "forward.jsonl",
            protocol,
            ForwardShadowObservation(
                observation.protocol_id,
                observation.session,
                observation.source_snapshot_sha256[:-1],
                observation.standard_net_excess_return,
                observation.double_cost_net_excess_return,
                observation.available_at,
            ),
        )


def test_v63_tampering_breaks_replay(tmp_path) -> None:
    protocol = _protocol()
    path = tmp_path / "forward.jsonl"
    append_forward_observation(path, protocol, _observation(protocol, "2026-08-17"))
    path.write_text(path.read_text(encoding="utf-8").replace("0.001", "0.009"), encoding="utf-8")
    with pytest.raises(ValueError, match="entry hash mismatch"):
        replay_forward_ledger(path, protocol)


def test_v63_minimum_sessions_cannot_be_lowered() -> None:
    with pytest.raises(ValueError, match="at least 25"):
        _protocol(minimum_new_sessions=10).validate()


def test_v63_planning_report_is_deterministic_and_never_tunes(tmp_path) -> None:
    first = run_v63_forward_shadow(tmp_path / "first")
    second = run_v63_forward_shadow(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_FORWARD_PROTOCOL"
    assert first.minimum_new_common_sessions == 25
    assert not first.tuning_from_forward_window
    assert first.inferential_trial_delta == 0
