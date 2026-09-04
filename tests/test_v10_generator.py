from __future__ import annotations

import pytest

from stephen_quant.discovery.v10_generator import (
    generate_v10_candidates,
    validate_candidate_availability,
)


def test_v10_generator_is_bounded_cross_source_and_label_free() -> None:
    first = generate_v10_candidates(budget=80)
    second = generate_v10_candidates(budget=80)
    assert first == second
    assert len(first.candidates) == 80
    assert first.labels_read is False
    assert len(first.policy_sha256) == 64
    assert {field.source for item in first.candidates for field in item.fields} >= {
        "qd_daily",
        "minute_features",
        "qd_fund_flow",
        "qd_auction",
        "qd_chip",
    }
    assert any(len(item.fields) == 2 for item in first.candidates)
    full = generate_v10_candidates(budget=500)
    assert any(len(item.fields) == 3 for item in full.candidates)


def test_v10_generator_historical_dedup_and_budget() -> None:
    base = generate_v10_candidates(budget=5)
    prior = frozenset({base.candidates[0].candidate_id})
    next_packet = generate_v10_candidates(budget=5, historical_candidate_ids=prior)
    assert base.candidates[0].candidate_id not in {
        item.candidate_id for item in next_packet.candidates
    }
    assert any(item.startswith("HISTORICAL_DUPLICATE:") for item in next_packet.rejected)


def test_v10_generator_small_budget_is_semantically_balanced() -> None:
    packet = generate_v10_candidates(budget=24)
    strata = {(item.mechanism, item.operator) for item in packet.candidates}
    mechanisms = {item.mechanism for item in packet.candidates}
    assert len(strata) >= 12
    assert {
        "daily_intraday_multiscale_divergence",
        "flow_persistence_vs_intraday_absorption",
        "auction_price_discovery_vs_session_path",
        "crowding_reversal_with_intraday_liquidity",
        "flow_price_divergence",
        "flow_crowding_interaction",
    } <= mechanisms


def test_v10_generator_rejects_unavailable_execution_time() -> None:
    candidate = generate_v10_candidates(budget=1).candidates[0]
    validate_candidate_availability(candidate, "T+1_OPEN")
    with pytest.raises(ValueError, match="unavailable"):
        validate_candidate_availability(candidate, "T_OPEN")
