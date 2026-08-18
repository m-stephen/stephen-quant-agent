# V4.4 Path-Robust Alpha Protocol

## Objective

Distinguish a repeatable stock-selection effect from overlapping-horizon inflation and from the
return of holding cash in a sparse market regime. This milestone does not weaken Alpha Court.

## Frozen search

- Research windows: 2022 and 2023 only.
- Final window: 2024, opened once after selection.
- Six V4.3 frozen chip/limit-event signals.
- Usages: BUY and AVOID; breadths: 5, 10 and 20.
- Prior-only regimes: all, risk-on, risk-off, mixed and liquidity-shock.
- Total search cells: 180; all increment the Trial Ledger.
- NAV: CNY 3 million; commission, tax, slippage, impact and 5% participation remain explicit.

Each 20-day strategy is split into 20 non-overlapping rebalance-offset paths. Candidate returns
are compared with an equal-weight portfolio with the same regime/cash exposure. A research cell
must pass in both years: median path Sharpe at least 0.50, lower-quartile path Sharpe above zero,
at least 16/20 profitable paths, positive mean path return, positive incremental return and
positive total excess return. Selection maximizes the worse-year lower-quartile Sharpe first.

## Final and falsification gates

The frozen candidate is evaluated once in 2024. Required gates are median path Sharpe at least
0.50, positive lower-quartile path Sharpe, at least 16/20 profitable paths, positive incremental
and portfolio excess return, drawdown no worse than -25%, DSR at least 0.95, and both signal and
return permutation p-values at most 0.05. A failed gate cannot be relabeled as a pass.

The post-result diagnosis that an inactive regime should hold an equal-weight baseline rather
than cash is an execution-wrapper correction. Because it was identified after opening 2024, it
must be labeled post-hoc until confirmed on genuinely new data.
