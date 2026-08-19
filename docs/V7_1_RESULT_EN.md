# V7.1 Real Automatic Factor-discovery Test

## Conclusion

System status: `OPERATIONAL`. Research status: `RESEARCH_CANDIDATE_PENDING_EXECUTION`. The result is
not deployable and has not passed the Alpha Court.

V7.1 fixes the identical CPCV path averages seen for fixed factors in V7.0. Each purged fold now
selects a candidate on its training side and ranks that selection on complementary OOS evidence,
producing non-degenerate temporal evidence.

## Frozen experiment

- Labels: 2022–2024 only.
- 2025 validation and 2026 final-test windows: unopened.
- Dynamic universe: at most 300 stocks per date.
- Automatic candidates: 16 formula identities in both directions, 32 total.
- CPCV candidates: seven; total Trials: 39 (32 training and seven CPCV).
- Snapshot: `b3a638ceb564292a5a36a577257bfacfbc0db05e5147cb3879bdc68d5c27a68e`.

## Leading research candidate

The candidate is `-volatility(close, 60)`, ranking stocks from lower to higher trailing 60-session
volatility:

- Mean fold RankIC: `0.109194`.
- Positive folds: 20/20.
- Minimum/maximum fold RankIC: `0.080968 / 0.137421`.
- Training cross-sectional turnover: approximately `0.0110`.
- Fold-selection PBO: `0.15`.

Other fold survivors were mainly inverse long price trend, five-session low volatility, inverse
amount trend and five/20-session reversals. The search therefore found a low-volatility/reversal
cluster rather than several independent Alphas.

## Decision

PBO 0.15 is below the exploratory research funnel's 0.20 ceiling, so execution diagnostics are
reasonable. It remains above the final Alpha Court ceiling of 0.05 and cannot be reported as a
PASS. The frozen candidate should next receive standard/doubled-cost, capacity, placebo and DSR
diagnostics without re-optimizing its window or direction on the same research labels.
