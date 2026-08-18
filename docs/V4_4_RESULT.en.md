# V4.4 Path-Robust Alpha Research Result

## Decision

V4.4 found a **stock-selection lead worth further discussion and validation**, but the complete
strategy still fails Alpha Court and is not deployable. In a prior-only `mixed` market regime,
the candidate ranks `limit_up_persistence_20_inverse_20_20d` and avoids the weakest ten stocks.

| Window | Median path Sharpe | Q25 Sharpe | Positive paths | Mean path return | Increment vs matched control | Full portfolio excess |
|---|---:|---:|---:|---:|---:|---:|
| 2022 research | 1.0640 | 0.7760 | 19/20 | 3.09% | 3.10% | 27.99% |
| 2023 research | 0.7466 | 0.1180 | 16/20 | 1.41% | 1.42% | 26.55% |
| 2024 one-shot final | 0.7309 | -0.3305 | 14/20 | 2.08% | 2.14% | -9.65% |

The 2024 incremental daily Sharpe was 1.9997. Signal-shuffle and return-permutation empirical
p-values were both 0.005. The weakest-stock avoidance effect therefore retained the same sign
across 2022-2024 and is not merely an artifact of overlapping 20-day labels.

## Why Alpha Court still rejects it

- Only 14/20 final paths were profitable, below the frozen 16/20 gate.
- The final lower-quartile path Sharpe was -0.3305.
- The original regime wrapper held cash outside `mixed` states and lagged the rising 2024 market
  by 9.65%. This is a beta/cash conversion failure rather than a negative selection increment.
- DSR was only 0.161953 after accounting for 1,022 recorded historical trials, below 0.95.

The precise claim is: **a positive 2022-2024 selection lead passed both placebo tests, while no
fully tradable, multiplicity-adjusted Alpha Court winner has yet been found.** Holding the
equal-weight baseline outside the target regime and applying the AVOID overlay inside it is the
appropriate wrapper repair, but it was diagnosed after viewing 2024 and is post-hoc until tested
on genuinely new data.

In the post-hoc overlay diagnostic, holding the equal-weight baseline outside `mixed` states
improved 2024 full-portfolio excess return from -9.65% to +0.38%, with -2.43% drawdown, but its
excess Sharpe was only 0.37 and 2023 remained -0.50%. This confirms that cash exposure was the
main conversion error while also showing that the repaired full strategy is not yet strong.
