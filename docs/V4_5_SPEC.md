# V4.5 Candidate-Level Forward Validation Protocol

## Frozen candidate

- Signal: `limit_up_persistence_20_inverse_20_20d`.
- Action: avoid the weakest ten stocks only in the prior-only `mixed` regime.
- Outside `mixed`: hold the equal-weight baseline rather than cash.
- Primary NAV: CNY 3 million.
- Validation: 2025 only; no 2025 value is used to select or alter the candidate.
- Universe: freeze the top-50 membership known on 2024-12-31 through 2025. No future
  constituent backfill is allowed.

The year is candidate-level unopened before V4.5, but it has been used by earlier project work.
It is therefore not a globally pristine final test and must be labeled project-level reused.

## Predeclared tests

The 27-cell stress grid is the Cartesian product of NAV CNY 3m/10m/20m, cost multiplier 1x/2x/3x,
and breadth 5/10/15. Every cell increments the Trial Ledger. The primary cell is 3m, 1x and
breadth ten.

The primary gate requires positive portfolio and incremental returns, portfolio excess Sharpe at
least 0.50, median non-overlapping path Sharpe at least 0.50, at least 16/20 profitable paths,
drawdown no worse than -15%, at least 75% positive stress cells, positive 2x/3x-cost and CNY 20m
returns, DSR at least 0.95, and both permutation p-values at most 0.05. No failed gate may be
redefined after observing 2025.
