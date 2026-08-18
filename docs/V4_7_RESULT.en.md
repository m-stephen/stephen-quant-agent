# V4.7 Low-Turnover Alpha Conversion Result

## Decision

V4.7 found the first development candidate that is **worth forward validation**, but it is not a
proven or deployable alpha.

The candidate equal-weights percentile ranks of `flow_price_divergence_5_20d` and
`auction_strength_5_20d`, then applies a 10-rank holding buffer. An existing holding is replaced
only after it enters the weaker exit zone. Mean turnover fell from 1.89% without a buffer to 1.13%,
a reduction of about 40%.

| Metric | Standard cost | 2x cost |
|---|---:|---:|
| Full portfolio excess return | +6.96% | +2.36% |
| Full portfolio excess Sharpe | 1.4784 | 0.5166 |
| Increment over matched control | +12.57% | +13.38% |
| Incremental daily Sharpe | 2.5939 | 2.7515 |
| Profitable non-overlapping paths | 17/20 | 18/20 |
| Median / lower-quartile path Sharpe | 0.7111 / 0.5182 | 0.7605 / 0.5488 |
| Maximum drawdown | -6.00% | -6.16% |
| Mean turnover | 1.13% | 1.13% |

Signal-shuffle and return-permutation empirical p-values are both 0.005. No capacity clipping
occurred at CNY 3 million. The 2025 incremental returns remain positive at +1.50% under standard
costs and +1.49% under doubled costs, with no directional reversal.

## Failure that remains binding

Alpha Court still returns `REJECT`. Corrected DSR uses all 40 Sharpe estimates in the V4.6 ledger
plus the 12 V4.7 estimates, rather than the tightly clustered current grid alone. With 1,101
recorded Trials, DSR is `1.68e-9`. Historical multiplicity has therefore not been overcome by new,
independent evidence.

At doubled costs, 2023 full excess return remains -0.91%, although the matched-control increment is
+2.48%. The candidate passes a development gate requiring simultaneous positive full and
incremental returns in at least three of four years plus positive 2025 increment; it is not
profitable in every annual slice.

## Next step

Stop tuning on 2022-2025. Freeze the signal formula, 10-rank buffer, cost model and universe rules
in an append-only shadow beginning 2026-08-19. Path robustness, cost stress and DSR should be
recomputed only after never-selected forward observations accumulate. Deployment should not be
considered unless that independent evidence passes Alpha Court.

Data snapshot SHA-256:
`c5d1b168a58217a7017a41a5c84deb4523e6846edb91a9f6ee2401a2126bfbe8`.
