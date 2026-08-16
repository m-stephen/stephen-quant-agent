from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from itertools import pairwise

from .models import AllocationStep, RewardConfig, RLError, RLObservation


def _parse(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RLError(f"invalid ISO timestamp: {value}") from exc


def validate_observations(
    observations: Sequence[RLObservation], asset_count: int
) -> tuple[RLObservation, ...]:
    if not observations:
        raise RLError("portfolio environment requires observations")
    if asset_count < 1:
        raise RLError("asset_count must be positive")
    ordered = tuple(sorted(observations, key=lambda row: _parse(row.execution_at)))
    seen: set[str] = set()
    state_dimension = len(ordered[0].features)
    if state_dimension < 1:
        raise RLError("state features cannot be empty")
    for row in ordered:
        if row.execution_at in seen:
            raise RLError(f"duplicate execution timestamp: {row.execution_at}")
        seen.add(row.execution_at)
        if len(row.features) != state_dimension:
            raise RLError("state feature dimension must be constant")
        if len(row.asset_returns) != asset_count:
            raise RLError("asset return dimension does not match assets")
        if any(not math.isfinite(value) for value in (*row.features, *row.asset_returns)):
            raise RLError("observations must be finite")
        if any(value <= -1 for value in row.asset_returns):
            raise RLError("long-only asset returns cannot be <= -100%")
        if _parse(row.state_available_at) >= _parse(row.execution_at):
            raise RLError("state is not available before execution")
        if _parse(row.return_end_at) <= _parse(row.execution_at):
            raise RLError("return window must follow execution")
    for left, right in pairwise(ordered):
        if _parse(left.return_end_at) > _parse(right.execution_at):
            raise RLError("sequential return windows cannot overlap")
    return ordered


def validate_reward_config(config: RewardConfig) -> None:
    values = (
        config.commission_bps,
        config.slippage_bps,
        config.turnover_penalty,
        config.drawdown_penalty,
    )
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise RLError("reward and cost assumptions must be finite and non-negative")
    if not config.reward_version:
        raise RLError("reward_version cannot be empty")


def validate_weights(weights: Sequence[float], action_dimension: int) -> tuple[float, ...]:
    values = tuple(float(value) for value in weights)
    if len(values) != action_dimension:
        raise RLError("action dimension does not match assets plus cash")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise RLError("allocation weights must be finite and non-negative")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
        raise RLError("allocation weights must sum to one")
    return values


class PortfolioEnvironment:
    def __init__(
        self,
        observations: Sequence[RLObservation],
        assets: Sequence[str],
        reward_config: RewardConfig,
        *,
        initial_nav: float = 1.0,
    ) -> None:
        if not assets or any(not asset for asset in assets) or len(set(assets)) != len(assets):
            raise RLError("assets must be unique non-empty identifiers")
        if not math.isfinite(initial_nav) or initial_nav <= 0:
            raise RLError("initial_nav must be finite and positive")
        validate_reward_config(reward_config)
        self.assets = tuple(assets)
        self.observations = validate_observations(observations, len(self.assets))
        self.reward_config = reward_config
        self.initial_nav = float(initial_nav)
        self.reset()

    def reset(self) -> RLObservation:
        self.index = 0
        self.nav = self.initial_nav
        self.peak_nav = self.initial_nav
        self.weights = (0.0,) * len(self.assets) + (1.0,)
        return self.observations[0]

    @property
    def done(self) -> bool:
        return self.index >= len(self.observations)

    def step(self, weights: Sequence[float]) -> AllocationStep:
        if self.done:
            raise RLError("portfolio episode is already complete")
        action = validate_weights(weights, len(self.assets) + 1)
        row = self.observations[self.index]
        risky_traded_fraction = sum(
            abs(action[index] - self.weights[index]) for index in range(len(self.assets))
        )
        turnover = risky_traded_fraction / 2
        cost = risky_traded_fraction * (
            self.reward_config.commission_bps + self.reward_config.slippage_bps
        ) / 10_000
        gross_return = sum(
            weight * asset_return
            for weight, asset_return in zip(
                action[:-1], row.asset_returns, strict=True
            )
        )
        net_return = gross_return - cost
        if net_return <= -1:
            raise RLError("cost-adjusted return would exhaust portfolio NAV")
        self.nav *= 1 + net_return
        self.peak_nav = max(self.peak_nav, self.nav)
        drawdown = self.nav / self.peak_nav - 1
        reward = (
            math.log1p(net_return)
            - self.reward_config.turnover_penalty * turnover
            - self.reward_config.drawdown_penalty * abs(drawdown)
        )
        gross_components = tuple(
            weight * (1 + asset_return)
            for weight, asset_return in zip(action[:-1], row.asset_returns, strict=True)
        ) + (action[-1],)
        gross_total = sum(gross_components)
        self.weights = tuple(value / gross_total for value in gross_components)
        self.index += 1
        return AllocationStep(
            timestamp=row.timestamp,
            weights=action,
            asset_weights=action[:-1],
            cash_weight=action[-1],
            gross_return=gross_return,
            net_return=net_return,
            turnover=turnover,
            cost=cost,
            drawdown=drawdown,
            reward=reward,
            end_nav=self.nav,
        )
