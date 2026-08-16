from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime

from .models import (
    FactorDefinition,
    FactorError,
    FactorValue,
    FutureDataError,
    InsufficientHistoryError,
    MissingDataError,
)

NumericSeries = Sequence[float | int | None]
Formula = Callable[[Mapping[str, list[float]]], float]


def _returns(values: list[float]) -> list[float]:
    return [values[index] / values[index - 1] - 1.0 for index in range(1, len(values))]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _population_volatility(values: list[float]) -> float:
    center = _mean(values)
    return math.sqrt(_mean([(value - center) ** 2 for value in values]))


def _period_return(data: Mapping[str, list[float]]) -> float:
    close = data["close"]
    return close[-1] / close[0] - 1.0


def _momentum120_skip20(data: Mapping[str, list[float]]) -> float:
    close = data["close"]
    return close[-21] / close[0] - 1.0


def _trend_efficiency20(data: Mapping[str, list[float]]) -> float:
    close = data["close"]
    path = sum(abs(close[index] - close[index - 1]) for index in range(1, len(close)))
    if path == 0:
        return 0.0
    return abs(close[-1] - close[0]) / path


def _range_position20(data: Mapping[str, list[float]]) -> float:
    upper = max(data["high"][-20:])
    lower = min(data["low"][-20:])
    if upper <= lower:
        raise MissingDataError("high-low range must be positive")
    return (data["close"][-1] - lower) / (upper - lower)


def _intraday_strength20(data: Mapping[str, list[float]]) -> float:
    opens = data["open"][-20:]
    closes = data["close"][-20:]
    if any(value <= 0 for value in opens):
        raise MissingDataError("open must be positive for intraday strength")
    return _mean(
        [close / opening - 1.0 for opening, close in zip(opens, closes, strict=True)]
    )


def _volume_surprise5_20(data: Mapping[str, list[float]]) -> float:
    volume = data["volume"][-20:]
    baseline = _mean(volume)
    if baseline <= 0:
        raise MissingDataError("mean volume must be positive")
    return _mean(volume[-5:]) / baseline - 1.0


def _signed_volume_momentum20(data: Mapping[str, list[float]]) -> float:
    volume = data["volume"][-20:]
    baseline = _mean(volume)
    if baseline <= 0:
        raise MissingDataError("mean volume must be positive")
    momentum = data["close"][-1] / data["close"][0] - 1.0
    return momentum * (_mean(volume[-5:]) / baseline)


def _dollar_liquidity20(data: Mapping[str, list[float]]) -> float:
    amount = data["amount"][-20:]
    average = _mean(amount)
    if average <= 0:
        raise MissingDataError("mean amount must be positive")
    return math.log(average)


def _parkinson_volatility20(data: Mapping[str, list[float]]) -> float:
    high = data["high"][-20:]
    low = data["low"][-20:]
    if any(upper <= 0 or lower <= 0 or upper < lower for upper, lower in zip(high, low)):
        raise MissingDataError("high and low must be positive and ordered")
    squared_ranges = [
        math.log(upper / lower) ** 2 for upper, lower in zip(high, low, strict=True)
    ]
    return math.sqrt(_mean(squared_ranges) / (4 * math.log(2)))


def _overnight_gap20(data: Mapping[str, list[float]]) -> float:
    opening = data["open"]
    close = data["close"]
    if any(value <= 0 for value in close[:-1]):
        raise MissingDataError("previous close must be positive for overnight gap")
    gaps = [
        opening[index] / close[index - 1] - 1.0
        for index in range(1, len(close))
    ]
    return _mean(gaps[-20:])


def _close_location20(data: Mapping[str, list[float]]) -> float:
    values: list[float] = []
    for upper, lower, close in zip(
        data["high"][-20:], data["low"][-20:], data["close"][-20:], strict=True
    ):
        if upper < lower or close < lower or close > upper:
            raise MissingDataError("close location requires ordered OHLC values")
        width = upper - lower
        values.append(0.0 if width == 0 else (2 * close - upper - lower) / width)
    return _mean(values)


def _ma20_60_ratio(data: Mapping[str, list[float]]) -> float:
    close = data["close"]
    return _mean(close[-20:]) / _mean(close[-60:]) - 1.0


def _price_ma120(data: Mapping[str, list[float]]) -> float:
    close = data["close"]
    return close[-1] / _mean(close[-120:]) - 1.0


def _trend_slope20(data: Mapping[str, list[float]]) -> float:
    close = data["close"][-20:]
    x_center = (len(close) - 1) / 2
    y_center = _mean(close)
    numerator = sum((index - x_center) * (value - y_center) for index, value in enumerate(close))
    denominator = sum((index - x_center) ** 2 for index in range(len(close)))
    return (numerator / denominator) / y_center


def _relative_strength(data: Mapping[str, list[float]]) -> float:
    return _period_return({"close": data["close"]}) - _period_return(
        {"close": data["benchmark_close"]}
    )


def _volume_ratio20_60(data: Mapping[str, list[float]]) -> float:
    volume = data["volume"]
    return _mean(volume[-20:]) / _mean(volume[-60:]) - 1.0


def _turnover20(data: Mapping[str, list[float]]) -> float:
    return _mean(data["turnover"][-20:])


def _amihud20(data: Mapping[str, list[float]]) -> float:
    returns = _returns(data["close"])
    amount = data["amount"][-len(returns) :]
    if any(value <= 0 for value in amount):
        raise MissingDataError("amount must be positive for Amihud")
    return _mean([abs(ret) / traded for ret, traded in zip(returns, amount, strict=True)])


def _volatility20(data: Mapping[str, list[float]]) -> float:
    return _population_volatility(_returns(data["close"]))


def _downside_volatility20(data: Mapping[str, list[float]]) -> float:
    returns = _returns(data["close"])
    return math.sqrt(_mean([min(value, 0.0) ** 2 for value in returns]))


def _max_drawdown60(data: Mapping[str, list[float]]) -> float:
    peak = data["close"][0]
    worst = 0.0
    for value in data["close"]:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def _atr20(data: Mapping[str, list[float]]) -> float:
    high, low, close = data["high"], data["low"], data["close"]
    true_ranges = [
        max(high[index] - low[index], abs(high[index] - close[index - 1]), abs(low[index] - close[index - 1]))
        for index in range(1, len(close))
    ]
    return _mean(true_ranges) / close[-1]


FORMULAS: dict[str, Formula] = {
    "period_return": _period_return,
    "momentum120_skip20": _momentum120_skip20,
    "trend_efficiency20": _trend_efficiency20,
    "range_position20": _range_position20,
    "intraday_strength20": _intraday_strength20,
    "volume_surprise5_20": _volume_surprise5_20,
    "signed_volume_momentum20": _signed_volume_momentum20,
    "dollar_liquidity20": _dollar_liquidity20,
    "parkinson_volatility20": _parkinson_volatility20,
    "overnight_gap20": _overnight_gap20,
    "close_location20": _close_location20,
    "ma20_60_ratio": _ma20_60_ratio,
    "price_ma120": _price_ma120,
    "trend_slope20": _trend_slope20,
    "relative_strength": _relative_strength,
    "volume_ratio20_60": _volume_ratio20_60,
    "turnover20": _turnover20,
    "amihud20": _amihud20,
    "volatility20": _volatility20,
    "downside_volatility20": _downside_volatility20,
    "max_drawdown60": _max_drawdown60,
    "atr20": _atr20,
}


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_factor(
    definition: FactorDefinition,
    data: Mapping[str, NumericSeries],
    available_at: Mapping[str, Sequence[str]],
    *,
    as_of_index: int,
    observation_times: Sequence[str],
    decision_at: str,
) -> FactorValue:
    """Compute one factor while enforcing history, missing-data, and timing rules."""

    start = as_of_index - definition.minimum_observations + 1
    if start < 0 or as_of_index >= len(observation_times):
        raise InsufficientHistoryError(
            f"{definition.key} needs {definition.minimum_observations} observations"
        )

    decision_time = _parse_timestamp(decision_at)
    window: dict[str, list[float]] = {}
    for field in definition.required_fields:
        if field not in data or field not in available_at:
            raise MissingDataError(f"missing required field or availability metadata: {field}")
        if len(data[field]) <= as_of_index or len(available_at[field]) <= as_of_index:
            raise InsufficientHistoryError(f"series is shorter than as_of_index: {field}")

        raw_values = data[field][start : as_of_index + 1]
        field_availability = available_at[field][start : as_of_index + 1]
        if len(raw_values) != definition.minimum_observations:
            raise InsufficientHistoryError(f"incomplete window for {field}")
        if any(_parse_timestamp(timestamp) > decision_time for timestamp in field_availability):
            raise FutureDataError(f"{field} contains data unavailable at {decision_at}")
        if any(value is None or not math.isfinite(float(value)) for value in raw_values):
            raise MissingDataError(f"{field} contains missing or non-finite data")
        window[field] = [float(value) for value in raw_values if value is not None]

    try:
        formula = FORMULAS[definition.formula]
    except KeyError as exc:
        raise FactorError(f"unknown formula: {definition.formula}") from exc
    value = formula(window)
    if not math.isfinite(value):
        raise MissingDataError(f"{definition.key} produced a non-finite value")

    return FactorValue(
        factor_id=definition.factor_id,
        version=definition.version,
        as_of=observation_times[as_of_index],
        decision_at=decision_at,
        value=value,
    )
