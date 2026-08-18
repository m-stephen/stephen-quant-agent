from __future__ import annotations

from stephen_quant.workflows.v41_semantic_alpha import UsageEvent
from stephen_quant.workflows.v44_path_robust_alpha import PathRobustness
from stephen_quant.workflows.v46_orthogonal_search import YearEvidence
from stephen_quant.workflows.v50_market_wide_search import (
    _execution_tiers,
    _incremental_returns,
    _moments,
    _stable,
)


def _path(increment: float, median_sharpe: float = 0.5) -> PathRobustness:
    return PathRobustness(
        year=2022,
        paths=20,
        median_sharpe=median_sharpe,
        lower_quartile_sharpe=0.1,
        positive_return_paths=16,
        mean_path_return=increment,
        worst_path_return=-0.01,
        worst_path_drawdown=-0.02,
        incremental_daily_sharpe=0.8,
        incremental_return=increment,
        portfolio_excess_sharpe=0.8,
        portfolio_excess_return=increment,
        portfolio_drawdown=-0.1,
    )


def test_v50_stability_requires_both_confirmation_years_positive() -> None:
    passed = tuple(
        YearEvidence(year, 200, ic, 0.01, (ic, ic, ic, ic), _path(0.02))
        for year, ic in ((2022, -0.01), (2023, 0.02), (2024, 0.01))
    )
    failed = tuple(
        YearEvidence(year, 200, ic, 0.01, (ic, ic, ic, ic), _path(0.02))
        for year, ic in ((2022, 0.03), (2023, 0.02), (2024, -0.01))
    )
    assert _stable(passed)
    assert not _stable(failed)


def test_v50_tiers_are_only_available_after_decision_day() -> None:
    tiers = {
        "2024-01-02": {
            "size": {"large": ("A",), "mid": ("B",), "small": ("C",)},
            "liquidity": {"high": ("A",), "mid": ("B",), "low": ("C",)},
        }
    }
    result = _execution_tiers(tiers, ("2024-01-02", "2024-01-03"))
    assert result["2024-01-02"]["size"]["large"] == frozenset()
    assert result["2024-01-03"]["size"]["large"] == frozenset({"A"})


def test_v50_dsr_uses_incremental_empirical_moments() -> None:
    events = [
        UsageEvent(f"2024-01-0{index}", 0, value, 0.0, 0.0, True)
        for index, value in enumerate((0.01, -0.02, 0.03, 0.04), start=1)
    ]
    controls = [
        UsageEvent(item.day, item.offset, 0.0, 0.0, 0.0, False) for item in events
    ]
    values = _incremental_returns(events, controls)
    skewness, excess_kurtosis = _moments(values)
    assert values == (0.01, -0.02, 0.03, 0.04)
    assert skewness != 0.0
    assert excess_kurtosis != 0.0
