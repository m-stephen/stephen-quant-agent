from __future__ import annotations

import pytest

from stephen_quant.discovery.portfolio_objective import (
    PairwiseDependence,
    PortfolioCandidateEvidence,
    PortfolioObjectiveConfig,
    select_portfolio_candidates,
)
from stephen_quant.workflows.v60_portfolio_aware import run_v60_portfolio_aware


def _candidate(index: int, **overrides) -> PortfolioCandidateEvidence:
    values = {
        "proposal_id": f"p{index}",
        "semantic_identity": f"{index:064x}",
        "net_sharpe": 0.5,
        "double_cost_sharpe": 0.2,
        "marginal_information_ratio": 0.2,
        "positive_path_fraction": 0.75,
        "annual_turnover": 8.0,
        "capacity_cny": 10_000_000.0,
        "maximum_drawdown": -0.15,
    }
    values.update(overrides)
    return PortfolioCandidateEvidence(**values)


def _pairs(values: dict[tuple[str, str], float]) -> tuple[PairwiseDependence, ...]:
    return tuple(PairwiseDependence(left, right, value) for (left, right), value in values.items())


def test_v60_prefers_complementary_factor_over_redundant_high_sharpe() -> None:
    candidates = (
        _candidate(1, net_sharpe=1.0, marginal_information_ratio=0.5),
        _candidate(2, net_sharpe=1.2, marginal_information_ratio=0.4),
        _candidate(3, net_sharpe=0.5, marginal_information_ratio=0.35),
    )
    pairs = _pairs({("p1", "p2"): 0.95, ("p1", "p3"): 0.1, ("p2", "p3"): 0.1})
    report = select_portfolio_candidates(
        candidates, pairs, config=PortfolioObjectiveConfig(maximum_factors=2)
    )
    assert report.selected_proposal_ids == ("p1", "p3")
    assert next(item for item in report.scores if item.proposal_id == "p2").reason == "redundancy"


def test_v60_enforces_three_million_capacity() -> None:
    candidates = (_candidate(1, capacity_cny=2_000_000), _candidate(2))
    report = select_portfolio_candidates(candidates, _pairs({("p1", "p2"): 0.0}))
    assert next(item for item in report.scores if item.proposal_id == "p1").reason == "capacity"


def test_v60_weights_sum_to_one() -> None:
    candidates = (_candidate(1), _candidate(2))
    report = select_portfolio_candidates(candidates, _pairs({("p1", "p2"): 0.1}))
    assert report.total_weight == pytest.approx(1.0)
    assert report.inferential_trial_delta == 0


def test_v60_requires_complete_dependence_matrix() -> None:
    with pytest.raises(ValueError, match="complete"):
        select_portfolio_candidates((_candidate(1), _candidate(2), _candidate(3)), ())


def test_v60_rejects_final_test_evidence() -> None:
    with pytest.raises(ValueError, match="research-only"):
        select_portfolio_candidates((_candidate(1, evidence_scope="final_test"),), ())


def test_v60_planning_report_is_deterministic_and_trial_free(tmp_path) -> None:
    first = run_v60_portfolio_aware(tmp_path / "first")
    second = run_v60_portfolio_aware(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_PORTFOLIO_EVIDENCE"
    assert first.config.minimum_capacity_cny == 3_000_000
    assert not first.validation_or_test_metrics_used
    assert first.inferential_trial_delta == 0
