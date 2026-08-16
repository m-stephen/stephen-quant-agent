from __future__ import annotations

import ast
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from .models import ResearchAgentError

ALLOWED_FIELDS = {
    "amount",
    "benchmark_close",
    "close",
    "high",
    "low",
    "turnover",
    "volume",
}
FUNCTION_FIELDS: dict[str, tuple[int, ...]] = {
    "period_return": (0,),
    "mean": (0,),
    "volatility": (0,),
    "sma_ratio": (0,),
    "relative_strength": (0, 1),
    "max_drawdown": (0,),
    "amihud": (0, 1),
}
FUNCTION_ARITY = {
    "period_return": 2,
    "mean": 2,
    "volatility": 2,
    "sma_ratio": 3,
    "relative_strength": 3,
    "max_drawdown": 2,
    "amihud": 3,
}


@dataclass(frozen=True)
class FormulaAnalysis:
    canonical_ast: str
    required_fields: tuple[str, ...]
    lookback_periods: int
    minimum_observations: int


@dataclass(frozen=True)
class FormulaInput:
    values: tuple[float | int | None, ...]
    available_at: tuple[str, ...]


def _integer(node: ast.AST, function: str) -> int:
    if not isinstance(node, ast.Constant) or type(node.value) is not int:
        raise ResearchAgentError(f"{function} lookbacks must be integer literals")
    value = int(node.value)
    if not 1 <= value <= 10_000:
        raise ResearchAgentError(f"{function} lookbacks must be between 1 and 10000")
    return value


def _validate_node(node: ast.AST, fields: set[str]) -> tuple[int, int]:
    if isinstance(node, ast.Expression):
        return _validate_node(node.body, fields)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _validate_node(node.left, fields)
        right = _validate_node(node.right, fields)
        return max(left[0], right[0]), max(left[1], right[1])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _validate_node(node.operand, fields)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        value = float(node.value)
        if not math.isfinite(value) or abs(value) > 1_000_000:
            raise ResearchAgentError("DSL constants must be finite and bounded")
        return 0, 0
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        raise ResearchAgentError("DSL permits only arithmetic and direct whitelisted calls")
    function = node.func.id
    if function not in FUNCTION_ARITY:
        raise ResearchAgentError(f"unknown DSL function: {function}")
    if node.keywords or len(node.args) != FUNCTION_ARITY[function]:
        raise ResearchAgentError(f"invalid arguments for DSL function: {function}")
    for position in FUNCTION_FIELDS[function]:
        argument = node.args[position]
        if not isinstance(argument, ast.Name) or argument.id not in ALLOWED_FIELDS:
            raise ResearchAgentError(f"{function} requires a whitelisted field identifier")
        fields.add(argument.id)
    lookbacks = [
        _integer(node.args[position], function)
        for position in range(len(node.args))
        if position not in FUNCTION_FIELDS[function]
    ]
    if function == "sma_ratio" and lookbacks[0] >= lookbacks[1]:
        raise ResearchAgentError("sma_ratio requires short lookback < long lookback")
    lookback = max(lookbacks)
    minimum = lookback + 1 if function in {"period_return", "volatility", "relative_strength", "amihud"} else lookback
    return lookback, minimum


def analyze_formula(formula: str) -> FormulaAnalysis:
    if not formula or len(formula) > 500:
        raise ResearchAgentError("formula must contain between 1 and 500 characters")
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise ResearchAgentError("formula is not valid safe DSL syntax") from exc
    fields: set[str] = set()
    lookback, minimum = _validate_node(tree, fields)
    return FormulaAnalysis(
        canonical_ast=ast.dump(tree, annotate_fields=True, include_attributes=False),
        required_fields=tuple(sorted(fields)),
        lookback_periods=lookback,
        minimum_observations=minimum,
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchAgentError(f"invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ResearchAgentError(f"timestamp must include a timezone: {value}")
    return parsed


def _prepare_inputs(
    analysis: FormulaAnalysis,
    inputs: Mapping[str, FormulaInput],
    decision_at: str,
) -> dict[str, list[float]]:
    decision = _parse_timestamp(decision_at)
    prepared: dict[str, list[float]] = {}
    for field in analysis.required_fields:
        if field not in inputs:
            raise ResearchAgentError(f"missing DSL input: {field}")
        item = inputs[field]
        if len(item.values) != len(item.available_at):
            raise ResearchAgentError(f"DSL values and availability differ for {field}")
        if len(item.values) < analysis.minimum_observations:
            raise ResearchAgentError(f"insufficient DSL history for {field}")
        values = item.values[-analysis.minimum_observations :]
        availability = item.available_at[-analysis.minimum_observations :]
        if any(_parse_timestamp(timestamp) > decision for timestamp in availability):
            raise ResearchAgentError(f"future-unavailable DSL input: {field}")
        if any(value is None or not math.isfinite(float(value)) for value in values):
            raise ResearchAgentError(f"missing or non-finite DSL input: {field}")
        prepared[field] = [float(value) for value in values if value is not None]
    return prepared


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _returns(values: Sequence[float]) -> list[float]:
    return [values[index] / values[index - 1] - 1 for index in range(1, len(values))]


def _call(function: str, arguments: Sequence[ast.AST], data: Mapping[str, list[float]]) -> float:
    fields = [
        argument.id for argument in arguments if isinstance(argument, ast.Name)
    ]
    lookbacks = [
        int(argument.value) for argument in arguments if isinstance(argument, ast.Constant)
    ]
    if function == "period_return":
        values, lookback = data[fields[0]], lookbacks[0]
        return values[-1] / values[-lookback - 1] - 1
    if function == "mean":
        return _mean(data[fields[0]][-lookbacks[0] :])
    if function == "volatility":
        returns = _returns(data[fields[0]][-lookbacks[0] - 1 :])
        center = _mean(returns)
        return math.sqrt(_mean([(value - center) ** 2 for value in returns]))
    if function == "sma_ratio":
        values, short, long = data[fields[0]], lookbacks[0], lookbacks[1]
        return _mean(values[-short:]) / _mean(values[-long:]) - 1
    if function == "relative_strength":
        lookback = lookbacks[0]
        left = data[fields[0]][-1] / data[fields[0]][-lookback - 1] - 1
        right = data[fields[1]][-1] / data[fields[1]][-lookback - 1] - 1
        return left - right
    if function == "max_drawdown":
        peak = data[fields[0]][-lookbacks[0]]
        worst = 0.0
        for value in data[fields[0]][-lookbacks[0] :]:
            peak = max(peak, value)
            worst = min(worst, value / peak - 1)
        return worst
    if function == "amihud":
        lookback = lookbacks[0]
        returns = _returns(data[fields[0]][-lookback - 1 :])
        amount = data[fields[1]][-lookback:]
        if any(value <= 0 for value in amount):
            raise ResearchAgentError("amihud amount must be positive")
        return _mean(
            [abs(value) / traded for value, traded in zip(returns, amount, strict=True)]
        )
    raise ResearchAgentError(f"unknown DSL function: {function}")


def _evaluate(node: ast.AST, data: Mapping[str, list[float]]) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, data)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, data)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left, right = _evaluate(node.left, data), _evaluate(node.right, data)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise ResearchAgentError("DSL division by zero")
        return left / right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _call(node.func.id, node.args, data)
    raise ResearchAgentError("invalid validated DSL node")


def evaluate_formula(
    formula: str,
    inputs: Mapping[str, FormulaInput],
    *,
    decision_at: str,
) -> float:
    analysis = analyze_formula(formula)
    data = _prepare_inputs(analysis, inputs, decision_at)
    tree = ast.parse(formula, mode="eval")
    try:
        value = _evaluate(tree, data)
    except ZeroDivisionError as exc:
        raise ResearchAgentError("DSL division by zero") from exc
    if not math.isfinite(value):
        raise ResearchAgentError("DSL produced a non-finite value")
    return value
