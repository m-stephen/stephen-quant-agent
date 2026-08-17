# V1.8.20: Factor Incremental Value and Return Attribution

Tracking issue: [#33](https://github.com/m-stephen/stephen-quant-agent/issues/33)

## Objective

V1.8.20 does not expand the candidate space. It explains why the flow-divergence factor's high RankIC fails to become tradable performance and decides whether the family should continue, stop, or be redesigned.

## Frozen diagnostics

- Reuse the eight fixed 20-day candidates and analyze only the 2022–2024 research period.
- Report daily decile returns, long and short legs, long-short spread, and extreme-date concentration for the flow-divergence parent.
- Within each decision-time cross-section, residualize against the visible price-reversal control and `log(ADV)` using OLS. Future returns are never used to estimate exposures.
- Register the attribution Trial before execution and DSR.
- Missing controls, future-visible observations, or singular control matrices fail closed.

## Frozen failure labels

- Residual RankIC below 0.02: `NO_INCREMENTAL_INFORMATION`
- Decile monotonicity below 0.50: `WEAK_MONOTONICITY`
- Long-leg return at or below zero: `WEAK_LONG_LEG`
- Top 10% of dates contribute over 50% of absolute spread: `DATE_CONCENTRATION`
- Net execution Sharpe below 0.50: `LOW_EXECUTION_SHARPE`
- Maximum drawdown below -25%: `EXCESSIVE_DRAWDOWN`

Incremental-information failure, low execution Sharpe, or excessive drawdown forces `STOP_OR_REDESIGN`. The 2025/2026 windows remain sealed.

