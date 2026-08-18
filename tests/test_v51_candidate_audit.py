from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.qmt.models import QmtDailyBar
from stephen_quant.workflows.v51_candidate_audit import (
    EXECUTION_SCENARIOS,
    SIGNAL_VARIANTS,
    V51Config,
    _execution_config,
    _industry_demean,
    _style_controls,
)


def _row(day: str, instrument: str, value: float) -> EvaluationObservation:
    return EvaluationObservation(
        timestamp=f"{day}T09:30:00+08:00",
        instrument=instrument,
        factor_value=value,
        factor_available_at=f"{day}T09:00:00+08:00",
        label_start_at=f"{day}T09:30:00+08:00",
        label_end_at=f"{day}T15:00:00+08:00",
        forward_return=value / 100,
        horizon="20d",
        subperiod="2024",
        regime="unspecified",
    )


def test_v51_grid_is_exactly_twelve_predeclared_trials() -> None:
    assert len(SIGNAL_VARIANTS) * len(EXECUTION_SCENARIOS) == 12
    assert SIGNAL_VARIANTS == (
        "raw",
        "style_residual",
        "industry_proxy",
        "style_industry_proxy",
    )


def test_v51_config_rejects_gate_relaxation() -> None:
    with pytest.raises(ValueError, match="falsification gates"):
        V51Config(minimum_dsr=0.90).validate()
    with pytest.raises(ValueError, match="path gate"):
        V51Config(minimum_positive_paths=14).validate()


def test_v51_conservative_execution_is_stricter_than_standard() -> None:
    standard = _execution_config("standard", V51Config())
    conservative = _execution_config("conservative", V51Config())
    assert conservative.slippage_bps > standard.slippage_bps
    assert conservative.impact_bps > standard.impact_bps
    assert conservative.participation_rate < standard.participation_rate


def test_v51_industry_proxy_uses_prior_session_label() -> None:
    rows = (_row("2024-01-03", "A", 1.0), _row("2024-01-03", "B", 3.0))
    labels = {("2024-01-02", "A"): "X", ("2024-01-02", "B"): "X"}
    result = _industry_demean(rows, labels=labels, calendar=("2024-01-02", "2024-01-03"))
    assert [item.factor_value for item in result] == [-1.0, 1.0]


def test_v51_style_controls_use_only_bars_before_execution() -> None:
    start = datetime(2023, 12, 1, tzinfo=timezone.utc)
    calendar = tuple((start + timedelta(days=index)).date().isoformat() for index in range(22))
    by_instrument = {
        "A": {
            day: QmtDailyBar("A", day, 10, 11, 9, 10 + index, 1000, 10000)
            for index, day in enumerate(calendar)
        }
    }
    tiers = {
        day: {
            "size": {"large": frozenset({"A"}), "mid": frozenset(), "small": frozenset()},
            "liquidity": {
                "high": frozenset({"A"}),
                "mid": frozenset(),
                "low": frozenset(),
            },
        }
        for day in calendar
    }
    panels = _style_controls(
        (_row(calendar[-1], "A", 1.0),),
        by_instrument=by_instrument,
        calendar=calendar,
        execution_tiers=tiers,
    )
    assert len(panels) == 4
    assert all(len(panel) == 1 for panel in panels)
    # The momentum control ends at the prior session: 30 / 10 - 1.
    assert panels[2][0].factor_value == pytest.approx(2.0)
