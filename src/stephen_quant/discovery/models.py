from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Literal

from stephen_quant.factors.models import FactorDefinition
from stephen_quant.research_agent.dsl import analyze_formula
from stephen_quant.research_agent.models import ResearchAgentError

PredictionHorizon = Literal["next_open", "1d", "5d", "20d"]


@dataclass(frozen=True)
class FactorSchema:
    """Machine-readable, deterministic contract for one factor hypothesis."""

    schema_id: str
    version: str
    name: str
    event: str
    context: str
    quality: str
    direction: Literal[-1, 1]
    output: str
    horizon: PredictionHorizon
    formula: str
    data_sources: tuple[str, ...]
    required_fields: tuple[str, ...]
    availability_lag_days: int
    economic_rationale: str
    parent_fingerprints: tuple[str, ...] = ()

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.schema_id):
            raise ValueError("schema_id must use lowercase snake_case")
        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ValueError("version must use semantic numeric form")
        if self.direction not in {-1, 1}:
            raise ValueError("direction must be -1 or 1")
        if self.horizon not in {"next_open", "1d", "5d", "20d"}:
            raise ValueError(f"unsupported prediction horizon: {self.horizon}")
        if self.availability_lag_days < 0:
            raise ValueError("availability_lag_days cannot be negative")
        required_text = {
            "name": self.name,
            "event": self.event,
            "context": self.context,
            "quality": self.quality,
            "output": self.output,
            "economic_rationale": self.economic_rationale,
        }
        for field, value in required_text.items():
            if not value.strip():
                raise ValueError(f"{field} cannot be empty")
        if not self.data_sources or len(set(self.data_sources)) != len(self.data_sources):
            raise ValueError("data_sources must be non-empty and unique")
        analysis = analyze_formula(self.formula.strip())
        if tuple(sorted(self.required_fields)) != analysis.required_fields:
            raise ValueError("required_fields do not match the safe DSL formula")

    @property
    def fingerprint(self) -> str:
        self.validate()
        analysis = analyze_formula(self.formula.strip())
        payload = {
            "canonical_formula": analysis.canonical_ast,
            "context": self.context,
            "direction": self.direction,
            "event": self.event,
            "horizon": self.horizon,
            "output": self.output,
            "quality": self.quality,
            "required_fields": analysis.required_fields,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def compile(self) -> FactorDefinition:
        """Compile the schema to the existing immutable Factor Registry contract."""

        self.validate()
        analysis = analyze_formula(self.formula.strip())
        return FactorDefinition(
            factor_id=self.schema_id,
            version=self.version,
            name=self.name,
            category=self.event,
            formula=self.formula.strip(),
            required_fields=analysis.required_fields,
            lookback_periods=analysis.lookback_periods,
            minimum_observations=analysis.minimum_observations,
            availability_lag_days=self.availability_lag_days,
            direction=self.direction,
            description=(
                f"[{self.horizon}] {self.economic_rationale} "
                f"Context={self.context}; Quality={self.quality}; Output={self.output}."
            ),
        )


@dataclass(frozen=True)
class CampaignBudget:
    schema: int
    cpcv: int
    execution: int

    def validate(self) -> None:
        if self.schema < 1 or not 0 <= self.execution <= self.cpcv <= self.schema:
            raise ValueError("budgets must satisfy 0 <= execution <= cpcv <= schema")


class DiscoveryError(ResearchAgentError):
    """Raised when a generated candidate violates the frozen discovery contract."""
