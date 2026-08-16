from __future__ import annotations

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.qmt import QmtDataError, combine_qmt_factor_observations


def _row(instrument: str, signal: float, forward_return: float) -> BaselineObservation:
    return BaselineObservation(
        instrument=instrument,
        signal=signal,
        signal_at="2024-01-02T15:00:00+08:00",
        signal_available_at="2024-01-02T15:01:00+08:00",
        average_daily_value=1_000_000,
        liquidity_available_at="2024-01-02T15:01:00+08:00",
        execution_at="2024-01-03T09:30:00+08:00",
        return_end_at="2024-01-04T09:30:00+08:00",
        forward_return=forward_return,
    )


def test_composite_uses_direction_adjusted_cross_sectional_ranks() -> None:
    components = {
        "volume": (_row("A", 3.0, 0.1), _row("B", 1.0, -0.1)),
        "risk": (_row("A", 2.0, 0.1), _row("B", 1.0, -0.1)),
    }
    combined = combine_qmt_factor_observations(
        components,
        {"volume": 0.75, "risk": 0.25},
        {"volume": 1, "risk": -1},
    )

    scores = {row.instrument: row.signal for row in combined}
    assert scores == {"A": 0.75, "B": 0.25}
    assert all(row.signal_available_at < row.execution_at for row in combined)


def test_composite_rejects_mismatched_panels() -> None:
    with pytest.raises(QmtDataError, match="same observation panel"):
        combine_qmt_factor_observations(
            {"left": (_row("A", 1.0, 0.1),), "right": (_row("B", 1.0, 0.1),)},
            {"left": 0.5, "right": 0.5},
            {"left": 1, "right": 1},
        )
