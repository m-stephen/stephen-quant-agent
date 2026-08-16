# V1.1 Factor Registry

## Goal

Define candidate factors as immutable, versioned, point-in-time contracts before evaluating their predictive value.

Each definition declares its formula, required fields, economic category, lookback, minimum history, availability lag, expected direction, and description. Calculation fails explicitly when history is insufficient, values are missing, or any input was unavailable at decision time.

## Seed library

The first library contains 15 simple baselines:

- Momentum and reversal: Ret5, Ret20, Ret60, Ret120
- Trend: MA20/MA60, Price/MA120, normalized 20-period slope
- Relative strength: 60-period return versus benchmark
- Liquidity: volume ratio, mean turnover, Amihud illiquidity
- Risk: realized volatility, downside volatility, maximum drawdown, normalized ATR

These are candidate inputs, not accepted alpha. Statistical acceptance belongs to V1.2 and falsification belongs to V1.4.

## Timing contract

`compute_factor` requires availability metadata for every input observation. A value with `available_at > decision_at` fails with `FutureDataError`. Missing values and insufficient warm-up windows also fail rather than being silently filled.

## Non-goals

- Cross-sectional normalization
- IC or RankIC evaluation
- Alpha acceptance thresholds
- Data vendor adapters
- Portfolio construction
