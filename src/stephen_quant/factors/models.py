from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FactorDefinition:
    """Immutable, versioned contract for one point-in-time factor."""

    factor_id: str
    version: str
    name: str
    category: str
    formula: str
    required_fields: tuple[str, ...]
    lookback_periods: int
    minimum_observations: int
    availability_lag_days: int
    direction: Literal[-1, 1]
    description: str

    @property
    def key(self) -> str:
        return f"{self.factor_id}@{self.version}"


@dataclass(frozen=True)
class FactorValue:
    factor_id: str
    version: str
    as_of: str
    decision_at: str
    value: float


class FactorError(ValueError):
    """Base class for deterministic factor calculation failures."""


class InsufficientHistoryError(FactorError):
    pass


class MissingDataError(FactorError):
    pass


class FutureDataError(FactorError):
    pass
