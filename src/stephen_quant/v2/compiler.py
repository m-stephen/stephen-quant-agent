from __future__ import annotations

import ast
import re
from dataclasses import dataclass, replace
from typing import Literal

from stephen_quant.discovery.models import SOURCE_FIELDS, FactorSchema
from stephen_quant.research_agent.dsl import FUNCTION_FIELDS, analyze_formula
from stephen_quant.research_agent.models import ResearchAgentError

from .contracts import V2FactorContract, V2Hypothesis, migrate_v1_factor_schema

DecisionContext = Literal["prior_close", "pre_open", "after_close"]
Dimension = Literal["price", "money", "volume", "return", "ratio", "scalar", "score"]


@dataclass(frozen=True)
class FieldPolicy:
    field: str
    source: str
    dimension: Dimension
    available_context: DecisionContext
    availability_lag_days: int = 0


@dataclass(frozen=True)
class CompilerPolicy:
    dataset_snapshot_id: str
    decision_context: DecisionContext
    field_coverage: tuple[tuple[str, float], ...]
    minimum_coverage: float = 0.80
    maximum_lookback: int = 252
    maximum_complexity_nodes: int = 48

    def validate(self) -> None:
        if not self.dataset_snapshot_id.strip():
            raise ValueError("compiler requires a frozen dataset snapshot")
        if not 0 < self.minimum_coverage <= 1:
            raise ValueError("minimum coverage must be in (0, 1]")
        if self.maximum_lookback < 1 or self.maximum_complexity_nodes < 1:
            raise ValueError("compiler limits must be positive")
        fields = [field for field, _ in self.field_coverage]
        if len(fields) != len(set(fields)):
            raise ValueError("field coverage declarations must be unique")
        if any(not 0 <= coverage <= 1 for _, coverage in self.field_coverage):
            raise ValueError("field coverage values must be in [0, 1]")


@dataclass(frozen=True)
class ExpressionBlueprint:
    blueprint_id: str
    event: str
    name: str
    formula_template: str
    parameters: tuple[tuple[str, int], ...]
    output: str = "cross_sectional_score"

    def render(self) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.blueprint_id):
            raise ValueError("blueprint_id must use lowercase snake_case")
        if len(self.parameters) != len(set(self.parameters)):
            raise ValueError("blueprint parameters must be unique")
        try:
            return self.formula_template.format(**dict(self.parameters))
        except (KeyError, ValueError) as exc:
            raise ValueError("blueprint parameters do not render deterministically") from exc


@dataclass(frozen=True)
class StaticAuditFinding:
    code: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class CompiledExpressionFamily:
    contract: V2FactorContract
    blueprint_id: str
    dimension: Dimension
    complexity_nodes: int
    findings: tuple[StaticAuditFinding, ...]


FIELD_POLICIES: dict[str, FieldPolicy] = {}


def _register(
    fields: tuple[str, ...],
    source: str,
    dimension: Dimension,
    context: DecisionContext,
) -> None:
    for field in fields:
        FIELD_POLICIES[field] = FieldPolicy(field, source, dimension, context)


_register(("close", "high", "low", "benchmark_close"), "qd_daily", "price", "after_close")
_register(("amount",), "qd_daily", "money", "after_close")
_register(("volume",), "qd_daily", "volume", "after_close")
_register(("turnover",), "qd_daily", "ratio", "after_close")
_register(tuple(sorted(SOURCE_FIELDS["qd_fund_flow"])), "qd_fund_flow", "money", "after_close")
_register(("auction_return",), "qd_auction", "return", "pre_open")
_register(("auction_amount",), "qd_auction", "money", "pre_open")
_register(("auction_volume_ratio_1",), "qd_auction", "ratio", "pre_open")
_register(tuple(sorted(SOURCE_FIELDS["qd_margin"])), "qd_margin", "money", "after_close")
_register(("industry_return",), "qd_industry", "return", "after_close")
_register(("industry_pe", "industry_pb"), "qd_industry", "ratio", "after_close")

_CONTEXT_RANK = {"prior_close": 0, "pre_open": 1, "after_close": 2}


@dataclass(frozen=True)
class _TypedValue:
    dimension: Dimension
    constant: bool = False


def _positive_floor(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return float(node.value) > 0
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _positive_floor(node.left) or _positive_floor(node.right)
    return False


def _typed(node: ast.AST) -> _TypedValue:
    if isinstance(node, ast.Expression):
        return _typed(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return _TypedValue("scalar", True)
    if isinstance(node, ast.UnaryOp):
        return _typed(node.operand)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = node.func.id
        field = node.args[0]
        if not isinstance(field, ast.Name):
            raise ResearchAgentError("typed DSL functions require a direct field")
        field_dimension = FIELD_POLICIES[field.id].dimension
        if function in {"period_return", "volatility", "relative_strength", "max_drawdown"}:
            return _TypedValue("return")
        if function == "sma_ratio":
            return _TypedValue("ratio")
        if function == "amihud":
            return _TypedValue("score")
        if function == "mean":
            return _TypedValue(field_dimension)
        raise ResearchAgentError(f"unknown typed DSL function: {function}")
    if isinstance(node, ast.BinOp):
        left, right = _typed(node.left), _typed(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            if left.dimension == right.dimension:
                return _TypedValue(left.dimension)
            if {left.dimension, right.dimension} <= {"ratio", "return"}:
                return _TypedValue("score")
            if left.constant:
                return _TypedValue(right.dimension)
            if right.constant:
                return _TypedValue(left.dimension)
            raise ResearchAgentError(
                f"typed DSL cannot add/subtract {left.dimension} and {right.dimension}"
            )
        if isinstance(node.op, ast.Mult):
            if left.constant:
                return _TypedValue(right.dimension)
            if right.constant:
                return _TypedValue(left.dimension)
            return _TypedValue("score")
        if isinstance(node.op, ast.Div):
            if not _positive_floor(node.right):
                raise ResearchAgentError("typed DSL division requires a positive denominator floor")
            if left.dimension == right.dimension:
                return _TypedValue("ratio")
            return _TypedValue("score")
    raise ResearchAgentError("invalid typed DSL node")


def _window_literals(tree: ast.AST) -> tuple[int, ...]:
    windows: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        for index, argument in enumerate(node.args):
            if index not in FUNCTION_FIELDS[node.func.id] and isinstance(argument, ast.Constant):
                windows.append(int(argument.value))
    return tuple(windows)


def compile_hypothesis(
    hypothesis: V2Hypothesis,
    blueprint: ExpressionBlueprint,
    policy: CompilerPolicy,
) -> CompiledExpressionFamily:
    """Compile one constrained blueprint and fail closed before any data evaluation."""

    hypothesis.validate()
    policy.validate()
    if hypothesis.event != blueprint.event:
        raise ValueError("blueprint event does not match hypothesis event")
    formula = blueprint.render()
    analysis = analyze_formula(formula)
    if analysis.required_fields != tuple(sorted(hypothesis.inputs)):
        raise ValueError("hypothesis inputs do not match compiled expression fields")
    unknown = set(analysis.required_fields) - set(FIELD_POLICIES)
    if unknown:
        raise ResearchAgentError(f"typed DSL field policy missing: {sorted(unknown)}")

    tree = ast.parse(formula, mode="eval")
    complexity = sum(1 for _ in ast.walk(tree))
    if complexity > min(
        policy.maximum_complexity_nodes, hypothesis.economic_complexity_budget * 16
    ):
        raise ResearchAgentError("typed DSL complexity budget exceeded")
    windows = _window_literals(tree)
    if windows and max(windows) > policy.maximum_lookback:
        raise ResearchAgentError("typed DSL lookback exceeds compiler policy")

    coverage = dict(policy.field_coverage)
    for field in analysis.required_fields:
        if field not in coverage or coverage[field] < policy.minimum_coverage:
            raise ResearchAgentError(f"typed DSL coverage gate failed for {field}")
        required_context = FIELD_POLICIES[field].available_context
        if _CONTEXT_RANK[required_context] > _CONTEXT_RANK[policy.decision_context]:
            raise ResearchAgentError(f"typed DSL PIT context failed for {field}")

    dimension = _typed(tree).dimension
    sources = tuple(sorted({FIELD_POLICIES[field].source for field in analysis.required_fields}))
    lag = max(FIELD_POLICIES[field].availability_lag_days for field in analysis.required_fields)
    schema_id = f"v2_{blueprint.blueprint_id}_{hypothesis.hypothesis_id[-8:]}"
    legacy = FactorSchema(
        schema_id=schema_id,
        version="2.0.0",
        name=blueprint.name,
        event=hypothesis.event,
        context="|".join(hypothesis.contexts),
        quality="compiler_policy_qualified",
        direction=hypothesis.direction,  # type: ignore[arg-type]
        output=blueprint.output,
        horizon=hypothesis.expected_horizon,  # type: ignore[arg-type]
        formula=formula,
        data_sources=sources,
        required_fields=analysis.required_fields,
        availability_lag_days=lag,
        economic_rationale=hypothesis.mechanism,
    )
    migrated = migrate_v1_factor_schema(
        legacy,
        dataset_snapshot_id=policy.dataset_snapshot_id,
        controls=hypothesis.controls,
        falsification_criteria=hypothesis.falsification_criteria,
        evidence_refs=hypothesis.evidence_refs,
        economic_complexity_budget=hypothesis.economic_complexity_budget,
        search_budget=hypothesis.search_budget,
    )
    contract = replace(
        migrated, hypothesis=hypothesis, migration_reason="native V2 constrained compilation"
    )
    contract.validate()
    findings = (
        StaticAuditFinding("DSL_ALLOWLIST", True, "all fields and functions are allowlisted"),
        StaticAuditFinding("TYPE_DIMENSION", True, f"compiled output dimension={dimension}"),
        StaticAuditFinding("WINDOW_BOUND", True, f"maximum lookback={analysis.lookback_periods}"),
        StaticAuditFinding("COVERAGE_GATE", True, "all required fields meet frozen coverage"),
        StaticAuditFinding("PIT_STATIC", True, f"decision context={policy.decision_context}"),
        StaticAuditFinding("SAFE_DIVISION", True, "all divisions have a positive floor"),
    )
    return CompiledExpressionFamily(
        contract, blueprint.blueprint_id, dimension, complexity, findings
    )


def default_blueprints() -> tuple[ExpressionBlueprint, ...]:
    return (
        ExpressionBlueprint(
            "flow_price_divergence",
            "flow_price_divergence",
            "Flow-price divergence",
            "mean(net_inflow_amount, {lookback}) / (mean(amount, {lookback}) + 1.0) - period_return(close, {lookback})",
            (("lookback", 20),),
        ),
        ExpressionBlueprint(
            "large_flow_surprise",
            "large_flow_surprise",
            "Large-order flow surprise",
            "(mean(large_buy_amount, {short}) - mean(large_sell_amount, {short})) / (mean(amount, {short}) + 1.0) - (mean(large_buy_amount, {long}) - mean(large_sell_amount, {long})) / (mean(amount, {long}) + 1.0)",
            (("short", 5), ("long", 60)),
        ),
        ExpressionBlueprint(
            "margin_demand_intensity",
            "margin_financing",
            "Margin demand intensity",
            "mean(margin_financing_buy, {lookback}) / (mean(amount, {lookback}) + 1.0)",
            (("lookback", 20),),
        ),
    )
