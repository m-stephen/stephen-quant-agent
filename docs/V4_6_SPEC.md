# V4.6 Bounded Orthogonal Search Protocol

## Search budget

- Development years: 2022-2025. All are reused project evidence; none is an independent final.
- Domains: auction, fund flow and chip distribution.
- Six economic mechanisms and their exact inverse per domain: 12 hypotheses per domain, 36 total.
- Horizon: 20 sessions; action: avoid the weakest ten names versus an exposure-matched
  equal-weight control.
- Every hypothesis and ensemble stress cell increments the Trial Ledger.

## Temporal and orthogonality gates

A candidate must have positive RankIC and incremental execution return in at least three of four
years, no yearly RankIC below -0.02, positive RankIC in every sequential outer development year
from 2023 through 2025, and positive median non-overlapping-path Sharpe in at least three years.
Two consecutive negative final quarters trigger a decay alarm.

Eligible candidates are ranked by worst outer-year plus mean RankIC. At most one candidate per
domain is admitted. A new domain is rejected when its daily-IC correlation with an admitted
candidate exceeds 0.75 in absolute value. At least two domains are required for an ensemble.
The ensemble uses equal percentile-rank weights; no weight is fitted on returns.

## Execution and statistical gates

The frozen stress grid is CNY 3m/20m crossed with 1x/2x transaction costs. At least 75% of cells
must have positive full and matched-control incremental returns. The primary ensemble requires
Sharpe at least 0.50, positive return, signal and return permutation p-values at most 0.05, and
DSR at least 0.95. A passing development result would still require prospective shadow evidence
starting 2026-08-19 before any deployment claim.
