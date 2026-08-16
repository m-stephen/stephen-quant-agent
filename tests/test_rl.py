from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.rl import (
    LinearGaussianActorCritic,
    PortfolioEnvironment,
    PPOConfig,
    RewardConfig,
    RLError,
    RLLineage,
    RLObservation,
    clipped_surrogate,
    evaluate_policy,
    fit_state_normalizer,
    generalized_advantage_estimate,
    softmax,
    train_ppo,
    write_ppo_report,
)


def _observations(start: date, periods: int, *, feature_scale: float = 1.0):
    rows: list[RLObservation] = []
    for index in range(periods):
        state_date = start + timedelta(days=index * 7)
        execution_date = state_date + timedelta(days=1)
        positive = index % 2 == 0
        feature = feature_scale if positive else -feature_scale
        returns = (0.03, -0.01) if positive else (-0.01, 0.03)
        rows.append(
            RLObservation(
                timestamp=f"{state_date.isoformat()}T15:00:00+08:00",
                state_available_at=f"{state_date.isoformat()}T15:01:00+08:00",
                execution_at=f"{execution_date.isoformat()}T09:30:00+08:00",
                return_end_at=(
                    f"{(execution_date + timedelta(days=5)).isoformat()}T15:00:00+08:00"
                ),
                features=(feature,),
                asset_returns=returns,
            )
        )
    return rows


def _datasets():
    train = _observations(date(2020, 1, 2), 40)
    validation = _observations(date(2021, 1, 7), 20)
    return train, validation


def _lineage(train, validation) -> RLLineage:
    return RLLineage(
        snapshot_id="snap_fixture",
        experiment_id="exp_fixture",
        trial_id="trial_fixture",
        code_version="test-sha",
        train_start_at=train[0].execution_at,
        train_end_at=train[-1].return_end_at,
        validation_start_at=validation[0].execution_at,
        validation_end_at=validation[-1].return_end_at,
    )


def _ppo_config() -> PPOConfig:
    return PPOConfig(
        episodes=80,
        update_epochs=4,
        actor_learning_rate=0.03,
        critic_learning_rate=0.04,
        entropy_coefficient=0.0,
        initial_log_std=-0.7,
    )


def test_softmax_actions_are_long_only_and_include_cash() -> None:
    weights = softmax((2.0, -1.0, 0.5))
    assert len(weights) == 3
    assert all(weight >= 0 for weight in weights)
    assert sum(weights) == pytest.approx(1.0)


def test_gae_respects_terminal_boundaries() -> None:
    advantages, returns = generalized_advantage_estimate(
        rewards=(1.0, 1.0, 5.0),
        values=(0.0, 0.0, 0.0),
        dones=(False, True, True),
        gamma=1.0,
        gae_lambda=1.0,
    )
    assert advantages == pytest.approx((2.0, 1.0, 5.0))
    assert returns == pytest.approx(advantages)


def test_clipped_surrogate_handles_positive_and_negative_advantages() -> None:
    assert clipped_surrogate(1.5, 2.0, 0.2) == pytest.approx(2.4)
    assert clipped_surrogate(1.5, -2.0, 0.2) == pytest.approx(-3.0)
    assert clipped_surrogate(0.5, -2.0, 0.2) == pytest.approx(-1.6)


def test_environment_rewards_are_net_of_cost_and_zero_trade_costs_zero() -> None:
    rows = _observations(date(2025, 1, 2), 2)
    rows = [RLObservation(**{**row.__dict__, "asset_returns": (0.0, 0.0)}) for row in rows]
    environment = PortfolioEnvironment(
        rows,
        ("A", "B"),
        RewardConfig(commission_bps=5.0, slippage_bps=5.0),
    )
    first = environment.step((0.5, 0.5, 0.0))
    second = environment.step((0.5, 0.5, 0.0))

    assert first.gross_return == 0.0
    assert first.cost == pytest.approx(0.001)
    assert first.net_return == pytest.approx(-0.001)
    assert second.turnover == 0.0
    assert second.cost == 0.0


def test_future_state_and_overlapping_returns_are_rejected() -> None:
    rows = _observations(date(2025, 1, 2), 2)
    rows[0] = RLObservation(
        **{**rows[0].__dict__, "state_available_at": rows[0].execution_at}
    )
    with pytest.raises(RLError, match="not available"):
        PortfolioEnvironment(rows, ("A", "B"), RewardConfig())

    rows = _observations(date(2025, 1, 2), 2)
    rows[0] = RLObservation(
        **{**rows[0].__dict__, "return_end_at": "2025-02-01T15:00:00+08:00"}
    )
    with pytest.raises(RLError, match="cannot overlap"):
        PortfolioEnvironment(rows, ("A", "B"), RewardConfig())


def test_training_is_deterministic_frozen_and_improves_synthetic_validation() -> None:
    train, validation = _datasets()
    arguments = (
        train,
        validation,
        ("A", "B"),
        _lineage(train, validation),
        RewardConfig(commission_bps=1.0, slippage_bps=1.0),
        _ppo_config(),
    )
    first = train_ppo(*arguments, seed=42)
    second = train_ppo(*arguments, seed=42)

    assert first.to_json() == second.to_json()
    assert first.policy_sha256 == second.policy_sha256
    assert first.normalizer.means == pytest.approx((0.0,))
    assert first.normalizer.scales == pytest.approx((1.0,))
    assert first.normalizer.observations == len(train)
    assert (
        first.final_validation.net_total_return
        > first.initial_validation.net_total_return
    )
    assert all(
        weight >= 0 and sum(step.weights) == pytest.approx(1.0)
        for step in first.final_validation.steps
        for weight in step.weights
    )


def test_validation_does_not_update_policy_or_normalizer() -> None:
    train, validation = _datasets()
    normalizer = fit_state_normalizer(train)
    policy = LinearGaussianActorCritic(1, 3, initial_log_std=-0.7)
    before = policy.snapshot()
    summary = evaluate_policy(
        policy, validation, ("A", "B"), normalizer, RewardConfig()
    )

    assert summary.observations == len(validation)
    assert policy.snapshot() == before
    assert normalizer == fit_state_normalizer(train)


def test_training_validation_overlap_and_false_lineage_are_rejected() -> None:
    train, _ = _datasets()
    overlapping = _observations(date(2020, 8, 1), 5)
    lineage = _lineage(train, overlapping)
    with pytest.raises(RLError, match="overlap"):
        train_ppo(
            train,
            overlapping,
            ("A", "B"),
            lineage,
            RewardConfig(),
            PPOConfig(episodes=1),
            seed=1,
        )

    _, validation = _datasets()
    bad_lineage = RLLineage(
        **{
            **_lineage(train, validation).__dict__,
            "train_start_at": "1999-01-01T00:00:00+00:00",
        }
    )
    with pytest.raises(RLError, match="do not match"):
        train_ppo(
            train,
            validation,
            ("A", "B"),
            bad_lineage,
            RewardConfig(),
            PPOConfig(episodes=1),
            seed=1,
        )


def test_report_artifacts_are_deterministic_and_complete(tmp_path: Path) -> None:
    train, validation = _datasets()
    report = train_ppo(
        train,
        validation,
        ("A", "B"),
        _lineage(train, validation),
        RewardConfig(commission_bps=1.0, slippage_bps=1.0),
        PPOConfig(
            episodes=5,
            update_epochs=2,
            actor_learning_rate=0.02,
            entropy_coefficient=0.0,
        ),
        seed=7,
    )
    first = write_ppo_report(report, tmp_path / "first")
    second = write_ppo_report(report, tmp_path / "second")
    payload = json.loads(first.json_path.read_text(encoding="utf-8"))

    assert first.json_sha256 == second.json_sha256
    assert first.markdown_sha256 == second.markdown_sha256
    assert payload["lineage"]["snapshot_id"] == "snap_fixture"
    assert payload["seed"] == 7
    assert payload["policy_sha256"] == report.policy.sha256
    assert payload["normalizer"]["observations"] == len(train)
