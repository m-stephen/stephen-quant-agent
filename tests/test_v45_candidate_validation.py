import pytest

from stephen_quant.workflows.v44_path_robust_alpha import PathRobustness
from stephen_quant.workflows.v45_candidate_validation import (
    StressResult,
    V45Config,
    primary_result,
)


def _metrics() -> PathRobustness:
    return PathRobustness(2025, 20, 1.0, 0.2, 18, 0.02, -0.01, -0.03, 1.0, 0.02, 1.1, 0.03, -0.04)


def _result(*, nav: float = 3_000_000.0, multiplier: float = 1.0, breadth: int = 10) -> StressResult:
    return StressResult(nav, multiplier, breadth, _metrics(), 0.0, 0.1, "trial", 1)


def test_v45_protocol_and_stress_grid_are_frozen() -> None:
    V45Config().validate()
    with pytest.raises(ValueError, match="validation year"):
        V45Config(validation_year=2024).validate()
    with pytest.raises(ValueError, match="NAV stress"):
        V45Config(stress_navs=(3_000_000.0,)).validate()
    with pytest.raises(ValueError, match="cost stress"):
        V45Config(stress_cost_multipliers=(1.0,)).validate()
    with pytest.raises(ValueError, match="breadth stress"):
        V45Config(stress_breadths=(10,)).validate()


def test_primary_cell_is_unique_and_frozen() -> None:
    assert primary_result((_result(), _result(multiplier=2.0))).primary
    with pytest.raises(ValueError, match="exactly one"):
        primary_result((_result(multiplier=2.0),))
    with pytest.raises(ValueError, match="exactly one"):
        primary_result((_result(), _result()))
