from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.discovery import AlphaCard, authorize_portfolio_signal


def _card() -> AlphaCard:
    return AlphaCard(
        protocol_version="signal-portfolio-gate-1.0.0",
        schema_id="price_momentum_20_5d",
        fingerprint="a" * 64,
        horizon="5d",
        snapshot_id="snap_a",
        experiment_id="exp_a",
        trial_id="trial_a",
        code_version="test",
        coverage=0.99,
        cpcv_mean_path_rank_ic=0.03,
        cpcv_positive_paths=10,
        cpcv_paths=10,
        turnover=4.0,
        net_total_return=0.10,
        annualized_net_sharpe=1.0,
        maximum_drawdown=-0.10,
        total_cost=100.0,
        capacity_clipped_notional=0.0,
        maximum_adv_participation=0.05,
        industry_exposure="not_measured",
        style_exposure="not_measured",
        alpha_court_passed=True,
        walk_forward_passed=True,
    )


def test_signal_portfolio_protocol_is_fail_closed() -> None:
    package = authorize_portfolio_signal(_card())
    assert package.alpha_card.fingerprint == "a" * 64
    assert "transaction_cost" in package.reward_fields

    with pytest.raises(ValueError, match="not authorized"):
        authorize_portfolio_signal(replace(_card(), alpha_court_passed=False))
    with pytest.raises(ValueError, match="not authorized"):
        authorize_portfolio_signal(replace(_card(), walk_forward_passed=False))
