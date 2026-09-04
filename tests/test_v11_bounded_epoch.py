from __future__ import annotations

from types import SimpleNamespace

import pytest

from stephen_quant.workflows.v11_bounded_epoch import (
    _failed_gates,
    frozen_epoch_candidates,
    signal_portfolio_bridge,
)
from stephen_quant.workflows.v11_research_reset import (
    NullPlacebo,
    PboIdentifiability,
    UniverseRobustness,
)


def test_v11_epoch_is_exactly_twelve_unique_preregistered_candidates() -> None:
    candidates = frozen_epoch_candidates()
    assert len(candidates) == 12
    assert len({item.candidate_id for item in candidates}) == 12
    assert {item.primary_horizon for item in candidates} == {3, 5, 10, 20}
    assert {item.mechanism for item in candidates} == {
        "auction_open_absorption",
        "intraday_closing_structure",
        "fund_flow_price_mismatch",
        "chip_dynamic_crowding",
    }
    assert all(
        sum(item.negative_control for item in candidates if item.mechanism == mechanism) == 1
        for mechanism in {item.mechanism for item in candidates}
    )


def test_v11_candidate_identity_binds_horizon_and_direction() -> None:
    candidates = frozen_epoch_candidates()
    assert all(len(item.candidate_id) == 64 for item in candidates)
    assert any(item.expression.startswith("-(") for item in candidates)
    assert all(item.expression for item in candidates)


def test_v11_negative_control_can_never_pass() -> None:
    candidate = next(item for item in frozen_epoch_candidates() if item.negative_control)
    report = SimpleNamespace(
        net_excess_total_return=0.2,
        double_cost_total_return=0.1,
        capacity_passed=True,
        year_attribution=(SimpleNamespace(net_excess_return=0.1),),
        periods=(
            SimpleNamespace(benchmark_return=-0.1, net_excess_return=0.1),
            SimpleNamespace(benchmark_return=0.1, net_excess_return=0.1),
        ),
    )
    robustness = UniverseRobustness("v", 10, 0.1, 0.1, 0.1, 0.1, 0.1, 1.0, 1.0, 0.1)
    placebo = NullPlacebo("v", "IDENTIFIABLE", 0.01, "null", "unit", (), "link")
    identifiable = PboIdentifiability("IDENTIFIABLE", 3, 6, 2, "varies")
    failed = _failed_gates(
        candidate,
        report,
        robustness,
        placebo,
        placebo,
        placebo,
        0.99,
        identifiable,
        0.0,
    )
    assert failed == ("NEGATIVE_CONTROL_NOT_ELIGIBLE",)


def test_v11_bridge_discloses_friction_cost_capacity_and_effective_samples() -> None:
    report = SimpleNamespace(
        periods=(
            SimpleNamespace(
                holdings=("a", "b"),
                gross_excess_return=0.1,
                net_excess_return=0.08,
                benchmark_return=-0.01,
            ),
            SimpleNamespace(
                holdings=("a", "c"),
                gross_excess_return=-0.05,
                net_excess_return=-0.05,
                benchmark_return=0.01,
            ),
        ),
        net_excess_total_return=0.03,
        double_cost_total_return=0.01,
        total_turnover=1.2,
        capacity_cny=4_000_000,
        year_attribution=(SimpleNamespace(year="2022", net_excess_return=0.03),),
    )
    bridge = signal_portfolio_bridge(report)
    assert bridge.periods == 2
    assert bridge.non_overlapping_effective_samples == 2
    assert bridge.frictionless_excess_return == pytest.approx(0.045)
    assert bridge.standard_cost_excess_return == 0.03
    assert bridge.double_cost_excess_return == 0.01
