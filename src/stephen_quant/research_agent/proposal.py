from __future__ import annotations

import json
import re

from .dsl import FormulaAnalysis, analyze_formula
from .models import FactorProposal, ResearchAgentError, sha256_text

PROPOSAL_FIELDS = {
    "direction",
    "economic_rationale",
    "evidence_source_ids",
    "factor_id",
    "failure_modes",
    "falsification_tests",
    "formula",
    "hypothesis",
    "lookback_periods",
    "minimum_observations",
    "name",
    "prediction_horizon",
    "required_fields",
    "version",
}
REQUIRED_FALSIFICATION = {"cpcv", "return_permutation", "signal_shuffle"}


def _string(payload: dict[str, object], field: str, *, maximum: int = 2_000) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ResearchAgentError(f"proposal field {field} must be a non-empty bounded string")
    return value.strip()


def _strings(payload: dict[str, object], field: str) -> tuple[str, ...]:
    value = payload[field]
    if not isinstance(value, list) or not value:
        raise ResearchAgentError(f"proposal field {field} must be a non-empty string array")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ResearchAgentError(f"proposal field {field} contains an invalid item")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise ResearchAgentError(f"proposal field {field} contains duplicates")
    return normalized


def parse_proposal(response: str) -> tuple[FactorProposal, FormulaAnalysis, str]:
    if not isinstance(response, str) or not response or len(response) > 100_000:
        raise ResearchAgentError("LLM response must be non-empty and bounded")

    def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ResearchAgentError(f"LLM response contains duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> object:
        raise ResearchAgentError(f"LLM response contains non-standard JSON number: {value}")

    try:
        payload = json.loads(
            response,
            object_pairs_hook=exact_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise ResearchAgentError("LLM response is not strict JSON") from exc
    if not isinstance(payload, dict) or set(payload) != PROPOSAL_FIELDS:
        raise ResearchAgentError("LLM response does not match the exact proposal schema")
    factor_id = _string(payload, "factor_id", maximum=80)
    version = _string(payload, "version", maximum=30)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", factor_id):
        raise ResearchAgentError("factor_id must use lowercase snake_case")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ResearchAgentError("version must use semantic numeric form")
    direction = payload["direction"]
    lookback = payload["lookback_periods"]
    minimum = payload["minimum_observations"]
    if type(direction) is not int or direction not in {-1, 1}:
        raise ResearchAgentError("direction must be -1 or 1")
    if type(lookback) is not int or lookback < 1:
        raise ResearchAgentError("lookback_periods must be a positive integer")
    if type(minimum) is not int or minimum < 1:
        raise ResearchAgentError("minimum_observations must be a positive integer")
    formula = _string(payload, "formula", maximum=500)
    analysis = analyze_formula(formula)
    required_fields = _strings(payload, "required_fields")
    if tuple(sorted(required_fields)) != analysis.required_fields:
        raise ResearchAgentError("declared required_fields do not match the formula")
    if lookback < analysis.lookback_periods or minimum < analysis.minimum_observations:
        raise ResearchAgentError("declared history is insufficient for the formula")
    falsification = _strings(payload, "falsification_tests")
    if not REQUIRED_FALSIFICATION.issubset(falsification):
        raise ResearchAgentError("proposal lacks mandatory falsification tests")
    proposal = FactorProposal(
        factor_id=factor_id,
        version=version,
        name=_string(payload, "name", maximum=200),
        hypothesis=_string(payload, "hypothesis"),
        formula=formula,
        required_fields=required_fields,
        direction=direction,
        lookback_periods=lookback,
        minimum_observations=minimum,
        prediction_horizon=_string(payload, "prediction_horizon", maximum=80),
        evidence_source_ids=_strings(payload, "evidence_source_ids"),
        falsification_tests=falsification,
        economic_rationale=_string(payload, "economic_rationale"),
        failure_modes=_strings(payload, "failure_modes"),
    )
    fingerprint_payload = json.dumps(
        {
            "canonical_formula": analysis.canonical_ast,
            "direction": direction,
            "prediction_horizon": proposal.prediction_horizon,
            "required_fields": analysis.required_fields,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return proposal, analysis, sha256_text(fingerprint_payload)
