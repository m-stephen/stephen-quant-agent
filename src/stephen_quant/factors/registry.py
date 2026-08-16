from __future__ import annotations

from collections.abc import Iterable

from .models import FactorDefinition


class FactorRegistry:
    """In-memory registry that rejects ambiguous factor versions."""

    def __init__(self, definitions: Iterable[FactorDefinition] = ()) -> None:
        self._definitions: dict[str, FactorDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: FactorDefinition) -> None:
        if definition.key in self._definitions:
            raise ValueError(f"factor definition already registered: {definition.key}")
        if definition.lookback_periods < 1:
            raise ValueError("lookback_periods must be positive")
        if definition.minimum_observations < 1:
            raise ValueError("minimum_observations must be positive")
        if definition.availability_lag_days < 0:
            raise ValueError("availability_lag_days cannot be negative")
        self._definitions[definition.key] = definition

    def get(self, factor_id: str, version: str = "1.0.0") -> FactorDefinition:
        key = f"{factor_id}@{version}"
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise KeyError(f"unknown factor definition: {key}") from exc

    def list(self) -> tuple[FactorDefinition, ...]:
        return tuple(self._definitions[key] for key in sorted(self._definitions))
