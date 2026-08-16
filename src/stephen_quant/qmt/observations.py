from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from stephen_quant.baseline import BaselineObservation
from stephen_quant.factors import FactorDefinition, compute_factor

from .models import QmtDailyBar, QmtDataError

MARKET_TIMEZONE = "+08:00"


def _at(day: str, clock: str) -> str:
    return f"{day}T{clock}{MARKET_TIMEZONE}"


def _date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QmtDataError(f"{field} must be an ISO date") from exc


def build_qmt_factor_observations(
    bars: Sequence[QmtDailyBar],
    definition: FactorDefinition,
    *,
    test_start: str,
    test_end: str,
    adv_lookback: int = 20,
) -> tuple[BaselineObservation, ...]:
    """Build prior-close signals and next-open execution returns from a strict panel."""

    start, end = _date(test_start, "test_start"), _date(test_end, "test_end")
    if start > end:
        raise QmtDataError("test_start must not be after test_end")
    if adv_lookback < 1:
        raise QmtDataError("adv_lookback must be positive")
    unsupported = set(definition.required_fields) - {"open", "high", "low", "close", "volume", "amount"}
    if unsupported:
        raise QmtDataError(
            f"factor {definition.key} requires unsupported QMT fields: {sorted(unsupported)}"
        )

    by_instrument: dict[str, dict[str, QmtDailyBar]] = defaultdict(dict)
    all_dates: set[str] = set()
    for bar in bars:
        by_instrument[bar.instrument][bar.trade_date] = bar
        all_dates.add(bar.trade_date)
    instruments = tuple(sorted(by_instrument))
    ordered_dates = sorted(all_dates)
    execution_indexes = [
        index
        for index, day in enumerate(ordered_dates[:-1])
        if start <= date.fromisoformat(day) <= end
    ]
    if not execution_indexes:
        raise QmtDataError("test window contains no executable trading dates")
    history = max(definition.minimum_observations, adv_lookback)
    first_required = execution_indexes[0] - history
    if first_required < 0:
        raise QmtDataError(
            f"test window needs at least {history} complete prior trading bars"
        )
    required_dates = ordered_dates[first_required : execution_indexes[-1] + 2]
    missing = [
        (instrument, day)
        for instrument in instruments
        for day in required_dates
        if day not in by_instrument[instrument]
    ]
    if missing:
        preview = ", ".join(f"{instrument}@{day}" for instrument, day in missing[:5])
        raise QmtDataError(f"incomplete QMT panel; missing {len(missing)} bars: {preview}")

    observations: list[BaselineObservation] = []
    for execution_index in execution_indexes:
        local_execution_index = execution_index - first_required
        signal_index = local_execution_index - 1
        execution_day = ordered_dates[execution_index]
        return_end_day = ordered_dates[execution_index + 1]
        for instrument in instruments:
            series = [by_instrument[instrument][day] for day in required_dates]
            signal_bar = series[signal_index]
            execution_bar = series[local_execution_index]
            return_end_bar = series[local_execution_index + 1]
            adv_window = series[
                local_execution_index - adv_lookback : local_execution_index
            ]
            average_daily_value = sum(item.amount for item in adv_window) / adv_lookback
            if average_daily_value <= 0:
                raise QmtDataError(
                    f"non-positive ADV for {instrument} before {execution_day}"
                )
            data = {
                field: [getattr(item, field) for item in series]
                for field in definition.required_fields
            }
            availability = {
                field: [_at(item.trade_date, "15:01:00") for item in series]
                for field in definition.required_fields
            }
            signal = compute_factor(
                definition,
                data,
                availability,
                as_of_index=signal_index,
                observation_times=[_at(item.trade_date, "15:00:00") for item in series],
                decision_at=_at(execution_day, "09:30:00"),
            )
            observations.append(
                BaselineObservation(
                    instrument=instrument,
                    signal=signal.value,
                    signal_at=_at(signal_bar.trade_date, "15:00:00"),
                    signal_available_at=_at(signal_bar.trade_date, "15:01:00"),
                    average_daily_value=average_daily_value,
                    liquidity_available_at=_at(signal_bar.trade_date, "15:01:00"),
                    execution_at=_at(execution_bar.trade_date, "09:30:00"),
                    return_end_at=_at(return_end_day, "09:30:00"),
                    forward_return=return_end_bar.open / execution_bar.open - 1.0,
                )
            )
    return tuple(observations)
