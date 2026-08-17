from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.v2 import (
    CandidateSignature,
    DiagnosticCode,
    DiagnosticObservation,
    DiagnosticPolicy,
    NoveltyBenchmarkCase,
    NoveltyCode,
    novelty_gate,
    run_cheap_diagnostics,
    run_novelty_benchmark,
)

CONTROL = (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
BASE = (-1.8, -1.1, -0.2, 0.1, 0.8, 0.7, 1.8, 1.7)


def _signature(
    candidate_id: str,
    formula: str,
    values: tuple[float, ...] = BASE,
    exposures: tuple[float, ...] = (0.8, 0.2),
    tags: tuple[str, ...] = ("flow", "demand"),
) -> CandidateSignature:
    return CandidateSignature(candidate_id, formula, values, CONTROL, exposures, tags)


def test_novelty_gate_supports_exact_algebraic_numerical_and_residual_checks() -> None:
    peer = _signature("peer", "mean(amount, 5) + mean(net_inflow_amount, 5)")
    exact = _signature("exact", peer.formula)
    algebraic = _signature("algebraic", "mean(net_inflow_amount, 5) + mean(amount, 5)")
    numerical = _signature(
        "numerical",
        "mean(net_inflow_amount, 20)",
        tuple(value * 1.001 + 0.0001 for value in BASE),
    )
    residual = _signature(
        "residual",
        "mean(large_buy_amount, 5) - mean(large_sell_amount, 5)",
        tuple(value + control * 3 for value, control in zip(BASE, CONTROL, strict=True)),
    )
    assert novelty_gate(exact, (peer,)).code == NoveltyCode.EXACT_AST_DUPLICATE
    assert novelty_gate(algebraic, (peer,)).code == NoveltyCode.ALGEBRAIC_DUPLICATE
    assert novelty_gate(numerical, (peer,)).code == NoveltyCode.NUMERICAL_DUPLICATE
    assert novelty_gate(residual, (peer,)).code == NoveltyCode.RESIDUAL_DUPLICATE


def test_frozen_novelty_benchmark_meets_preregistered_engineering_thresholds() -> None:
    peer = _signature("peer", "mean(amount, 5) + mean(net_inflow_amount, 5)")
    cases = (
        NoveltyBenchmarkCase(_signature("e", peer.formula), (peer,), True, True, False),
        NoveltyBenchmarkCase(
            _signature("a", "mean(net_inflow_amount, 5) + mean(amount, 5)"),
            (peer,),
            True,
            False,
            False,
        ),
        NoveltyBenchmarkCase(
            _signature("n", "mean(net_inflow_amount, 20)", tuple(v * 1.001 for v in BASE)),
            (peer,),
            True,
            False,
            False,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "r",
                "mean(large_buy_amount, 5) - mean(large_sell_amount, 5)",
                tuple(v + c * 3 for v, c in zip(BASE, CONTROL, strict=True)),
            ),
            (peer,),
            True,
            False,
            False,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "valid1",
                "period_return(close, 20)",
                (-0.4, 0.8, -1.2, 1.7, 0.2, -0.7, 0.6, 1.1),
                (0.1, 0.9),
                ("price", "momentum"),
            ),
            (peer,),
            False,
            False,
            True,
        ),
        NoveltyBenchmarkCase(
            _signature(
                "valid2",
                "mean(margin_financing_buy, 20) / (mean(amount, 20) + 1.0)",
                (1.2, -0.4, 0.3, -1.1, 1.5, 0.7, -0.8, 0.1),
                (0.7, -0.3),
                ("margin", "leverage"),
            ),
            (peer,),
            False,
            False,
            True,
        ),
    )
    result = run_novelty_benchmark(cases)
    assert result.exact_duplicate_recall == 1.0
    assert result.empirical_duplicate_precision == 1.0
    assert result.empirical_duplicate_recall == 1.0
    assert result.workload_reduction >= 0.50
    assert result.known_valid_recall == 1.0
    assert all(decision.code != "" for decision in result.decisions)


def _diagnostic_fixture() -> tuple[DiagnosticObservation, ...]:
    rows: list[DiagnosticObservation] = []
    for date_index in range(4):
        for instrument_index in range(10):
            value = float(instrument_index - 4.5) + date_index * 0.05
            rows.append(
                DiagnosticObservation(
                    date=f"2024-01-{date_index + 2:02d}",
                    instrument=f"stock_{instrument_index:02d}",
                    value=value,
                    forward_return=value * 0.001 + (instrument_index % 2) * 0.00001,
                    residual_return=value * 0.0008 + (instrument_index % 3) * 0.00001,
                    stale_days=0,
                    regime="up" if date_index < 2 else "down",
                    industry="A" if instrument_index < 5 else "B",
                    style_exposures=(("size", float(instrument_index)), ("volatility", -value)),
                    holding_returns=(value * 0.001, value * 0.0007, value * 0.0003),
                )
            )
    return tuple(rows)


def test_cheap_diagnostics_cover_required_metrics_and_pass_good_fixture() -> None:
    rows = _diagnostic_fixture()
    report = run_cheap_diagnostics(rows, DiagnosticPolicy(expected_observations=len(rows)))
    assert report.coverage == 1.0
    assert report.missingness == 0.0
    assert report.mean_rank_ic > 0.99
    assert report.residual_ic > 0.99
    assert len(report.quantile_returns) == 5
    assert report.long_return > report.short_return
    assert report.gross_spread > 0
    assert len(report.holding_decay) == 3
    assert {name for name, _ in report.style_exposures} == {"size", "volatility"}
    assert report.net_spread_after_cost > 0
    assert report.codes == (DiagnosticCode.PASS,)


def test_cheap_diagnostics_return_typed_failure_codes() -> None:
    rows = list(_diagnostic_fixture())
    degraded = tuple(
        replace(
            row,
            value=None if index < 10 else row.value,
            forward_return=-row.forward_return,
            residual_return=-row.residual_return,
            stale_days=2,
        )
        for index, row in enumerate(rows)
    )
    report = run_cheap_diagnostics(
        degraded,
        DiagnosticPolicy(
            expected_observations=len(rows),
            maximum_stale_fraction=0.1,
            cost_bps=10_000,
        ),
    )
    assert DiagnosticCode.LOW_COVERAGE in report.codes
    assert DiagnosticCode.HIGH_MISSINGNESS in report.codes
    assert DiagnosticCode.STALE_SIGNAL in report.codes
    assert DiagnosticCode.FLAT_QUANTILES in report.codes
    assert DiagnosticCode.COST_ERASED in report.codes


def test_novelty_gate_rejects_malformed_fixture_before_comparison() -> None:
    malformed = replace(_signature("bad", "mean(amount, 5)"), fixture_values=(1.0, 2.0))
    with pytest.raises(ValueError, match="equal length"):
        novelty_gate(malformed, ())
