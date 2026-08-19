from __future__ import annotations

import pytest

from stephen_quant.discovery.search_controller import (
    SearchArmState,
    SearchControllerConfig,
    choose_search_action,
)
from stephen_quant.workflows.v59_search_controller import run_v59_search_controller


def _arm(family: str, **overrides) -> SearchArmState:
    values = {
        "family": family,
        "attempts": 5,
        "training_passes": 1,
        "cpcv_passes": 0,
        "mean_research_score": 0.01,
        "expected_trial_cost": 1.5,
        "dominant_failure": "training_rank_ic",
        "consecutive_same_failure": 1,
    }
    values.update(overrides)
    return SearchArmState(**values)


def test_v59_prefers_untried_family_for_exploration() -> None:
    decision = choose_search_action(
        (_arm("old", attempts=20), _arm("new", attempts=0, training_passes=0)), spent_trials=20
    )
    assert decision.action == "EXPLORE"
    assert decision.family == "new"
    assert decision.controller_trial_delta == 0


def test_v59_repairs_repeated_failure_instead_of_blind_mutation() -> None:
    decision = choose_search_action(
        (_arm("margin", consecutive_same_failure=4, mean_research_score=1.0),), spent_trials=20
    )
    assert decision.action == "REPAIR"
    assert decision.reason == "repair_training_rank_ic"


def test_v59_stops_at_frozen_trial_reserve() -> None:
    config = SearchControllerConfig(total_trial_budget=100, reserve_trials=20)
    decision = choose_search_action((_arm("price"),), spent_trials=80, config=config)
    assert decision.action == "STOP"
    assert decision.maximum_incremental_trials == 0


def test_v59_sealed_evidence_is_rejected() -> None:
    with pytest.raises(ValueError, match="research-only"):
        choose_search_action((_arm("price", evidence_scope="final_test"),), spent_trials=0)


def test_v59_exhausted_families_stop() -> None:
    decision = choose_search_action(
        (_arm("price", consecutive_same_failure=9), _arm("flow", consecutive_same_failure=8)),
        spent_trials=0,
    )
    assert decision.action == "STOP"
    assert decision.reason == "all_families_exhausted"


def test_v59_batch_never_spends_reserve() -> None:
    config = SearchControllerConfig(total_trial_budget=100, reserve_trials=20, maximum_batch=50)
    decision = choose_search_action(
        (_arm("price", expected_trial_cost=3.0),), spent_trials=30, config=config
    )
    assert decision.maximum_incremental_trials <= 50
    assert decision.remaining_trials_before - decision.maximum_incremental_trials >= 20


def test_v59_planning_run_is_deterministic_and_trial_free(tmp_path) -> None:
    first = run_v59_search_controller(tmp_path / "first")
    second = run_v59_search_controller(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.status == "READY_FOR_PORTFOLIO_AWARE_SEARCH"
    assert first.decision.action == "EXPLORE"
    assert not first.validation_or_test_metrics_used
    assert first.inferential_trial_delta == 0
