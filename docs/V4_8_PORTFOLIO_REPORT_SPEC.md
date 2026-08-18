# V4.8 Frozen Candidate Portfolio Accounting Supplement

This supplement answers a reporting question only: what would CNY 3 million have earned under the
already frozen V4.7/V4.8 candidate, and how much of that result is distinguishable from market and
same-universe exposure? It does not search, select or modify a factor.

## Frozen identity and scope

- Candidate: equal percentile ranks of `flow_price_divergence_5_20d` and
  `auction_strength_5_20d`.
- Mapping: avoid the bottom 10 names, retain existing positions with a 10-rank buffer, and use 20
  staggered holding paths.
- Capital: CNY 3 million; standard and doubled transaction-cost scenarios.
- Account window: cohort starts from 2025-01-01 through the last cohort that can mature by
  2026-08-16.
- Evidence: 2025 is consumed development data; 2026 is the consumed one-time sealed window. The
  combined curve is descriptive and is never labelled wholly out of sample.
- Trial policy: one report-only ledger entry with `inferential_trial_delta=0`.

## Required outputs

1. Absolute gross and net return, CNY profit, ending model value, annualized return, drawdown and
   explicit cost.
2. Same-universe, same-path and same-cost all-eligible control, with factor value-add in percentage
   points and CNY.
3. 2025 and 2026 cohort-start attribution.
4. CSI 300 and CSI 500 price-index comparisons over each index file's actual common coverage.
5. Source hashes, membership coverage, limitations and bilingual JSON/Markdown artifacts.

## Interpretation constraints

- Index outperformance is not automatically factor alpha because it includes the frozen top-50
  universe's style exposure.
- The matched-control increment is the conservative factor contribution estimate.
- The overlapping-cohort accounting is the existing research convention, not an independently
  reconciled daily broker NAV.
- Missing index dates are never imputed or extrapolated.
- Nothing in this report changes the V4.8 `REJECT_ALPHA_COURT` decision.
