from __future__ import annotations

from stephen_quant.qmt import (
    ConfirmedFundamentalObservation,
    QmtDailyBar,
    build_fundamental_factor_observations,
)


def _fixture(day: str, *, reverse: bool = False):
    bars = []
    fundamentals = []
    for index in range(6):
        instrument = f"00000{index + 1}.SZ"
        raw_close = 10.0 + index
        factor = 2.5
        bars.append(
            QmtDailyBar(
                instrument=instrument,
                trade_date=day,
                open=raw_close * factor,
                high=raw_close * factor,
                low=raw_close * factor,
                close=raw_close * factor,
                volume=1000,
                amount=10000,
                adjustment_factor=factor,
            )
        )
        quality = 6 - index if reverse else index + 1
        fundamentals.append(
            ConfirmedFundamentalObservation(
                decision_date=day,
                available_at=f"{day}T15:01:00+08:00",
                instrument=instrument,
                industry="银行" if index < 3 else "制造",
                total_shares=(index + 1) * 100_000_000,
                book_value_per_share=float(quality + 4),
                earnings_per_share=float(quality) / 10,
                net_margin_pct=float(quality),
                revenue_growth_pct=1.0,
                profit_growth_pct=1.0,
            )
        )
    return bars, fundamentals


def test_fundamental_factors_restore_raw_price_and_neutralize_same_day() -> None:
    bars, fundamentals = _fixture("2024-01-02")

    rows, audit = build_fundamental_factor_observations(
        bars, fundamentals, minimum_industry_members=3
    )

    assert len(rows) == 6
    assert rows[0].raw_close == 10.0
    assert rows[0].market_cap == 1_000_000_000
    assert set(rows[0].components) == {
        "book_to_price",
        "earnings_yield",
        "profitability",
        "net_margin",
    }
    assert audit.component_valid_rows["book_to_price"] == 6
    assert abs(sum(row.components["net_margin"] for row in rows)) < 1e-10


def test_future_cross_section_cannot_change_prior_day_factor() -> None:
    first_bars, first_fundamentals = _fixture("2024-01-02")
    future_bars, future_fundamentals = _fixture("2024-01-03", reverse=True)
    first_only, _ = build_fundamental_factor_observations(
        first_bars, first_fundamentals, minimum_industry_members=3
    )
    combined, _ = build_fundamental_factor_observations(
        first_bars + future_bars,
        first_fundamentals + future_fundamentals,
        minimum_industry_members=3,
    )

    prior_from_combined = tuple(row for row in combined if row.decision_date == "2024-01-02")
    assert prior_from_combined == first_only


def test_nonpositive_book_value_is_excluded_only_from_dependent_components() -> None:
    bars, fundamentals = _fixture("2024-01-02")
    bad = fundamentals[0]
    fundamentals[0] = ConfirmedFundamentalObservation(
        **{**bad.__dict__, "book_value_per_share": -1.0}
    )

    rows, audit = build_fundamental_factor_observations(
        bars, fundamentals, minimum_industry_members=3
    )
    first = next(row for row in rows if row.instrument == "000001.SZ")

    assert "book_to_price" not in first.components
    assert "profitability" not in first.components
    assert "earnings_yield" in first.components
    assert audit.component_valid_rows["book_to_price"] == 5
