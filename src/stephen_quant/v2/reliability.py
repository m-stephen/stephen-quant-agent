from __future__ import annotations

from dataclasses import asdict, dataclass

from .novelty import CandidateSignature, NoveltyBenchmarkCase, run_novelty_benchmark


@dataclass(frozen=True)
class ReliabilityCalibration:
    exact_duplicate_recall: float
    duplicate_precision: float
    duplicate_recall: float
    known_valid_recall: float
    workload_reduction: float
    false_promotion_rate: float
    decision: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _signature(
    candidate_id: str,
    formula: str,
    values: tuple[float, ...],
    tags: tuple[str, ...],
) -> CandidateSignature:
    return CandidateSignature(
        candidate_id,
        formula,
        values,
        (1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        (values[0], values[-1]),
        tags,
    )


def run_reliability_calibration() -> ReliabilityCalibration:
    """Frozen controls proving the novelty gate rejects copies but keeps signal."""

    base = _signature(
        "library_flow",
        "mean(net_inflow_amount, 5) / (mean(amount, 5) + 1.0)",
        (0.1, 0.4, -0.2, 0.8, 0.3, -0.5),
        ("flow", "liquidity"),
    )
    cases = (
        NoveltyBenchmarkCase(
            _signature("exact", base.formula, base.fixture_values, base.semantic_tags),
            (base,),
            True,
            True,
            False,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "numerical_copy",
                "mean(large_buy_amount, 5) / (mean(amount, 5) + 1.0)",
                tuple(value * 2 for value in base.fixture_values),
                ("large_flow", "liquidity"),
            ),
            (base,),
            True,
            False,
            False,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "injected_signal",
                "period_return(close, 20)",
                (-0.4, 0.7, 0.1, -0.8, 0.9, 0.2),
                ("price", "continuation"),
            ),
            (base,),
            False,
            False,
            True,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "negative_control",
                "volatility(close, 20)",
                (0.3, -0.1, 0.8, 0.2, -0.7, 0.5),
                ("risk", "negative_control"),
            ),
            (base,),
            False,
            False,
            True,
        ),
    )
    benchmark = run_novelty_benchmark(cases)
    false_promotions = sum(
        decision.is_novel and case.expected_duplicate
        for decision, case in zip(benchmark.decisions, cases, strict=True)
    )
    false_promotion_rate = false_promotions / sum(case.expected_duplicate for case in cases)
    passed = (
        benchmark.exact_duplicate_recall == 1.0
        and benchmark.empirical_duplicate_precision == 1.0
        and benchmark.empirical_duplicate_recall == 1.0
        and benchmark.known_valid_recall == 1.0
        and false_promotion_rate == 0.0
    )
    return ReliabilityCalibration(
        benchmark.exact_duplicate_recall,
        benchmark.empirical_duplicate_precision,
        benchmark.empirical_duplicate_recall,
        benchmark.known_valid_recall,
        benchmark.workload_reduction,
        false_promotion_rate,
        "PASS" if passed else "FAIL",
    )
