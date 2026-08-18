import pytest

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.v41_semantic_alpha import (
    RegimeState,
    UsageEvent,
    UsageSpec,
    V41Config,
    evaluate_usage_events,
)
from stephen_quant.workflows.v44_path_robust_alpha import (
    PathRobustness,
    RobustCandidate,
    V44Config,
    research_eligible,
    select_robust_candidate,
    summarize_paths,
)


def _metric(
    year: int,
    *,
    median_sharpe: float = 1.0,
    lower_quartile_sharpe: float = 0.2,
    positive_paths: int = 18,
) -> PathRobustness:
    return PathRobustness(
        year,
        20,
        median_sharpe,
        lower_quartile_sharpe,
        positive_paths,
        0.02,
        -0.01,
        -0.03,
        1.0,
        0.02,
        1.1,
        0.05,
        -0.04,
    )


def _candidate(name: str, q25: float) -> RobustCandidate:
    metrics = (_metric(2022, lower_quartile_sharpe=q25), _metric(2023, lower_quartile_sharpe=q25))
    return RobustCandidate(name, "AVOID", 10, "mixed", metrics, True, f"trial-{name}", 1)


def test_v44_protocol_is_frozen() -> None:
    V44Config().validate()
    with pytest.raises(ValueError, match="windows"):
        V44Config(final_year=2025).validate()
    with pytest.raises(ValueError, match="regime grid"):
        V44Config(regimes=("all",)).validate()


def test_research_gate_requires_both_years_and_all_path_conditions() -> None:
    config = V44Config()
    assert research_eligible((_metric(2022), _metric(2023)), config)
    assert not research_eligible((_metric(2022),), config)
    assert not research_eligible(
        (_metric(2022), _metric(2023, lower_quartile_sharpe=0.0)), config
    )
    assert not research_eligible((_metric(2022), _metric(2023, positive_paths=15)), config)


def test_selection_prefers_worst_year_quartile_not_peak_sharpe() -> None:
    selected = select_robust_candidate((_candidate("fragile", 0.1), _candidate("robust", 0.4)))
    assert selected.candidate_id == "robust"
    with pytest.raises(ValueError, match="no candidate"):
        select_robust_candidate(
            (
                RobustCandidate(
                    "rejected", "BUY", 5, "all", (_metric(2022), _metric(2023)), False, "trial", 1
                ),
            )
        )


def test_path_summary_subtracts_matched_control_and_rejects_grid_drift() -> None:
    candidate = []
    control = []
    for offset in range(20):
        for index in range(3):
            day = f"2022-{offset + 1:02d}-{index + 1:02d}"
            candidate.append(UsageEvent(day, offset, 0.002 + index * 0.001, 0.0, 0.0, True))
            control.append(UsageEvent(day, offset, 0.001, 0.0, 0.0, True))
    result = summarize_paths(
        2022,
        tuple(candidate),
        tuple(control),
        horizon=20,
        portfolio_sharpe=1.0,
        portfolio_return=0.1,
        portfolio_drawdown=-0.05,
    )
    assert result.paths == 20
    assert result.positive_return_paths == 20
    assert result.incremental_return > 0
    with pytest.raises(ValueError, match="grids differ"):
        summarize_paths(
            2022,
            tuple(candidate[:-1]),
            tuple(control),
            horizon=20,
            portfolio_sharpe=1.0,
            portfolio_return=0.1,
            portfolio_drawdown=-0.05,
        )


def test_inactive_regime_can_hold_equal_weight_overlay_instead_of_cash() -> None:
    day = "2022-01-04"
    prior = "2022-01-03"
    rows = tuple(
        EvaluationObservation(
            timestamp=day,
            instrument=f"00000{index}.SZ",
            factor_value=float(index),
            factor_available_at=prior,
            label_start_at=day,
            label_end_at="2022-02-01",
            forward_return=0.01 * index,
            horizon="20d",
            subperiod="2022",
            regime="unspecified",
        )
        for index in range(1, 5)
    )
    bars = {
        row.instrument: {
            prior: QmtDailyBar(
                row.instrument, prior, 10, 10, 10, 10, 1_000_000, 100_000_000
            )
        }
        for row in rows
    }
    regimes = {day: RegimeState(day, "risk_on", 0, 0, 0, 0, 1, prior)}
    cash, _ = evaluate_usage_events(
        rows,
        rows,
        UsageSpec("AVOID", 1, "mixed"),
        horizon=1,
        nav=3_000_000,
        bars=bars,
        calendar=(prior, day),
        regimes=regimes,
        config=V41Config(),
    )
    overlay, _ = evaluate_usage_events(
        rows,
        rows,
        UsageSpec("AVOID", 1, "mixed"),
        horizon=1,
        nav=3_000_000,
        bars=bars,
        calendar=(prior, day),
        regimes=regimes,
        config=V41Config(),
        hold_equal_weight_when_inactive=True,
    )
    assert cash[0].excess_return < 0
    assert overlay[0].excess_return > cash[0].excess_return
