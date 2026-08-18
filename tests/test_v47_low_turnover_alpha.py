from stephen_quant.evaluation import EvaluationObservation
from stephen_quant.qmt import QmtDailyBar
from stephen_quant.workflows.v41_semantic_alpha import V41Config
from stephen_quant.workflows.v47_low_turnover_alpha import (
    BUFFER_RANKS,
    COST_MULTIPLIERS,
    SIGNAL_STRUCTURES,
    V47Config,
    evaluate_buffered_avoid_accounting_events,
    evaluate_buffered_avoid_events,
)


def _row(day: str, instrument: str, factor: float, forward: float = 0.01) -> EvaluationObservation:
    return EvaluationObservation(
        timestamp=f"{day}T09:30:00+08:00",
        instrument=instrument,
        factor_value=factor,
        factor_available_at=f"{day}T09:25:00+08:00",
        label_start_at=f"{day}T09:30:00+08:00",
        label_end_at=f"{day}T15:00:00+08:00",
        forward_return=forward,
        horizon="1d",
        subperiod="test",
        regime="all",
    )


def _bar(day: str, instrument: str) -> QmtDailyBar:
    return QmtDailyBar(
        instrument=instrument,
        trade_date=day,
        open=10.0,
        high=10.5,
        low=9.5,
        close=10.0,
        volume=1_000_000.0,
        amount=10_000_000.0,
    )


def test_v47_grid_is_exactly_twelve_predeclared_trials() -> None:
    config = V47Config()
    config.validate()
    assert len(SIGNAL_STRUCTURES) * len(BUFFER_RANKS) * len(COST_MULTIPLIERS) == 12


def test_rank_buffer_retains_borderline_holding_and_reduces_turnover() -> None:
    calendar = ("2025-01-01", "2025-01-02", "2025-01-03")
    instruments = ("A", "B", "C", "D")
    rows = (
        *(_row("2025-01-02", name, value) for name, value in zip(instruments, (0, 1, 2, 3))),
        *(_row("2025-01-03", name, value) for name, value in zip(instruments, (0, 2, 1, 3))),
    )
    bars = {
        name: {day: _bar(day, name) for day in calendar}
        for name in instruments
    }
    config = V41Config(
        commission_bps=0,
        sell_tax_bps=0,
        slippage_bps=0,
        impact_bps=0,
        participation_rate=1.0,
    )
    plain, _ = evaluate_buffered_avoid_events(
        rows,
        breadth=2,
        buffer_ranks=0,
        horizon=1,
        nav=1_000_000,
        bars=bars,
        calendar=calendar,
        config=config,
    )
    buffered, _ = evaluate_buffered_avoid_events(
        rows,
        breadth=2,
        buffer_ranks=1,
        horizon=1,
        nav=1_000_000,
        bars=bars,
        calendar=calendar,
        config=config,
    )
    assert buffered[-1].turnover < plain[-1].turnover


def test_accounting_components_reconcile_to_legacy_excess_event() -> None:
    calendar = ("2025-01-01", "2025-01-02")
    instruments = ("A", "B", "C", "D")
    rows = tuple(
        _row("2025-01-02", name, value, forward)
        for name, value, forward in zip(
            instruments,
            (0, 1, 2, 3),
            (-0.02, -0.01, 0.01, 0.02),
            strict=True,
        )
    )
    bars = {name: {day: _bar(day, name) for day in calendar} for name in instruments}
    config = V41Config(
        commission_bps=3,
        sell_tax_bps=5,
        slippage_bps=5,
        impact_bps=10,
        participation_rate=1.0,
    )
    accounting, _ = evaluate_buffered_avoid_accounting_events(
        rows,
        breadth=2,
        buffer_ranks=1,
        horizon=1,
        nav=1_000_000,
        bars=bars,
        calendar=calendar,
        config=config,
    )
    legacy, _ = evaluate_buffered_avoid_events(
        rows,
        breadth=2,
        buffer_ranks=1,
        horizon=1,
        nav=1_000_000,
        bars=bars,
        calendar=calendar,
        config=config,
    )

    assert len(accounting) == len(legacy) == 1
    assert accounting[0].net_portfolio_return == (
        accounting[0].gross_portfolio_return - accounting[0].cost_rate
    )
    assert accounting[0].excess_return == legacy[0].excess_return


def test_invalid_buffer_fails_closed() -> None:
    try:
        evaluate_buffered_avoid_events(
            (),
            breadth=2,
            buffer_ranks=3,
            horizon=1,
            nav=1,
            bars={},
            calendar=(),
            config=V41Config(),
        )
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("invalid buffer must fail closed")
