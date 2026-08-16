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
)


def build_seed_registry() -> FactorRegistry:
    return FactorRegistry(SEED_FACTORS)
