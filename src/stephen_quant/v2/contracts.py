from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from stephen_quant.discovery.models import FactorSchema
from stephen_quant.research_agent.dsl import analyze_formula

V2_CONTRACT_VERSION = "factor-schema-2.0.0"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _identifier(prefix: str, value: object) -> str:
    return f"{prefix}_{hashlib.sha256(_canonical(value).encode()).hexdigest()[:24]}"


@dataclass(frozen=True)
class V2Hypothesis:
    statement: str
    event: str
    contexts: tuple[str, ...]
    mechanism: str
    direction: int
    expected_horizon: str
    universe: str
    regime: str
    inputs: tuple[str, ...]
    controls: tuple[str, ...]
    falsification_criteria: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    economic_complexity_budget: int
    search_budget: int
    parent_hypothesis_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        required = (
            self.statement,
            self.event,
            self.mechanism,
            self.expected_horizon,
            self.universe,
            self.regime,
        )
        if any(not item.strip() for item in required):
            raise ValueError("V2 hypothesis contains empty required text")
        if self.direction not in {-1, 1}:
            raise ValueError("V2 hypothesis direction must be -1 or 1")
        if not self.inputs or not self.falsification_criteria:
            raise ValueError("V2 hypothesis requires inputs and falsification criteria")
        if self.economic_complexity_budget < 1 or self.search_budget < 1:
            raise ValueError("V2 hypothesis budgets must be positive")
        for values in (
            self.contexts,
            self.inputs,
            self.controls,
            self.falsification_criteria,
            self.evidence_refs,
            self.parent_hypothesis_ids,
        ):
            if len(values) != len(set(values)):
                raise ValueError("V2 hypothesis tuple fields must be unique")

    @property
    def hypothesis_id(self) -> str:
        self.validate()
        return _identifier("hyp", asdict(self))


@dataclass(frozen=True)
class HierarchicalIds:
    hypothesis_id: str
    expression_structure_id: str
    parameter_variant_id: str
    test_stage_id: str


@dataclass(frozen=True)
class V2FactorContract:
    contract_version: str
    hypothesis: V2Hypothesis
    formula: str
    canonical_ast: str
    parameters: tuple[tuple[str, str], ...]
    test_stage: str
    dataset_snapshot_id: str
    legacy_schema_json: str
    legacy_fingerprint: str
    migration_reason: str

    def validate(self) -> None:
        if self.contract_version != V2_CONTRACT_VERSION:
            raise ValueError("unsupported V2 contract version")
        self.hypothesis.validate()
        analysis = analyze_formula(self.formula)
        if analysis.canonical_ast != self.canonical_ast:
            raise ValueError("V2 canonical AST does not match formula")
        if not self.test_stage.strip() or not self.dataset_snapshot_id.strip():
            raise ValueError("V2 test stage and dataset snapshot are required")
        if len(self.legacy_fingerprint) != 64 or not self.migration_reason.strip():
            raise ValueError("V2 migration provenance is incomplete")
        if len(self.parameters) != len(set(self.parameters)):
            raise ValueError("V2 parameters must be unique")
        legacy = self.to_v1()
        if legacy.fingerprint != self.legacy_fingerprint:
            raise ValueError("V2 migration does not preserve the V1 fingerprint")
        if analyze_formula(legacy.formula).canonical_ast != self.canonical_ast:
            raise ValueError("V2 expression differs from embedded legacy provenance")

    @property
    def ids(self) -> HierarchicalIds:
        self.validate()
        structure_id = _identifier(
            "expr",
            {
                "canonical_ast": self.canonical_ast,
                "inputs": self.hypothesis.inputs,
            },
        )
        variant_id = _identifier(
            "variant",
            {
                "hypothesis_id": self.hypothesis.hypothesis_id,
                "expression_structure_id": structure_id,
                "parameters": self.parameters,
                "direction": self.hypothesis.direction,
                "horizon": self.hypothesis.expected_horizon,
            },
        )
        stage_id = _identifier(
            "stage",
            {
                "parameter_variant_id": variant_id,
                "test_stage": self.test_stage,
                "dataset_snapshot_id": self.dataset_snapshot_id,
            },
        )
        return HierarchicalIds(
            self.hypothesis.hypothesis_id, structure_id, variant_id, stage_id
        )

    def to_v1(self) -> FactorSchema:
        try:
            payload = json.loads(self.legacy_schema_json)
            schema = FactorSchema(**payload)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("legacy FactorSchema JSON is invalid") from exc
        schema.validate()
        return schema

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def migrate_v1_factor_schema(
    schema: FactorSchema,
    *,
    dataset_snapshot_id: str,
    test_stage: str = "research",
    controls: tuple[str, ...] = (),
    falsification_criteria: tuple[str, ...] = (
        "residual_ic_disappears_after_controls",
        "long_leg_has_no_positive_net_return",
        "result_is_date_concentrated",
    ),
    evidence_refs: tuple[str, ...] = (),
    economic_complexity_budget: int = 3,
    search_budget: int = 1,
) -> V2FactorContract:
    """Losslessly wrap a validated V1 factor in the V2 contract."""

    schema.validate()
    analysis = analyze_formula(schema.formula)
    hypothesis = V2Hypothesis(
        statement=schema.economic_rationale,
        event=schema.event,
        contexts=(schema.context,),
        mechanism=schema.economic_rationale,
        direction=schema.direction,
        expected_horizon=schema.horizon,
        universe="declared_dynamic_research_universe",
        regime="all_preregistered_research_regimes",
        inputs=analysis.required_fields,
        controls=controls,
        falsification_criteria=falsification_criteria,
        evidence_refs=evidence_refs,
        economic_complexity_budget=economic_complexity_budget,
        search_budget=search_budget,
    )
    parameters = (
        ("availability_lag_days", str(schema.availability_lag_days)),
        ("lookback_periods", str(analysis.lookback_periods)),
        ("minimum_observations", str(analysis.minimum_observations)),
        ("schema_version", schema.version),
    )
    contract = V2FactorContract(
        contract_version=V2_CONTRACT_VERSION,
        hypothesis=hypothesis,
        formula=schema.formula,
        canonical_ast=analysis.canonical_ast,
        parameters=parameters,
        test_stage=test_stage,
        dataset_snapshot_id=dataset_snapshot_id,
        legacy_schema_json=schema.to_json(),
        legacy_fingerprint=schema.fingerprint,
        migration_reason="lossless V1-to-V2 compatible migration",
    )
    contract.validate()
    return contract
