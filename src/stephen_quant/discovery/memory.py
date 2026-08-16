from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace

from stephen_quant.research_agent.dsl import analyze_formula

from .cpcv import DiscoveryCpcvReport
from .execution import DiscoveryExecutionReport
from .generator import GeneratedCandidate
from .models import FactorSchema
from .screening import ScreeningReport

RESEARCH_MEMORY_VERSION = "bounded-research-memory-1.0.0"


@dataclass(frozen=True)
class ResearchExperience:
    fingerprint: str
    schema_id: str
    family: str
    horizon: str
    proposal_number: int
    parent_fingerprints: tuple[str, ...]
    outcome: str
    reason: str
    training_rank_ic: float | None
    cpcv_rank_ic: float | None


@dataclass(frozen=True)
class SearchRecommendation:
    operation: str
    family: str
    parent_fingerprint: str | None
    changed_dimension: str | None
    rationale: str


@dataclass(frozen=True)
class ResearchMemory:
    memory_version: str
    campaign_id: str
    experiment_id: str
    feedback_partition: str
    experiences: tuple[ResearchExperience, ...]
    recommendations: tuple[SearchRecommendation, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)

    def to_markdown(self, language: str) -> str:
        if language not in {"en", "zh"}:
            raise ValueError("research memory language must be en or zh")
        zh = language == "zh"
        title = "# V1.8.16 研究记忆" if zh else "# V1.8.16 Research Memory"
        lines = [
            title,
            "",
            f"- {'实验' if zh else 'Experiment'}: `{self.experiment_id}`",
            f"- {'活动' if zh else 'Campaign'}: `{self.campaign_id}`",
            f"- {'反馈分区' if zh else 'Feedback partition'}: `{self.feedback_partition}`",
            "",
            "| Schema | Family | Outcome | Training RankIC | CPCV RankIC |",
            "|---|---|---|---:|---:|",
        ]
        for item in self.experiences:
            training = "N/A" if item.training_rank_ic is None else f"{item.training_rank_ic:.6f}"
            cpcv = "N/A" if item.cpcv_rank_ic is None else f"{item.cpcv_rank_ic:.6f}"
            lines.append(
                f"| `{item.schema_id}` | {item.family} | {item.outcome} | "
                f"{training} | {cpcv} |"
            )
        lines.extend(["", "## Explore / Exploit / Mutate", ""])
        lines.extend(
            f"- **{item.operation.upper()}** `{item.family}`: {item.rationale}"
            for item in self.recommendations
        )
        return "\n".join(lines) + "\n"


def _family(schema_id: str) -> str:
    pieces = schema_id.rsplit("_", 2)
    return pieces[0] if len(pieces) == 3 else schema_id


def build_research_memory(
    candidates: tuple[GeneratedCandidate, ...],
    screening: ScreeningReport,
    cpcv: DiscoveryCpcvReport | None,
    execution: DiscoveryExecutionReport | None,
    *,
    experiment_id: str,
) -> ResearchMemory:
    """Replay research-only outcomes; sealed validation/test data is never accepted."""

    if not experiment_id.strip():
        raise ValueError("research memory experiment_id cannot be empty")

    screen_by_fingerprint = {score.fingerprint: score for score in screening.scores}
    cpcv_by_fingerprint = (
        {score.fingerprint: score for score in cpcv.configurations} if cpcv else {}
    )
    experiences: list[ResearchExperience] = []
    for candidate in sorted(candidates, key=lambda item: item.proposal_number):
        schema = candidate.schema
        screen = screen_by_fingerprint.get(schema.fingerprint)
        cpcv_score = cpcv_by_fingerprint.get(schema.fingerprint)
        if not candidate.unique:
            outcome, reason = "duplicate", "structural fingerprint already proposed"
        elif screen is None:
            outcome, reason = "invalid", "candidate was not measured"
        elif cpcv_score is None:
            outcome, reason = screen.decision, screen.reason
        elif execution is None or execution.selected_fingerprint != schema.fingerprint:
            outcome, reason = "cpcv_evaluated", "not selected for final execution evidence"
        else:
            outcome, reason = execution.decision.lower(), "Alpha Court and walk-forward decision"
        experiences.append(
            ResearchExperience(
                fingerprint=schema.fingerprint,
                schema_id=schema.schema_id,
                family=_family(schema.schema_id),
                horizon=schema.horizon,
                proposal_number=candidate.proposal_number,
                parent_fingerprints=schema.parent_fingerprints,
                outcome=outcome,
                reason=reason,
                training_rank_ic=None if screen is None else screen.mean_rank_ic,
                cpcv_rank_ic=None if cpcv_score is None else cpcv_score.mean_path_rank_ic,
            )
        )

    family_scores: dict[str, list[ResearchExperience]] = {}
    for item in experiences:
        family_scores.setdefault(item.family, []).append(item)
    recommendations: list[SearchRecommendation] = []
    unexplored = sorted(
        family
        for family, rows in family_scores.items()
        if all(row.cpcv_rank_ic is None for row in rows)
    )
    if unexplored:
        recommendations.append(
            SearchRecommendation(
                operation="explore",
                family=unexplored[0],
                parent_fingerprint=None,
                changed_dimension=None,
                rationale="This family has no CPCV experience; allocate only a future frozen budget.",
            )
        )
    ranked = sorted(
        (item for item in experiences if item.cpcv_rank_ic is not None),
        key=lambda item: (item.cpcv_rank_ic or float("-inf"), item.fingerprint),
        reverse=True,
    )
    if ranked:
        best = ranked[0]
        recommendations.append(
            SearchRecommendation(
                operation="exploit",
                family=best.family,
                parent_fingerprint=best.fingerprint,
                changed_dimension=None,
                rationale="Retain the strongest research-only family without opening sealed windows.",
            )
        )
        recommendations.append(
            SearchRecommendation(
                operation="mutate",
                family=best.family,
                parent_fingerprint=best.fingerprint,
                changed_dimension="one_pre_registered_parameter",
                rationale="Change one dimension in the next campaign and preserve parent lineage.",
            )
        )
    return ResearchMemory(
        memory_version=RESEARCH_MEMORY_VERSION,
        campaign_id=screening.campaign_id,
        experiment_id=experiment_id,
        feedback_partition="research_only",
        experiences=tuple(experiences),
        recommendations=tuple(recommendations),
    )


def mutate_schema(
    parent: FactorSchema,
    *,
    schema_id: str,
    formula: str,
) -> FactorSchema:
    """Create one pre-registered formula mutation with explicit parent lineage."""

    analysis = analyze_formula(formula)
    if analysis.canonical_ast == analyze_formula(parent.formula).canonical_ast:
        raise ValueError("mutation must change the canonical formula")
    child = replace(
        parent,
        schema_id=schema_id,
        formula=formula,
        required_fields=analysis.required_fields,
        parent_fingerprints=(parent.fingerprint,),
    )
    child.validate()
    return child
