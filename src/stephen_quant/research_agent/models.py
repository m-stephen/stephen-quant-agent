from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

from stephen_quant.integrity.models import TrialSpec

AGENT_METHOD_VERSION = "integrity-first-factor-agent-1.0.0"
PROMPT_VERSION = "factor-proposal-json-dsl-1.0.0"


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    title: str
    content: str
    available_at: str


@dataclass(frozen=True)
class ResearchContext:
    snapshot_id: str
    knowledge_cutoff_at: str
    sources: tuple[ResearchSource, ...]


@dataclass(frozen=True)
class AgentRunSpec:
    model_id: str
    model_version: str
    seed: int
    trial: TrialSpec
    prompt_version: str = PROMPT_VERSION


@dataclass(frozen=True)
class FactorProposal:
    factor_id: str
    version: str
    name: str
    hypothesis: str
    formula: str
    required_fields: tuple[str, ...]
    direction: Literal[-1, 1]
    lookback_periods: int
    minimum_observations: int
    prediction_horizon: str
    evidence_source_ids: tuple[str, ...]
    falsification_tests: tuple[str, ...]
    economic_rationale: str
    failure_modes: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class AgentFinding:
    check: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class FactorResearchReport:
    method_version: str
    prompt_version: str
    status: Literal["proposed", "rejected"]
    trial_id: str
    trial_number: int
    snapshot_id: str
    experiment_id: str
    model_id: str
    model_version: str
    seed: int
    knowledge_cutoff_at: str
    source_ids: tuple[str, ...]
    prompt_sha256: str
    response_sha256: str | None
    candidate_id: str | None
    duplicate_of_candidate_id: str | None
    proposal: FactorProposal | None
    findings: tuple[AgentFinding, ...]
    rejection_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines = [
            "# LLM Factor Research Audit",
            "",
            f"**Status: {self.status.upper()}**",
            "",
            f"- Trial: `{self.trial_id}` (#{self.trial_number})",
            f"- Snapshot: `{self.snapshot_id}`",
            f"- Experiment: `{self.experiment_id}`",
            f"- Model: `{self.model_id}@{self.model_version}`",
            f"- Seed: {self.seed}",
            f"- Knowledge cutoff: `{self.knowledge_cutoff_at}`",
            f"- Prompt: `{self.prompt_version}` / `{self.prompt_sha256}`",
            f"- Response SHA-256: `{self.response_sha256 or 'not-called'}`",
            f"- Candidate: `{self.candidate_id or 'none'}`",
            "",
            "## Findings",
            "",
        ]
        lines.extend(
            f"- {'PASS' if finding.passed else 'FAIL'} — {finding.check}: {finding.detail}"
            for finding in self.findings
        )
        if self.rejection_reason:
            lines.extend(["", f"Rejection: {self.rejection_reason}"])
        if self.proposal:
            lines.extend(
                [
                    "",
                    "## Proposed hypothesis",
                    "",
                    f"- Factor: `{self.proposal.factor_id}@{self.proposal.version}`",
                    f"- Formula: `{self.proposal.formula}`",
                    f"- Horizon: `{self.proposal.prediction_horizon}`",
                    f"- Hypothesis: {self.proposal.hypothesis}",
                ]
            )
        lines.extend(
            [
                "",
                "A proposed candidate is not promoted, backtested, or approved for trading.",
            ]
        )
        return "\n".join(lines) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ResearchAgentError(ValueError):
    """Raised when LLM research violates schema, timing, or safe-DSL constraints."""
