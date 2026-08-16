from __future__ import annotations

import math
import random
from collections.abc import Sequence
from datetime import datetime
from statistics import fmean, pstdev

from .environment import PortfolioEnvironment, validate_observations
from .models import (
    METHOD_VERSION,
    EvaluationSummary,
    PPOConfig,
    PPOTrainingReport,
    RewardConfig,
    RLError,
    RLLineage,
    RLObservation,
    StateNormalizer,
)
from .ppo import (
    LinearGaussianActorCritic,
    Transition,
    generalized_advantage_estimate,
    validate_ppo_config,
)


def fit_state_normalizer(observations: Sequence[RLObservation]) -> StateNormalizer:
    if not observations:
        raise RLError("normalizer requires training observations")
    ordered = tuple(sorted(observations, key=lambda row: _parse(row.execution_at)))
    dimension = len(ordered[0].features)
    if dimension < 1 or any(len(row.features) != dimension for row in ordered):
        raise RLError("normalizer requires a constant positive state dimension")
    columns = [tuple(row.features[index] for row in ordered) for index in range(dimension)]
    means = tuple(fmean(column) for column in columns)
    scales = tuple(
        dispersion if (dispersion := pstdev(column)) > 1e-12 else 1.0
        for column in columns
    )
    return StateNormalizer(
        means=means,
        scales=scales,
        observations=len(ordered),
        fitted_start_at=ordered[0].execution_at,
        fitted_end_at=ordered[-1].return_end_at,
    )


def _parse(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RLError(f"invalid ISO timestamp: {value}") from exc


def _validate_lineage(
    lineage: RLLineage,
    train: Sequence[RLObservation],
    validation: Sequence[RLObservation],
) -> None:
    if not all(
        (
            lineage.snapshot_id,
            lineage.experiment_id,
            lineage.trial_id,
            lineage.code_version,
            lineage.train_start_at,
            lineage.train_end_at,
            lineage.validation_start_at,
            lineage.validation_end_at,
        )
    ):
        raise RLError("RL lineage identifiers and boundaries cannot be empty")
    expected = (
        train[0].execution_at,
        train[-1].return_end_at,
        validation[0].execution_at,
        validation[-1].return_end_at,
    )
    declared = (
        lineage.train_start_at,
        lineage.train_end_at,
        lineage.validation_start_at,
        lineage.validation_end_at,
    )
    if declared != expected:
        raise RLError("RL lineage boundaries do not match the supplied datasets")
    if _parse(train[-1].return_end_at) > _parse(validation[0].execution_at):
        raise RLError("training and validation windows overlap")


def evaluate_policy(
    policy: LinearGaussianActorCritic,
    observations: Sequence[RLObservation],
    assets: Sequence[str],
    normalizer: StateNormalizer,
    reward_config: RewardConfig,
) -> EvaluationSummary:
    environment = PortfolioEnvironment(observations, assets, reward_config)
    steps = []
    environment.reset()
    for row in environment.observations:
        state = normalizer.transform(row.features)
        action = policy.act(state, rng=None, deterministic=True)
        steps.append(environment.step(action.weights))
    return EvaluationSummary(
        observations=len(steps),
        initial_nav=environment.initial_nav,
        final_nav=environment.nav,
        net_total_return=environment.nav / environment.initial_nav - 1,
        cumulative_reward=sum(step.reward for step in steps),
        total_turnover=sum(step.turnover for step in steps),
        total_cost=sum(step.cost for step in steps),
        max_drawdown=min((step.drawdown for step in steps), default=0.0),
        steps=tuple(steps),
    )


def train_ppo(
    train_observations: Sequence[RLObservation],
    validation_observations: Sequence[RLObservation],
    assets: Sequence[str],
    lineage: RLLineage,
    reward_config: RewardConfig,
    ppo_config: PPOConfig,
    *,
    seed: int,
) -> PPOTrainingReport:
    """Train only on the research window, then evaluate a frozen policy on validation."""

    validate_ppo_config(ppo_config)
    if not isinstance(seed, int):
        raise RLError("seed must be an integer")
    asset_tuple = tuple(assets)
    train = validate_observations(train_observations, len(asset_tuple))
    validation = validate_observations(validation_observations, len(asset_tuple))
    _validate_lineage(lineage, train, validation)
    normalizer = fit_state_normalizer(train)
    policy = LinearGaussianActorCritic(
        state_dimension=len(normalizer.means),
        action_dimension=len(asset_tuple) + 1,
        initial_log_std=ppo_config.initial_log_std,
    )
    initial_validation = evaluate_policy(
        policy, validation, asset_tuple, normalizer, reward_config
    )
    generator = random.Random(seed)
    episode_rewards: list[float] = []
    episode_final_navs: list[float] = []
    for _ in range(ppo_config.episodes):
        environment = PortfolioEnvironment(train, asset_tuple, reward_config)
        environment.reset()
        transitions: list[Transition] = []
        for index, row in enumerate(environment.observations):
            state = normalizer.transform(row.features)
            action = policy.act(state, rng=generator, deterministic=False)
            step = environment.step(action.weights)
            transitions.append(
                Transition(
                    state=state,
                    latent=action.latent,
                    old_log_probability=action.log_probability,
                    value=action.value,
                    reward=step.reward,
                    done=index == len(environment.observations) - 1,
                )
            )
        advantages, returns = generalized_advantage_estimate(
            [transition.reward for transition in transitions],
            [transition.value for transition in transitions],
            [transition.done for transition in transitions],
            gamma=ppo_config.gamma,
            gae_lambda=ppo_config.gae_lambda,
        )
        policy.update(transitions, advantages, returns, ppo_config)
        episode_rewards.append(sum(transition.reward for transition in transitions))
        episode_final_navs.append(environment.nav)

    final_validation = evaluate_policy(
        policy, validation, asset_tuple, normalizer, reward_config
    )
    snapshot = policy.snapshot()
    parameters = (
        tuple(value for row in snapshot.actor_weights for value in row)
        + snapshot.actor_bias
        + snapshot.log_std
        + snapshot.critic_weights
        + (snapshot.critic_bias,)
    )
    if any(not math.isfinite(value) for value in parameters):
        raise RLError("training produced non-finite policy parameters")
    return PPOTrainingReport(
        method_version=METHOD_VERSION,
        lineage=lineage,
        assets=asset_tuple,
        seed=seed,
        reward_config=reward_config,
        ppo_config=ppo_config,
        normalizer=normalizer,
        initial_validation=initial_validation,
        final_validation=final_validation,
        episode_rewards=tuple(episode_rewards),
        episode_final_navs=tuple(episode_final_navs),
        policy=snapshot,
        policy_sha256=snapshot.sha256,
    )
