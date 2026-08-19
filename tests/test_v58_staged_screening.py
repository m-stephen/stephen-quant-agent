from __future__ import annotations

import pytest

from stephen_quant.discovery.staged_screening import (
    FunnelEvidence,
    StagedScreeningConfig,
    run_staged_screening,
)
from stephen_quant.workflows.v58_screening_funnel import run_v58_screening_funnel


def _evidence(index: int, **overrides) -> FunnelEvidence:
    values = {
        "proposal_id": f"proposal-{index}",
        "semantic_identity": f"{index:064x}",
        "coverage": 0.95,
        "missing_fraction": 0.05,
        "signal_variance": 0.1,
        "rank_turnover": 0.2,
        "training_rank_ic": 0.03,
        "positive_year_fraction": 0.75,
        "cpcv_rank_ic": 0.02,
        "positive_path_fraction": 0.75,
        "pbo": 0.05,
        "net_sharpe": 0.5,
        "double_cost_sharpe": 0.2,
    }
    values.update(overrides)
    return FunnelEvidence(**values)


def test_v58_funnel_enforces_monotone_budgets() -> None:
    evidence = tuple(_evidence(index) for index in range(20))
    config = StagedScreeningConfig(20, 12, 8, 4, 2)
    report = run_staged_screening(evidence, config=config)
    assert (report.input_candidates, report.data_quality_candidates) == (20, 12)
    assert (report.training_candidates, report.cpcv_candidates, report.execution_candidates) == (8, 4, 2)
    assert len(report.survivors) == 2
    assert report.inferential_trial_delta == 14


def test_v58_label_free_rejection_spends_no_trial() -> None:
    report = run_staged_screening((_evidence(1, coverage=0.1), _evidence(2)))
    rejected = next(item for item in report.decisions if item.proposal_id == "proposal-1")
    assert rejected.terminal_stage == "data_quality"
    assert rejected.trial_delta == 0


def test_v58_missing_labels_waits_without_trial() -> None:
    report = run_staged_screening(
        (_evidence(1, training_rank_ic=None, positive_year_fraction=None),)
    )
    assert report.decisions[0].decision == "WAITING_FOR_LABELS"
    assert report.inferential_trial_delta == 0


def test_v58_failures_account_for_trials_at_each_labeled_stage() -> None:
    report = run_staged_screening(
        (
            _evidence(1, training_rank_ic=-0.01),
            _evidence(2, pbo=0.8),
            _evidence(3, double_cost_sharpe=-1.0),
        )
    )
    assert {item.proposal_id: item.trial_delta for item in report.decisions} == {
        "proposal-1": 1,
        "proposal-2": 2,
        "proposal-3": 3,
    }
    assert report.inferential_trial_delta == 6


def test_v58_duplicate_semantics_fail_before_screening() -> None:
    with pytest.raises(ValueError, match="duplicate semantic"):
        run_staged_screening((_evidence(1), _evidence(2, semantic_identity=f"{1:064x}")))


def test_v58_invalid_budget_order_fails_closed() -> None:
    with pytest.raises(ValueError, match="non-increasing"):
        run_staged_screening((_evidence(1),), config=StagedScreeningConfig(10, 5, 6, 2, 1))


def test_v58_planning_run_is_deterministic_and_trial_free(tmp_path) -> None:
    first = run_v58_screening_funnel(tmp_path / "first")
    second = run_v58_screening_funnel(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_DATA_EVIDENCE"
    assert first.available_typed_proposals == 191
    assert first.inferential_trial_delta == 0
