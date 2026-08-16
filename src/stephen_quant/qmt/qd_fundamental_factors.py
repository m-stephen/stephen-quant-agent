from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from .models import QmtDailyBar, QmtDataError
from .qd_fundamentals import ConfirmedFundamentalObservation

QD_FUNDAMENTAL_FACTOR_VERSION = "qd-value-quality-neutralized-1.0.0"
FUNDAMENTAL_COMPONENTS = (
    "book_to_price",
    "earnings_yield",
    "profitability",
    "net_margin",
)


@dataclass(frozen=True)
class FundamentalFactorObservation:
    decision_date: str
    available_at: str
    instrument: str
    raw_close: float
    market_cap: float
    components: dict[str, float]


@dataclass(frozen=True)
class FundamentalFactorAudit:
    method_version: str
    input_rows: int
    output_rows: int
    missing_price_rows: int
    invalid_metadata_rows: int
    component_valid_rows: dict[str, int]


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _neutralize(
    rows: Sequence[tuple[str, str, float, float]],
    *,
    minimum_industry_members: int,
    winsor_tail: float,
) -> dict[str, float]:
    values = [item[2] for item in rows]
    lower = _quantile(values, winsor_tail)
    upper = _quantile(values, 1 - winsor_tail)
    clipped = {instrument: min(max(value, lower), upper) for instrument, _, value, _ in rows}
    global_mean = sum(clipped.values()) / len(clipped)
    industries: dict[str, list[str]] = defaultdict(list)
    for instrument, industry, _, _ in rows:
        industries[industry].append(instrument)
    industry_means = {
        industry: sum(clipped[item] for item in members) / len(members)
        for industry, members in industries.items()
        if len(members) >= minimum_industry_members
    }
    residual = {
        instrument: clipped[instrument] - industry_means.get(industry, global_mean)
        for instrument, industry, _, _ in rows
    }
    log_size = {instrument: math.log(market_cap) for instrument, _, _, market_cap in rows}
    x_mean = sum(log_size.values()) / len(log_size)
    y_mean = sum(residual.values()) / len(residual)
    denominator = sum((value - x_mean) ** 2 for value in log_size.values())
    slope = (
        sum(
            (log_size[instrument] - x_mean) * (residual[instrument] - y_mean)
            for instrument in residual
        )
        / denominator
        if denominator > 0
        else 0.0
    )
    return {
        instrument: residual[instrument] - y_mean - slope * (log_size[instrument] - x_mean)
        for instrument in residual
    }


def build_fundamental_factor_observations(
    bars: Sequence[QmtDailyBar],
    fundamentals: Sequence[ConfirmedFundamentalObservation],
    *,
    minimum_industry_members: int = 5,
    winsor_tail: float = 0.01,
) -> tuple[tuple[FundamentalFactorObservation, ...], FundamentalFactorAudit]:
    if minimum_industry_members < 1:
        raise QmtDataError("minimum_industry_members must be positive")
    if not 0 <= winsor_tail < 0.5:
        raise QmtDataError("winsor_tail must be in [0, 0.5)")
    prices = {(bar.trade_date, bar.instrument): bar for bar in bars}
    prepared: dict[str, list[tuple[ConfirmedFundamentalObservation, float, float]]] = defaultdict(list)
    missing_price = 0
    invalid_metadata = 0
    for row in fundamentals:
        bar = prices.get((row.decision_date, row.instrument))
        if bar is None:
            missing_price += 1
            continue
        if (
            row.industry is None
            or row.total_shares is None
            or row.total_shares <= 0
            or bar.adjustment_factor <= 0
        ):
            invalid_metadata += 1
            continue
        raw_close = bar.close / bar.adjustment_factor
        market_cap = raw_close * row.total_shares
        if not math.isfinite(raw_close) or raw_close <= 0 or not math.isfinite(market_cap):
            invalid_metadata += 1
            continue
        prepared[row.decision_date].append((row, raw_close, market_cap))

    output: list[FundamentalFactorObservation] = []
    valid_counts = {component: 0 for component in FUNDAMENTAL_COMPONENTS}
    for decision_date in sorted(prepared):
        day_rows = prepared[decision_date]
        raw_components: dict[str, list[tuple[str, str, float, float]]] = {
            component: [] for component in FUNDAMENTAL_COMPONENTS
        }
        for row, raw_close, market_cap in day_rows:
            if row.book_value_per_share is not None and row.book_value_per_share > 0:
                raw_components["book_to_price"].append(
                    (row.instrument, row.industry or "", row.book_value_per_share / raw_close, market_cap)
                )
                if row.earnings_per_share is not None:
                    raw_components["profitability"].append(
                        (
                            row.instrument,
                            row.industry or "",
                            row.earnings_per_share / row.book_value_per_share,
                            market_cap,
                        )
                    )
            if row.earnings_per_share is not None:
                raw_components["earnings_yield"].append(
                    (row.instrument, row.industry or "", row.earnings_per_share / raw_close, market_cap)
                )
            if row.net_margin_pct is not None:
                raw_components["net_margin"].append(
                    (row.instrument, row.industry or "", row.net_margin_pct, market_cap)
                )
        neutralized = {
            component: _neutralize(
                values,
                minimum_industry_members=minimum_industry_members,
                winsor_tail=winsor_tail,
            )
            for component, values in raw_components.items()
            if len(values) >= 3
        }
        by_instrument = {row.instrument: (row, close, cap) for row, close, cap in day_rows}
        for instrument in sorted(by_instrument):
            components = {
                component: values[instrument]
                for component, values in neutralized.items()
                if instrument in values
            }
            for component in components:
                valid_counts[component] += 1
            if not components:
                continue
            row, raw_close, market_cap = by_instrument[instrument]
            output.append(
                FundamentalFactorObservation(
                    decision_date=decision_date,
                    available_at=row.available_at,
                    instrument=instrument,
                    raw_close=raw_close,
                    market_cap=market_cap,
                    components=components,
                )
            )
    audit = FundamentalFactorAudit(
        method_version=QD_FUNDAMENTAL_FACTOR_VERSION,
        input_rows=len(fundamentals),
        output_rows=len(output),
        missing_price_rows=missing_price,
        invalid_metadata_rows=invalid_metadata,
        component_valid_rows=dict(sorted(valid_counts.items())),
    )
    return tuple(output), audit
