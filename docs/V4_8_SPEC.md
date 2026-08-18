# V4.8 One-Time Sealed Alpha Court Protocol

The V4.7 candidate is frozen at merge commit
`30de08a7edd0ded2b3bd8977b505829e18b64582`. V4.8 reveals 2026 data once and prohibits any
candidate modification after the result is known.

- holdout: 2026-01-01 through 2026-08-16;
- signal: equal percentile ranks of `flow_price_divergence_5_20d` and
  `auction_strength_5_20d`;
- execution: AVOID bottom 10, 10-rank holding buffer, 20-day offset paths;
- capital: CNY 3 million; standard and doubled costs;
- budget: exactly two sealed stress Trials;
- minimum economics: positive full and matched-control returns, at least 15/20 profitable paths,
  and non-negative median path Sharpe at both cost levels;
- falsification: signal and return placebo p-values at most 0.05, DSR at least 0.95 using all
  V4.6/V4.7/V4.8 Sharpe estimates, 1,103 recorded Trials, and the sealed return series' empirical
  skewness and excess kurtosis; execution-selection PBO must be at most 0.05 from audited purged
  CPCV over all six V4.7 signal/buffer configurations.

Failure consumes the holdout permanently. Its values may not be used to tune this candidate or to
generate a replacement.
