from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from stephen_quant.baseline import BaselineObservation
from stephen_quant.evaluation import average_ranks
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


def _quantile(values: list[float], probability: float) -> float:
    position = probability * (len(values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    weight = position - lower_index
    return values[lower_index] * (1 - weight) + values[upper_index] * weight


def build_qmt_factor_observations(
    bars: Sequence[QmtDailyBar],
    definition: FactorDefinition,
    *,
    test_start: str,
    test_end: str,
    adv_lookback: int = 20,
    horizon_sessions: int = 1,
    eligible_by_execution_date: dict[str, tuple[str, ...]] | None = None,
) -> tuple[BaselineObservation, ...]:
    """Build prior-close signals and forward open-to-open returns from a strict panel."""

    start, end = _date(test_start, "test_start"), _date(test_end, "test_end")
    if start > end:
        raise QmtDataError("test_start must not be after test_end")
    if adv_lookback < 1:
        raise QmtDataError("adv_lookback must be positive")
    if horizon_sessions < 1:
        raise QmtDataError("horizon_sessions must be positive")
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
        for index, day in enumerate(ordered_dates[:-horizon_sessions])
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
    required_dates = ordered_dates[
        first_required : execution_indexes[-1] + horizon_sessions + 1
    ]
    missing = [
        (instrument, day)
        for instrument in instruments
        for day in required_dates
        if day not in by_instrument[instrument]
    ]
    if missing and eligible_by_execution_date is None:
        preview = ", ".join(f"{instrument}@{day}" for instrument, day in missing[:5])
        raise QmtDataError(f"incomplete QMT panel; missing {len(missing)} bars: {preview}")

    if eligible_by_execution_date is not None:
        normalized_eligibility = {
            day: {instrument.upper() for instrument in members}
            for day, members in eligible_by_execution_date.items()
        }
        dynamic: list[BaselineObservation] = []
        for execution_index in execution_indexes:
            execution_day = ordered_dates[execution_index]
            return_end_day = ordered_dates[execution_index + horizon_sessions]
            eligible = normalized_eligibility.get(execution_day, set())
            recently_eligible: set[str] = set()
            for recent_index in range(
                max(execution_index - horizon_sessions, 0), execution_index + 1
            ):
                recently_eligible.update(
                    normalized_eligibility.get(ordered_dates[recent_index], set())
                )
            history_dates = ordered_dates[execution_index - history : execution_index]
            for instrument in sorted(recently_eligible):
                instrument_bars = by_instrument.get(instrument, {})
                needed = (*history_dates, execution_day, return_end_day)
                if any(day not in instrument_bars for day in needed):
                    continue
                history_series = tuple(instrument_bars[day] for day in history_dates)
                execution_bar = instrument_bars[execution_day]
                return_end_bar = instrument_bars[return_end_day]
                adv_window = history_series[-adv_lookback:]
                average_daily_value = sum(item.amount for item in adv_window) / adv_lookback
                if average_daily_value <= 0:
                    continue
                data = {
                    field: [getattr(item, field) for item in history_series]
                    for field in definition.required_fields
                }
                availability = {
                    field: [_at(item.trade_date, "15:01:00") for item in history_series]
                    for field in definition.required_fields
                }
                signal = compute_factor(
                    definition,
                    data,
                    availability,
                    as_of_index=len(history_series) - 1,
                    observation_times=[
                        _at(item.trade_date, "15:00:00") for item in history_series
                    ],
                    decision_at=_at(execution_day, "09:30:00"),
                )
                signal_bar = history_series[-1]
                dynamic.append(
                    BaselineObservation(
                        instrument=instrument,
                        signal=signal.value,
                        signal_at=_at(signal_bar.trade_date, "15:00:00"),
                        signal_available_at=_at(signal_bar.trade_date, "15:01:00"),
                        average_daily_value=average_daily_value,
                        liquidity_available_at=_at(signal_bar.trade_date, "15:01:00"),
                        execution_at=_at(execution_day, "09:30:00"),
                        return_end_at=_at(return_end_day, "09:30:00"),
                        forward_return=return_end_bar.open / execution_bar.open - 1.0,
                        can_buy_open=execution_bar.can_buy_open,
                        can_sell_open=execution_bar.can_sell_open,
                        tradability_reason=execution_bar.tradability_reason,
                        eligible=instrument in eligible,
                    )
                )
        if not dynamic:
            raise QmtDataError("dynamic universe produced no factor observations")
        return tuple(dynamic)

    series_by_instrument = {
        instrument: tuple(by_instrument[instrument][day] for day in required_dates)
        for instrument in instruments
    }
    data_by_instrument = {
        instrument: {
            field: [getattr(item, field) for item in series]
            for field in definition.required_fields
        }
        for instrument, series in series_by_instrument.items()
    }
    availability_by_instrument = {
        instrument: {
            field: [_at(item.trade_date, "15:01:00") for item in series]
            for field in definition.required_fields
        }
        for instrument, series in series_by_instrument.items()
    }
    observation_times_by_instrument = {
        instrument: [_at(item.trade_date, "15:00:00") for item in series]
        for instrument, series in series_by_instrument.items()
    }

    observations: list[BaselineObservation] = []
    for execution_index in execution_indexes:
        local_execution_index = execution_index - first_required
        signal_index = local_execution_index - 1
        execution_day = ordered_dates[execution_index]
        return_end_day = ordered_dates[execution_index + horizon_sessions]
        for instrument in instruments:
            series = series_by_instrument[instrument]
            signal_bar = series[signal_index]
            execution_bar = series[local_execution_index]
            return_end_bar = series[local_execution_index + horizon_sessions]
            adv_window = series[
                local_execution_index - adv_lookback : local_execution_index
            ]
            average_daily_value = sum(item.amount for item in adv_window) / adv_lookback
            if average_daily_value <= 0:
                raise QmtDataError(
                    f"non-positive ADV for {instrument} before {execution_day}"
                )
            signal = compute_factor(
                definition,
                data_by_instrument[instrument],
                availability_by_instrument[instrument],
                as_of_index=signal_index,
                observation_times=observation_times_by_instrument[instrument],
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
                    can_buy_open=execution_bar.can_buy_open,
                    can_sell_open=execution_bar.can_sell_open,
                    tradability_reason=execution_bar.tradability_reason,
                    eligible=True,
                )
            )
    return tuple(observations)


def combine_qmt_factor_observations(
    components: dict[str, Sequence[BaselineObservation]],
    weights: dict[str, float],
    directions: dict[str, int],
) -> tuple[BaselineObservation, ...]:
    """Combine direction-adjusted cross-sectional ranks without fitting global transforms."""

    if not components or set(components) != set(weights) or set(components) != set(directions):
        raise QmtDataError("components, weights, and directions must have identical non-empty keys")
    if any(weight < 0 for weight in weights.values()):
        raise QmtDataError("composite weights cannot be negative")
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise QmtDataError("composite weights must have positive total weight")
    if any(direction not in {-1, 1} for direction in directions.values()):
        raise QmtDataError("component directions must be -1 or 1")

    by_component: dict[str, dict[tuple[str, str], BaselineObservation]] = {}
    for name, rows in components.items():
        indexed = {(row.execution_at, row.instrument): row for row in rows}
        if len(indexed) != len(rows):
            raise QmtDataError(f"duplicate composite observation key in {name}")
        by_component[name] = indexed
    key_sets = [set(indexed) for indexed in by_component.values()]
    if any(keys != key_sets[0] for keys in key_sets[1:]):
        raise QmtDataError("composite components do not cover the same observation panel")

    normalized = {name: weight / total_weight for name, weight in weights.items()}
    scores: dict[tuple[str, str], float] = {key: 0.0 for key in key_sets[0]}
    dates = sorted({execution_at for execution_at, _ in key_sets[0]})
    for execution_at in dates:
        date_keys = sorted(key for key in key_sets[0] if key[0] == execution_at)
        for name, indexed in by_component.items():
            ranked = average_ranks(
                [directions[name] * indexed[key].signal for key in date_keys]
            )
            scale = max(len(ranked) - 1, 1)
            for key, rank in zip(date_keys, ranked, strict=True):
                scores[key] += normalized[name] * (rank - 1) / scale

    anchor = next(iter(by_component.values()))
    combined: list[BaselineObservation] = []
    for key in sorted(key_sets[0]):
        base = anchor[key]
        for indexed in by_component.values():
            row = indexed[key]
            if (
                row.signal_at != base.signal_at
                or row.signal_available_at != base.signal_available_at
                or row.return_end_at != base.return_end_at
                or row.forward_return != base.forward_return
            ):
                raise QmtDataError("composite components have inconsistent timing or labels")
        combined.append(
            BaselineObservation(
                instrument=base.instrument,
                signal=scores[key],
                signal_at=base.signal_at,
                signal_available_at=base.signal_available_at,
                average_daily_value=base.average_daily_value,
                liquidity_available_at=base.liquidity_available_at,
                execution_at=base.execution_at,
                return_end_at=base.return_end_at,
                forward_return=base.forward_return,
                can_buy_open=base.can_buy_open,
                can_sell_open=base.can_sell_open,
                tradability_reason=base.tradability_reason,
                eligible=base.eligible,
            )
        )
    return tuple(combined)


def normalize_cross_sectional_observations(
    observations: Sequence[BaselineObservation],
    *,
    winsor_fraction: float = 0.01,
    groups: dict[str, str] | None = None,
) -> tuple[BaselineObservation, ...]:
    """Same-decision-time winsorization, optional group neutralization and z-score."""

    if not 0 <= winsor_fraction < 0.5:
        raise QmtDataError("winsor_fraction must be in [0, 0.5)")
    by_date: dict[str, list[BaselineObservation]] = defaultdict(list)
    for row in observations:
        by_date[row.execution_at].append(row)
    normalized: list[BaselineObservation] = []
    for execution_at in sorted(by_date):
        rows = sorted(by_date[execution_at], key=lambda row: row.instrument)
        eligible = [row for row in rows if row.eligible and math.isfinite(row.signal)]
        if len(eligible) < 3:
            normalized.extend(rows)
            continue
        ordered = sorted(row.signal for row in eligible)
        lower = _quantile(ordered, winsor_fraction)
        upper = _quantile(ordered, 1 - winsor_fraction)
        clipped = {row.instrument: min(max(row.signal, lower), upper) for row in eligible}
        if groups:
            grouped: dict[str, list[float]] = defaultdict(list)
            for instrument, value in clipped.items():
                grouped[groups.get(instrument, "__market__")].append(value)
            centers = {key: sum(values) / len(values) for key, values in grouped.items()}
            clipped = {
                instrument: value - centers[groups.get(instrument, "__market__")]
                for instrument, value in clipped.items()
            }
        else:
            center = sum(clipped.values()) / len(clipped)
            clipped = {instrument: value - center for instrument, value in clipped.items()}
        scale = math.sqrt(sum(value**2 for value in clipped.values()) / len(clipped))
        values = {
            instrument: (value / scale if scale else 0.0)
            for instrument, value in clipped.items()
        }
        normalized.extend(
            replace(row, signal=values[row.instrument])
            if row.instrument in values
            else row
            for row in rows
        )
    normalized.sort(key=lambda row: (row.execution_at, row.instrument))
    return tuple(normalized)
