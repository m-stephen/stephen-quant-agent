from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import pstdev

from .models import PolicySnapshot, PPOConfig, RLError

LOG_TWO_PI = math.log(2 * math.pi)


def softmax(logits: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in logits)
    if not values or any(not math.isfinite(value) for value in values):
        raise RLError("softmax logits must be finite and non-empty")
    maximum = max(values)
    exponentials = [math.exp(value - maximum) for value in values]
    total = sum(exponentials)
    return tuple(value / total for value in exponentials)


def gaussian_log_probability(
    latent: Sequence[float], means: Sequence[float], log_std: Sequence[float]
) -> float:
    if not (len(latent) == len(means) == len(log_std)):
        raise RLError("Gaussian policy dimensions do not match")
    return -0.5 * sum(
        ((value - mean) / math.exp(scale)) ** 2 + 2 * scale + LOG_TWO_PI
        for value, mean, scale in zip(latent, means, log_std, strict=True)
    )


def clipped_surrogate(ratio: float, advantage: float, epsilon: float) -> float:
    if ratio <= 0 or not math.isfinite(ratio):
        raise RLError("PPO probability ratio must be finite and positive")
    if not 0 < epsilon < 1:
        raise RLError("PPO clip epsilon must be between zero and one")
    clipped = min(max(ratio, 1 - epsilon), 1 + epsilon)
    return min(ratio * advantage, clipped * advantage)


def generalized_advantage_estimate(
    rewards: Sequence[float],
    values: Sequence[float],
    dones: Sequence[bool],
    *,
    gamma: float,
    gae_lambda: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    if not (len(rewards) == len(values) == len(dones)) or not rewards:
        raise RLError("GAE inputs must have equal non-zero length")
    if not 0 <= gamma <= 1 or not 0 <= gae_lambda <= 1:
        raise RLError("GAE gamma and lambda must be in [0, 1]")
    advantages = [0.0] * len(rewards)
    running = 0.0
    for index in range(len(rewards) - 1, -1, -1):
        terminal = 1.0 if dones[index] else 0.0
        next_value = 0.0 if index == len(rewards) - 1 else values[index + 1]
        delta = rewards[index] + gamma * next_value * (1 - terminal) - values[index]
        running = delta + gamma * gae_lambda * (1 - terminal) * running
        advantages[index] = running
    returns = tuple(advantage + value for advantage, value in zip(advantages, values, strict=True))
    return tuple(advantages), returns


def validate_ppo_config(config: PPOConfig) -> None:
    if config.episodes < 1 or config.update_epochs < 1:
        raise RLError("PPO episodes and update_epochs must be positive")
    if not 0 <= config.gamma <= 1 or not 0 <= config.gae_lambda <= 1:
        raise RLError("PPO gamma and GAE lambda must be in [0, 1]")
    if not 0 < config.clip_epsilon < 1:
        raise RLError("PPO clip_epsilon must be in (0, 1)")
    positive = (
        config.actor_learning_rate,
        config.critic_learning_rate,
        config.max_gradient_norm,
    )
    if any(not math.isfinite(value) or value <= 0 for value in positive):
        raise RLError("PPO learning rates and gradient norm must be finite and positive")
    if not math.isfinite(config.entropy_coefficient) or config.entropy_coefficient < 0:
        raise RLError("entropy_coefficient must be finite and non-negative")
    if not math.isfinite(config.initial_log_std) or not -10 <= config.initial_log_std <= 2:
        raise RLError("initial_log_std must be finite and between -10 and 2")


@dataclass(frozen=True)
class PolicyAction:
    latent: tuple[float, ...]
    weights: tuple[float, ...]
    log_probability: float
    value: float


@dataclass(frozen=True)
class Transition:
    state: tuple[float, ...]
    latent: tuple[float, ...]
    old_log_probability: float
    value: float
    reward: float
    done: bool


class LinearGaussianActorCritic:
    def __init__(
        self,
        state_dimension: int,
        action_dimension: int,
        *,
        initial_log_std: float,
    ) -> None:
        if state_dimension < 1 or action_dimension < 2:
            raise RLError("policy dimensions are invalid")
        self.state_dimension = state_dimension
        self.action_dimension = action_dimension
        self.actor_weights = [
            [0.0 for _ in range(state_dimension)] for _ in range(action_dimension)
        ]
        self.actor_bias = [0.0 for _ in range(action_dimension)]
        self.log_std = [float(initial_log_std) for _ in range(action_dimension)]
        self.critic_weights = [0.0 for _ in range(state_dimension)]
        self.critic_bias = 0.0

    def means(self, state: Sequence[float]) -> tuple[float, ...]:
        if len(state) != self.state_dimension:
            raise RLError("state dimension does not match policy")
        return tuple(
            sum(weight * value for weight, value in zip(row, state, strict=True)) + bias
            for row, bias in zip(self.actor_weights, self.actor_bias, strict=True)
        )

    def value(self, state: Sequence[float]) -> float:
        if len(state) != self.state_dimension:
            raise RLError("state dimension does not match critic")
        return sum(
            weight * value for weight, value in zip(self.critic_weights, state, strict=True)
        ) + self.critic_bias

    def act(
        self, state: Sequence[float], *, rng: random.Random | None, deterministic: bool
    ) -> PolicyAction:
        means = self.means(state)
        if deterministic:
            latent = means
        else:
            if rng is None:
                raise RLError("stochastic policy action requires an explicit RNG")
            latent = tuple(
                mean + math.exp(scale) * rng.gauss(0.0, 1.0)
                for mean, scale in zip(means, self.log_std, strict=True)
            )
        return PolicyAction(
            latent=tuple(latent),
            weights=softmax(latent),
            log_probability=gaussian_log_probability(latent, means, self.log_std),
            value=self.value(state),
        )

    def snapshot(self) -> PolicySnapshot:
        return PolicySnapshot(
            actor_weights=tuple(tuple(row) for row in self.actor_weights),
            actor_bias=tuple(self.actor_bias),
            log_std=tuple(self.log_std),
            critic_weights=tuple(self.critic_weights),
            critic_bias=self.critic_bias,
        )

    def update(
        self,
        transitions: Sequence[Transition],
        advantages: Sequence[float],
        returns: Sequence[float],
        config: PPOConfig,
    ) -> None:
        if not (len(transitions) == len(advantages) == len(returns)) or not transitions:
            raise RLError("PPO update inputs must have equal non-zero length")
        scale = pstdev(advantages)
        center = sum(advantages) / len(advantages)
        normalized = tuple(
            (advantage - center) / scale if scale > 1e-12 else advantage - center
            for advantage in advantages
        )
        for _ in range(config.update_epochs):
            actor_w_grad = [
                [0.0 for _ in range(self.state_dimension)]
                for _ in range(self.action_dimension)
            ]
            actor_b_grad = [0.0 for _ in range(self.action_dimension)]
            log_std_grad = [config.entropy_coefficient] * self.action_dimension
            critic_w_grad = [0.0 for _ in range(self.state_dimension)]
            critic_b_grad = 0.0
            count = len(transitions)
            for transition, advantage, target in zip(
                transitions, normalized, returns, strict=True
            ):
                means = self.means(transition.state)
                new_log_probability = gaussian_log_probability(
                    transition.latent, means, self.log_std
                )
                ratio = math.exp(max(min(new_log_probability - transition.old_log_probability, 20), -20))
                unclipped = ratio * advantage
                clipped = min(
                    max(ratio, 1 - config.clip_epsilon), 1 + config.clip_epsilon
                ) * advantage
                coefficient = advantage * ratio if unclipped <= clipped else 0.0
                for action_index in range(self.action_dimension):
                    difference = transition.latent[action_index] - means[action_index]
                    variance = math.exp(2 * self.log_std[action_index])
                    mean_gradient = coefficient * difference / variance
                    actor_b_grad[action_index] += mean_gradient / count
                    for state_index, state_value in enumerate(transition.state):
                        actor_w_grad[action_index][state_index] += (
                            mean_gradient * state_value / count
                        )
                    log_std_grad[action_index] += (
                        coefficient * (-1 + difference**2 / variance) / count
                    )
                error = self.value(transition.state) - target
                critic_b_grad += 2 * error / count
                for state_index, state_value in enumerate(transition.state):
                    critic_w_grad[state_index] += 2 * error * state_value / count

            actor_values = [
                value for row in actor_w_grad for value in row
            ] + actor_b_grad + log_std_grad
            actor_norm = math.sqrt(sum(value * value for value in actor_values))
            actor_scale = min(1.0, config.max_gradient_norm / max(actor_norm, 1e-12))
            critic_values = critic_w_grad + [critic_b_grad]
            critic_norm = math.sqrt(sum(value * value for value in critic_values))
            critic_scale = min(1.0, config.max_gradient_norm / max(critic_norm, 1e-12))
            for action_index in range(self.action_dimension):
                for state_index in range(self.state_dimension):
                    self.actor_weights[action_index][state_index] += (
                        config.actor_learning_rate
                        * actor_scale
                        * actor_w_grad[action_index][state_index]
                    )
                self.actor_bias[action_index] += (
                    config.actor_learning_rate * actor_scale * actor_b_grad[action_index]
                )
                self.log_std[action_index] += (
                    config.actor_learning_rate * actor_scale * log_std_grad[action_index]
                )
                self.log_std[action_index] = min(max(self.log_std[action_index], -4.0), 1.0)
            for state_index in range(self.state_dimension):
                self.critic_weights[state_index] -= (
                    config.critic_learning_rate
                    * critic_scale
                    * critic_w_grad[state_index]
                )
            self.critic_bias -= (
                config.critic_learning_rate * critic_scale * critic_b_grad
            )
