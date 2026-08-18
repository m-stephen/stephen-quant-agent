# V4.6 Three-Domain Orthogonal Alpha Research Result

## Decision

V4.6 found a more plausible two-domain combination than the standalone limit-event factor, but
the decision remains `NO_DEVELOPMENT_ALPHA`.

Only two of 36 candidates passed the cross-year signal gate:

- `flow_price_divergence_5_20d`: five-day normalized fund flow relative to five-day price change.
- `auction_strength_5_20d`: five-day opening-auction return strength.

Their daily RankIC correlation was -0.1309, satisfying the orthogonality gate. No chip candidate
passed the cross-year gate.

| Metric | Ensemble result |
|---|---:|
| CNY 3m standard-cost excess return | +2.80% |
| Full portfolio excess Sharpe | 0.8250 |
| Increment vs matched control | +8.40% |
| Incremental daily Sharpe | 2.0143 |
| Positive non-overlapping paths | 17/20 |
| Median / Q25 path Sharpe | 0.4084 / 0.1165 |
| Maximum drawdown | -5.08% |
| Signal / return placebo p-value | 0.005 / 0.005 |
| 2x-cost full excess return | -4.54% |
| Positive stress cells | 2/4 |
| DSR | 3.76e-10 |

CNY 20m matched the CNY 3m result with zero capacity clipping. Capacity is therefore not the
problem; turnover and cost conversion are. Flow-price divergence retained positive incremental
return in all four years, including +1.97% in 2025. Auction strength reversed to -1.40% in 2025
and reduced temporal stability.

## Next steps

1. Do not expand the hypothesis count. Test turnover buffers, layered replacement and minimum
   trade thresholds in a small frozen grid.
2. Retain flow-price divergence as the core lead. Auction strength may confirm it but must not
   determine holdings alone.
3. Pause chip-family expansion until field scaling, coverage and overlap with price information
   are audited.
4. Add annual and quarterly cost attribution separating gross increment, turnover cost and
   equal-weight baseline cost.
5. Add domain-alignment caching. This 36-candidate run took about ten minutes and roughly 3.2 GB;
   repeated safe-DSL scans are not suitable for a continuous loop.
6. All follow-up remains 2022-2025 development evidence. Independent claims require the
   append-only forward shadow beginning 2026-08-19.
