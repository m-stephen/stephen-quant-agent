import pytest

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.workflows.v41_semantic_alpha import _daily_metrics
from stephen_quant.workflows.v43_conversion import (
    ConversionConfig,
    MappingResult,
    select_mapping,
)


def _result(*, year: int = 2022, sharpe: float = 1.0, turnover: float = 0.1) -> MappingResult:
    return MappingResult(
        "candidate",
        "AVOID",
        10,
        year,
        sharpe,
        0.1,
        -0.1,
        turnover,
        0.001,
        200,
        "trial",
        1,
    )


def test_mapping_selection_is_2022_only_and_deterministic() -> None:
    selected = select_mapping(
        (
            _result(sharpe=1.0, turnover=0.2),
            MappingResult(**{**_result(sharpe=1.1).__dict__, "candidate_id": "winner"}),
        )
    )
    assert selected.candidate_id == "winner"
    with pytest.raises(ValueError, match="2022"):
        select_mapping((_result(year=2023),))
    with pytest.raises(ValueError, match="finite"):
        select_mapping((_result(sharpe=float("-inf")),))


def test_conversion_windows_and_mapping_grid_are_frozen() -> None:
    ConversionConfig().validate()
    with pytest.raises(ValueError, match="windows"):
        ConversionConfig(confirmation_year=2024).validate()
    with pytest.raises(ValueError, match="identities"):
        ConversionConfig(breadths=(5, 10)).validate()


def test_alternative_panel_semantics_group_timestamp_as_date() -> None:
    rows = tuple(
        EvaluationObservation(
            timestamp="2022-01-04T09:30:00+08:00",
            instrument=f"00000{index}.SZ",
            factor_value=float(index),
            factor_available_at="2022-01-03T18:00:00+08:00",
            label_start_at="2022-01-04T09:30:00+08:00",
            label_end_at="2022-02-01T09:30:00+08:00",
            forward_return=float(index) / 100,
            horizon="20d",
            subperiod="2022",
            regime="unspecified",
        )
        for index in range(1, 6)
    )
    metrics = _daily_metrics(rows)
    assert len(metrics) == 1
    assert metrics[0].day == "2022-01-04"
    assert metrics[0].observations == 5
