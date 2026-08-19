from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass

from stephen_quant.research_agent.dsl import FUNCTION_ARITY, FUNCTION_FIELDS, analyze_formula
from stephen_quant.research_agent.models import ResearchAgentError

from .models import FactorSchema
from .semantic_catalog import (
    CandidateRoutingDecision,
    FieldSemantic,
    build_semantic_catalog,
    route_factor_schema,
)

TYPED_DSL_VERSION = "5.6.0"
MAX_AUTOMATIC_LOOKBACK = 252
_DIMENSIONLESS = {"ratio", "return", "multiple", "binary", "dimensionless"}


@dataclass(frozen=True)
class TypedValue:
    value_type: str
    unit: str
    frequency: str
    availability: tuple[str, ...]
    fields: tuple[str, ...]


@dataclass(frozen=True)
class TypedFormulaAnalysis:
    typed_dsl_version: str
    canonical_ast: str
    required_fields: tuple[str, ...]
    lookback_periods: int
    minimum_observations: int
    output: TypedValue
    research_form: str
    semantic_identity: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def _dimensionless(unit: str) -> bool:
    return unit in _DIMENSIONLESS


def _combine_unit(left: TypedValue, right: TypedValue, operation: ast.operator) -> str:
    if isinstance(operation, (ast.Add, ast.Sub)):
        if left.value_type == "constant":
            return right.unit
        if right.value_type == "constant":
            return left.unit
        if _dimensionless(left.unit) and _dimensionless(right.unit):
            return "ratio"
        if left.unit != right.unit:
            raise ResearchAgentError(
                f"typed DSL cannot add/subtract incompatible units: {left.unit}, {right.unit}"
            )
        return left.unit
    if isinstance(operation, ast.Mult):
        if _dimensionless(left.unit):
            return right.unit
        if _dimensionless(right.unit):
            return left.unit
        return "*".join(sorted((left.unit, right.unit)))
    if left.unit == right.unit:
        return "ratio"
    if _dimensionless(right.unit):
        return left.unit
    return f"{left.unit}_per_{right.unit}"


def _field_index(catalog: tuple[FieldSemantic, ...]) -> dict[str, FieldSemantic]:
    grouped: dict[str, list[FieldSemantic]] = {}
    for item in catalog:
        grouped.setdefault(item.field, []).append(item)
    ambiguous = sorted(field for field, items in grouped.items() if len(items) != 1)
    if ambiguous:
        raise ResearchAgentError(f"typed DSL requires unambiguous field semantics: {ambiguous}")
    return {field: items[0] for field, items in grouped.items()}


def _merge_metadata(*values: TypedValue, unit: str, value_type: str = "continuous") -> TypedValue:
    frequencies = {item.frequency for item in values}
    if len(frequencies) != 1:
        raise ResearchAgentError(f"typed DSL frequency mismatch: {sorted(frequencies)}")
    return TypedValue(
        value_type,
        unit,
        next(iter(frequencies)),
        tuple(sorted({availability for item in values for availability in item.availability})),
        tuple(sorted({field for item in values for field in item.fields})),
    )


def _typed_node(node: ast.AST, fields: dict[str, FieldSemantic]) -> TypedValue:
    if isinstance(node, ast.Expression):
        return _typed_node(node.body, fields)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return TypedValue("constant", "dimensionless", "daily", (), ())
    if isinstance(node, ast.UnaryOp):
        return _typed_node(node.operand, fields)
    if isinstance(node, ast.BinOp):
        left = _typed_node(node.left, fields)
        right = _typed_node(node.right, fields)
        return _merge_metadata(left, right, unit=_combine_unit(left, right, node.op))
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ResearchAgentError("invalid typed DSL node")
    function = node.func.id
    if function not in FUNCTION_ARITY:
        raise ResearchAgentError(f"unknown typed DSL function: {function}")
    inputs: list[FieldSemantic] = []
    for position in FUNCTION_FIELDS[function]:
        argument = node.args[position]
        if not isinstance(argument, ast.Name) or argument.id not in fields:
            raise ResearchAgentError(f"typed DSL has no semantic contract for {ast.unparse(argument)}")
        inputs.append(fields[argument.id])
    if function == "relative_strength" and inputs[0].unit != inputs[1].unit:
        raise ResearchAgentError("relative_strength requires fields with the same unit")
    if function == "mean":
        unit = "ratio" if inputs[0].value_type == "binary" else inputs[0].unit
        value_type = "continuous" if inputs[0].value_type != "binary" else "ratio"
    elif function == "amihud":
        if inputs[1].unit != "CNY":
            raise ResearchAgentError("amihud denominator must be a CNY traded-amount field")
        unit, value_type = "return_per_CNY", "continuous"
    else:
        unit, value_type = "return", "continuous"
    typed_inputs = tuple(
        TypedValue(
            item.value_type,
            item.unit,
            item.frequency,
            (item.availability,),
            (item.field,),
        )
        for item in inputs
    )
    return _merge_metadata(*typed_inputs, unit=unit, value_type=value_type)


def type_check_schema(
    schema: FactorSchema,
    *,
    route: CandidateRoutingDecision | None = None,
    catalog: tuple[FieldSemantic, ...] | None = None,
    max_lookback: int = MAX_AUTOMATIC_LOOKBACK,
) -> TypedFormulaAnalysis:
    schema.validate()
    semantics = catalog or build_semantic_catalog()
    routing = route or route_factor_schema(schema, catalog=semantics)
    if routing.schema_fingerprint != schema.fingerprint:
        raise ResearchAgentError("typed DSL route is not bound to this schema fingerprint")
    base = analyze_formula(schema.formula.strip())
    if base.lookback_periods > max_lookback:
        raise ResearchAgentError(
            f"typed DSL lookback {base.lookback_periods} exceeds automatic limit {max_lookback}"
        )
    tree = ast.parse(schema.formula.strip(), mode="eval")
    output = _typed_node(tree, _field_index(semantics))
    if output.fields != tuple(sorted(schema.required_fields)):
        raise ResearchAgentError("typed DSL field provenance differs from the schema contract")
    payload = {
        "catalog_version": TYPED_DSL_VERSION,
        "canonical_ast": base.canonical_ast,
        "output_unit": output.unit,
        "research_form": routing.primary_form,
        "route_identity": routing.semantic_identity,
    }
    identity = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return TypedFormulaAnalysis(
        TYPED_DSL_VERSION,
        base.canonical_ast,
        base.required_fields,
        base.lookback_periods,
        base.minimum_observations,
        output,
        routing.primary_form,
        identity,
    )
