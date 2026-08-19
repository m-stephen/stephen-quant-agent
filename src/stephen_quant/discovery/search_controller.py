from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from typing import Literal

SEARCH_CONTROLLER_VERSION = "5.9.0"
SearchAction = Literal["EXPLORE", "MUTATE", "REPAIR", "STOP"]


@dataclass(frozen=True)
class SearchArmState:
    family: str
    attempts: int
    training_passes: int
    cpcv_passes: int
    mean_research_score: float
    expected_trial_cost: float
    dominant_failure: str | None
    consecutive_same_failure: int
    evidence_scope: str = "research_only"

    def validate(self) -> None:
        if not self.family or self.attempts < 0:
            raise ValueError("search arm requires a family and non-negative attempts")
        if not 0 <= self.cpcv_passes <= self.training_passes <= self.attempts:
            raise ValueError("search arm pass counts must be nested")
        if not math.isfinite(self.mean_research_score) or self.expected_trial_cost <= 0:
            raise ValueError("search arm scores and costs must be finite and positive")
        if self.consecutive_same_failure < 0:
            raise ValueError("consecutive failure count cannot be negative")
        if self.evidence_scope != "research_only":
            raise ValueError("search controller accepts research-only evidence")


@dataclass(frozen=True)
class SearchControllerConfig:
    total_trial_budget: int = 256
    reserve_trials: int = 32
    maximum_batch: int = 16
    exploration_weight: float = 0.35
    failure_penalty: float = 0.10
    repair_after_failures: int = 3
    stop_after_failures: int = 8

    def validate(self) -> None:
        if not 0 <= self.reserve_trials < self.total_trial_budget:
            raise ValueError("trial reserve must be below total budget")
        if self.maximum_batch < 1 or self.exploration_weight < 0 or self.failure_penalty < 0:
            raise ValueError("invalid search-controller tuning")
        if not 1 <= self.repair_after_failures < self.stop_after_failures:
            raise ValueError("failure thresholds must be positive and ordered")


DEFAULT_SEARCH_CONTROLLER_CONFIG = SearchControllerConfig()


@dataclass(frozen=True)
class SearchDecision:
    action: SearchAction
    family: str | None
    batch_size: int
    score: float | None
    remaining_trials_before: int
    maximum_incremental_trials: int
    reason: str
    controller_trial_delta: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _arm_score(arm: SearchArmState, total_attempts: int, config: SearchControllerConfig) -> float:
    exploitation = arm.mean_research_score
    conversion = (arm.training_passes + 2 * arm.cpcv_passes) / max(arm.attempts, 1)
    exploration = config.exploration_weight * math.sqrt(
        math.log(total_attempts + 2) / (arm.attempts + 1)
    )
    repeated = config.failure_penalty * arm.consecutive_same_failure
    cost = 0.02 * arm.expected_trial_cost
    return exploitation + conversion + exploration - repeated - cost


def choose_search_action(
    arms: tuple[SearchArmState, ...],
    *,
    spent_trials: int,
    config: SearchControllerConfig = DEFAULT_SEARCH_CONTROLLER_CONFIG,
) -> SearchDecision:
    config.validate()
    if spent_trials < 0 or spent_trials > config.total_trial_budget:
        raise ValueError("spent trials are outside the frozen budget")
    if not arms:
        raise ValueError("search controller requires at least one arm")
    for arm in arms:
        arm.validate()
    if len({arm.family for arm in arms}) != len(arms):
        raise ValueError("search arms must have unique families")
    remaining = config.total_trial_budget - spent_trials
    usable = remaining - config.reserve_trials
    if usable <= 0:
        return SearchDecision("STOP", None, 0, None, remaining, 0, "trial_reserve_reached")
    viable = [arm for arm in arms if arm.consecutive_same_failure < config.stop_after_failures]
    if not viable:
        return SearchDecision("STOP", None, 0, None, remaining, 0, "all_families_exhausted")
    total_attempts = sum(arm.attempts for arm in arms)
    ranked = sorted(
        ((_arm_score(arm, total_attempts, config), arm) for arm in viable),
        key=lambda item: (-item[0], item[1].family),
    )
    score, selected = ranked[0]
    affordable = int(usable // selected.expected_trial_cost)
    if affordable < 1:
        return SearchDecision("STOP", None, 0, None, remaining, 0, "insufficient_trial_budget")
    batch = min(config.maximum_batch, affordable)
    if selected.attempts == 0:
        action, reason = "EXPLORE", "untried_semantic_family"
    elif selected.consecutive_same_failure >= config.repair_after_failures:
        action, reason = "REPAIR", f"repair_{selected.dominant_failure or 'repeated_failure'}"
    else:
        action, reason = "MUTATE", "best_research_only_expected_improvement"
    return SearchDecision(
        action,
        selected.family,
        batch,
        score,
        remaining,
        math.ceil(batch * selected.expected_trial_cost),
        reason,
    )
