from __future__ import annotations

from typing import Literal

from .models import FactorDefinition
from .registry import FactorRegistry


def _definition(
    factor_id: str,
    name: str,
    category: str,
    formula: str,
    fields: tuple[str, ...],
    lookback: int,
    observations: int,
    direction: Literal[-1, 1],
    description: str,
) -> FactorDefinition:
    return FactorDefinition(
        factor_id=factor_id,
        version="1.0.0",
        name=name,
        category=category,
        formula=formula,
        required_fields=fields,
        lookback_periods=lookback,
        minimum_observations=observations,
        availability_lag_days=0,
        direction=direction,
        description=description,
    )


SEED_FACTORS = (
    _definition("ret_5", "5-period reversal", "reversal", "period_return", ("close",), 5, 6, -1, "Short-horizon return, interpreted contrarian."),
    _definition("ret_20", "20-period momentum", "momentum", "period_return", ("close",), 20, 21, 1, "Medium-short price momentum."),
    _definition("ret_60", "60-period momentum", "momentum", "period_return", ("close",), 60, 61, 1, "Medium-horizon price momentum."),
    _definition("ret_120", "120-period momentum", "momentum", "period_return", ("close",), 120, 121, 1, "Long-horizon price momentum."),
    _definition("ma_20_60", "MA20 / MA60", "trend", "ma20_60_ratio", ("close",), 60, 60, 1, "Short moving average relative to long moving average."),
    _definition("price_ma_120", "Price / MA120", "trend", "price_ma120", ("close",), 120, 120, 1, "Latest close relative to its long moving average."),
    _definition("trend_slope_20", "Normalized trend slope", "trend", "trend_slope20", ("close",), 20, 20, 1, "OLS price slope normalized by mean price."),
    _definition("rs_index_60", "Index-relative strength", "relative_strength", "relative_strength", ("close", "benchmark_close"), 60, 61, 1, "Asset return minus benchmark return."),
    _definition("volume_ratio_20_60", "Volume ratio 20 / 60", "liquidity", "volume_ratio20_60", ("volume",), 60, 60, 1, "Recent volume relative to its longer baseline."),
    _definition("turnover_20", "Mean turnover", "liquidity", "turnover20", ("turnover",), 20, 20, 1, "Average traded fraction over the recent window."),
    _definition("amihud_20", "Amihud illiquidity", "liquidity", "amihud20", ("close", "amount"), 20, 21, -1, "Absolute return per unit of traded amount."),
    _definition("volatility_20", "Realized volatility", "risk", "volatility20", ("close",), 20, 21, -1, "Population volatility of simple returns."),
    _definition("downside_vol_20", "Downside volatility", "risk", "downside_volatility20", ("close",), 20, 21, -1, "Root mean squared negative return."),
    _definition("max_drawdown_60", "Maximum drawdown", "risk", "max_drawdown60", ("close",), 60, 61, 1, "Worst peak-to-trough return in the window."),
    _definition("atr_20", "Normalized ATR", "risk", "atr20", ("high", "low", "close"), 20, 21, -1, "Average true range divided by latest close."),
    _definition("mom_120_skip_20", "120-period momentum skipping 20", "momentum", "momentum120_skip20", ("close",), 120, 121, 1, "Long momentum measured through t-20 so the recent month cannot dominate."),
    _definition("trend_efficiency_20", "20-period trend efficiency", "trend", "trend_efficiency20", ("close",), 20, 21, 1, "Absolute endpoint move divided by the total absolute return path."),
    _definition("range_position_20", "20-period range position", "trend", "range_position20", ("high", "low", "close"), 20, 20, 1, "Latest close location inside the trailing high-low range."),
    _definition("intraday_strength_20", "20-period intraday strength", "price_action", "intraday_strength20", ("open", "close"), 20, 20, 1, "Mean close-to-open return over the recent window."),
    _definition("volume_surprise_5_20", "Volume surprise 5 / 20", "volume", "volume_surprise5_20", ("volume",), 20, 20, 1, "Recent five-period volume relative to its twenty-period baseline."),
    _definition("signed_volume_mom_20", "Volume-confirmed 20-period momentum", "volume", "signed_volume_momentum20", ("close", "volume"), 20, 21, 1, "Twenty-period return scaled by recent relative volume."),
    _definition("dollar_liquidity_20", "20-period dollar liquidity", "liquidity", "dollar_liquidity20", ("amount",), 20, 20, 1, "Log mean traded amount over the recent window."),
    _definition("parkinson_vol_20", "20-period Parkinson volatility", "risk", "parkinson_volatility20", ("high", "low"), 20, 20, -1, "High-low range volatility using the Parkinson estimator."),
)


def build_seed_registry() -> FactorRegistry:
    return FactorRegistry(SEED_FACTORS)
