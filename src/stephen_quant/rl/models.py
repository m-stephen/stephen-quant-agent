from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

METHOD_VERSION = "linear-gaussian-ppo-1.0.0"
REWARD_VERSION = "net-log-return-drawdown-turnover-1.0.0"


@dataclass(frozen=True)
class RLObservation:
    timestamp: str
    state_available_at: str
    execution_at: str
    return_end_at: str
    features: tuple[float, ...]
    asset_returns: tuple[float, ...]


@dataclass(frozen=True)
class RLLineage:
    snapshot_id: str
    experiment_id: str
    trial_id: str
    code_version: str
    train_start_at: str
    train_end_at: str
    validation_start_at: str
    validation_end_at: str


@dataclass(frozen=True)
class RewardConfig:
    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    turnover_penalty: float = 0.0
    drawdown_penalty: float = 0.0
    reward_version: str = REWARD_VERSION


@dataclass(frozen=True)
class PPOConfig:
    episodes: int = 50
    update_epochs: int = 4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    actor_learning_rate: float = 0.01
    critic_learning_rate: float = 0.03
    entropy_coefficient: float = 0.001
    initial_log_std: float = -0.7
    max_gradient_norm: float = 5.0


@dataclass(frozen=True)
class StateNormalizer:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    observations: int
    fitted_start_at: str
    fitted_end_at: str

    def transform(self, features: tuple[float, ...]) -> tuple[float, ...]:
        if len(features) != len(self.means):
            raise RLError("state dimension does not match the fitted normalizer")
        return tuple(
            (value - mean) / scale
            for value, mean, scale in zip(features, self.means, self.scales, strict=True)
        )


@dataclass(frozen=True)
class PolicySnapshot:
    actor_weights: tuple[tuple[float, ...], ...]
    actor_bias: tuple[float, ...]
    log_std: tuple[float, ...]
    critic_weights: tuple[float, ...]
    critic_bias: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()


@dataclass(frozen=True)
class AllocationStep:
    timestamp: str
    weights: tuple[float, ...]
    asset_weights: tuple[float, ...]
    cash_weight: float
    gross_return: float
    net_return: float
    turnover: float
    cost: float
    drawdown: float
    reward: float
    end_nav: float


@dataclass(frozen=True)
class EvaluationSummary:
    observations: int
    initial_nav: float
    final_nav: float
    net_total_return: float
    cumulative_reward: float
    total_turnover: float
    total_cost: float
    max_drawdown: float
    steps: tuple[AllocationStep, ...]


@dataclass(frozen=True)
class PPOTrainingReport:
    method_version: str
    lineage: RLLineage
    assets: tuple[str, ...]
    seed: int
    reward_config: RewardConfig
    ppo_config: PPOConfig
    normalizer: StateNormalizer
    initial_validation: EvaluationSummary
    final_validation: EvaluationSummary
    episode_rewards: tuple[float, ...]
    episode_final_navs: tuple[float, ...]
    policy: PolicySnapshot
    policy_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        initial = self.initial_validation
        final = self.final_validation
        lines = [
            "# PPO Long-only Allocation Report",
            "",
            "## Lineage",
            "",
            f"- Snapshot: `{self.lineage.snapshot_id}`",
            f"- Experiment: `{self.lineage.experiment_id}`",
            f"- Trial: `{self.lineage.trial_id}`",
            f"- Code: `{self.lineage.code_version}`",
            f"- Training: `{self.lineage.train_start_at}` to `{self.lineage.train_end_at}`",
            (
                f"- Validation: `{self.lineage.validation_start_at}` "
                f"to `{self.lineage.validation_end_at}`"
            ),
            f"- Seed: {self.seed}",
            f"- Method: `{self.method_version}`",
            f"- Reward: `{self.reward_config.reward_version}`",
            f"- Policy SHA-256: `{self.policy_sha256}`",
            "",
            "## Frozen validation",
            "",
            f"- Initial policy net return: {initial.net_total_return:.6%}",
            f"- Final policy net return: {final.net_total_return:.6%}",
            f"- Final NAV: {final.final_nav:.6f}",
            f"- Cumulative reward: {final.cumulative_reward:.6f}",
            f"- Total turnover: {final.total_turnover:.6f}",
            f"- Total cost: {final.total_cost:.6f}",
            f"- Maximum drawdown: {final.max_drawdown:.6%}",
            "",
            "Validation uses deterministic actions and does not update policy or normalization.",
        ]
        return "\n".join(lines) + "\n"


class RLError(ValueError):
    """Raised when RL data, actions, or training configuration violate integrity rules."""
