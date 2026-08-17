from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from enum import Enum

from stephen_quant.evaluation.metrics import pearson_correlation, spearman_correlation
from stephen_quant.research_agent.dsl import analyze_formula


class NoveltyCode(str, Enum):
    EXACT_AST_DUPLICATE = "EXACT_AST_DUPLICATE"
    ALGEBRAIC_DUPLICATE = "ALGEBRAIC_DUPLICATE"
    NUMERICAL_DUPLICATE = "NUMERICAL_DUPLICATE"
    RESIDUAL_DUPLICATE = "RESIDUAL_DUPLICATE"
    NOVEL = "NOVEL"


@dataclass(frozen=True)
class CandidateSignature:
    candidate_id: str
    formula: str
    fixture_values: tuple[float, ...]
    control_values: tuple[float, ...]
    exposures: tuple[float, ...]
    semantic_tags: tuple[str, ...]

    def validate(self) -> None:
        analyze_formula(self.formula)
        lengths = {len(self.fixture_values), len(self.control_values)}
        if len(lengths) != 1 or next(iter(lengths)) < 4:
            raise ValueError("novelty fixture and control values require equal length >= 4")
        if not self.exposures or not self.semantic_tags:
            raise ValueError("novelty signature requires exposures and semantic tags")
        numeric = (*self.fixture_values, *self.control_values, *self.exposures)
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("novelty signature contains non-finite values")


@dataclass(frozen=True)
class NoveltyPolicy:
    numerical_rank_threshold: float = 0.995
    numerical_pearson_threshold: float = 0.995
    residual_threshold: float = 0.98
    exposure_cosine_threshold: float = 0.98

    def validate(self) -> None:
        if any(
            not 0 < value <= 1
            for value in (
                self.numerical_rank_threshold,
                self.numerical_pearson_threshold,
                self.residual_threshold,
                self.exposure_cosine_threshold,
            )
        ):
            raise ValueError("novelty thresholds must be in (0, 1]")


DEFAULT_NOVELTY_POLICY = NoveltyPolicy()


@dataclass(frozen=True)
class NoveltyMatch:
    library_candidate_id: str
    code: NoveltyCode
    pearson: float
    rank_correlation: float
    residual_correlation: float
    exposure_cosine: float
    semantic_similarity: float


@dataclass(frozen=True)
class NoveltyDecision:
    candidate_id: str
    is_novel: bool
    code: NoveltyCode
    matches: tuple[NoveltyMatch, ...]


class _CommutativeNormalizer(ast.NodeTransformer):
    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.op, (ast.Add, ast.Mult)):
            left = ast.dump(node.left, include_attributes=False)
            right = ast.dump(node.right, include_attributes=False)
            if right < left:
                node.left, node.right = node.right, node.left
        return node


def normalized_ast(formula: str) -> str:
    analyze_formula(formula)
    tree = _CommutativeNormalizer().visit(ast.parse(formula, mode="eval"))
    ast.fix_missing_locations(tree)
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


def _residual(values: tuple[float, ...], control: tuple[float, ...]) -> tuple[float, ...]:
    x_mean = sum(control) / len(control)
    y_mean = sum(values) / len(values)
    denominator = sum((value - x_mean) ** 2 for value in control)
    if denominator == 0:
        return tuple(value - y_mean for value in values)
    beta = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(control, values, strict=True)) / denominator
    )
    return tuple(y - (y_mean + beta * (x - x_mean)) for x, y in zip(control, values, strict=True))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return (
        0.0
        if denominator == 0
        else sum(a * b for a, b in zip(left, right, strict=True)) / denominator
    )


def _jaccard(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a | b else 0.0


def novelty_gate(
    candidate: CandidateSignature,
    library: tuple[CandidateSignature, ...],
    policy: NoveltyPolicy = DEFAULT_NOVELTY_POLICY,
) -> NoveltyDecision:
    candidate.validate()
    policy.validate()
    candidate_ast = analyze_formula(candidate.formula).canonical_ast
    candidate_normalized = normalized_ast(candidate.formula)
    matches: list[NoveltyMatch] = []
    for peer in library:
        peer.validate()
        if len(peer.fixture_values) != len(candidate.fixture_values):
            raise ValueError("novelty library fixture length mismatch")
        pearson = pearson_correlation(candidate.fixture_values, peer.fixture_values)
        rank = spearman_correlation(candidate.fixture_values, peer.fixture_values)
        residual = pearson_correlation(
            _residual(candidate.fixture_values, candidate.control_values),
            _residual(peer.fixture_values, peer.control_values),
        )
        exposure = _cosine(candidate.exposures, peer.exposures)
        semantic = _jaccard(candidate.semantic_tags, peer.semantic_tags)
        if candidate_ast == analyze_formula(peer.formula).canonical_ast:
            code = NoveltyCode.EXACT_AST_DUPLICATE
        elif candidate_normalized == normalized_ast(peer.formula):
            code = NoveltyCode.ALGEBRAIC_DUPLICATE
        elif (
            abs(pearson) >= policy.numerical_pearson_threshold
            and abs(rank) >= policy.numerical_rank_threshold
        ):
            code = NoveltyCode.NUMERICAL_DUPLICATE
        elif (
            abs(residual) >= policy.residual_threshold
            and abs(exposure) >= policy.exposure_cosine_threshold
        ):
            code = NoveltyCode.RESIDUAL_DUPLICATE
        else:
            continue
        matches.append(
            NoveltyMatch(peer.candidate_id, code, pearson, rank, residual, exposure, semantic)
        )
    priority = (
        NoveltyCode.EXACT_AST_DUPLICATE,
        NoveltyCode.ALGEBRAIC_DUPLICATE,
        NoveltyCode.NUMERICAL_DUPLICATE,
        NoveltyCode.RESIDUAL_DUPLICATE,
    )
    if matches:
        code = next(item for item in priority if any(match.code == item for match in matches))
        return NoveltyDecision(candidate.candidate_id, False, code, tuple(matches))
    return NoveltyDecision(candidate.candidate_id, True, NoveltyCode.NOVEL, ())


@dataclass(frozen=True)
class NoveltyBenchmarkCase:
    candidate: CandidateSignature
    library: tuple[CandidateSignature, ...]
    expected_duplicate: bool
    exact_duplicate: bool
    known_valid: bool


@dataclass(frozen=True)
class NoveltyBenchmarkResult:
    exact_duplicate_recall: float
    empirical_duplicate_precision: float
    empirical_duplicate_recall: float
    workload_reduction: float
    known_valid_recall: float
    decisions: tuple[NoveltyDecision, ...]


def run_novelty_benchmark(
    cases: tuple[NoveltyBenchmarkCase, ...],
    policy: NoveltyPolicy = DEFAULT_NOVELTY_POLICY,
) -> NoveltyBenchmarkResult:
    if not cases:
        raise ValueError("novelty benchmark requires cases")
    decisions = tuple(novelty_gate(case.candidate, case.library, policy) for case in cases)
    predicted = [not item.is_novel for item in decisions]
    actual = [case.expected_duplicate for case in cases]
    exact_indices = [index for index, case in enumerate(cases) if case.exact_duplicate]
    exact_recall = sum(predicted[index] for index in exact_indices) / len(exact_indices)
    true_positive = sum(p and a for p, a in zip(predicted, actual, strict=True))
    precision = true_positive / max(sum(predicted), 1)
    recall = true_positive / max(sum(actual), 1)
    valid_indices = [index for index, case in enumerate(cases) if case.known_valid]
    valid_recall = sum(not predicted[index] for index in valid_indices) / len(valid_indices)
    return NoveltyBenchmarkResult(
        exact_recall,
        precision,
        recall,
        sum(predicted) / len(predicted),
        valid_recall,
        decisions,
    )
