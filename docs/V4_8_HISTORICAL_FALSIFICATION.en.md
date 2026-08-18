# Frozen Suspected Alpha: 2020–2021 Historical Falsification

## Technical summary

The unchanged candidate earned **37.86%** net in 2020–2021, or **CNY 1,135,696.78** on CNY
3 million, ending at **CNY 4,135,696.78**. Against a same-universe, same-path and same-cost matched
control, the factor added **10.33 percentage points**, or **CNY 309,895.08**.

The economics merit further discussion, but the formal result is
`FAIL_HISTORICAL_FALSIFICATION`. Path, doubled-cost and placebo checks passed; DSR was only
0.025975 versus the frozen 0.95 threshold. This backward temporal test was performed after
candidate discovery. It cannot replace a new forward Alpha Court and may not be used for tuning.

## Frozen identity and data scope

- Candidate fingerprint: `49bbaa53abab3f00a43011565235529629d807e8712eafc163e020f10ab9fec7`.
- Candidate commit: `30de08a7edd0ded2b3bd8977b505829e18b64582`.
- Test window: 2020-01-01 through 2021-12-31.
- Common daily, fund-flow and auction sessions: 486.
- Point-in-time universe decisions: 472.
- Universe construction follows the original V1.8.11 rule: rebuild the daily top-300 names from
  same-day fundamentals and trailing liquidity, then use the first 50 names for the candidate.
- Fourteen empty or schema-incomplete fundamental partitions are quarantined as no-new-decision
  days. No missing fields are imputed and no 2022 membership is backfilled.

## CNY 3 million account and cost stress

| Cost | Net return | Net profit | Ending value | Matched control | Factor increment | Value add | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard | 37.86% | 1,135,696.78 | 4,135,696.78 | 27.53% | +10.33pp | 309,895.08 | -14.68% |
| 2x | 34.68% | 1,040,273.91 | 4,040,273.91 | 23.99% | +10.69pp | 320,602.26 | -14.81% |

Absolute return uses the project's staggered 20-session cohort contribution convention, not a
broker-reconciled daily marked NAV.

## Direction replicated in both years, but 2021 lost money

| Year | Candidate net | Matched control | Factor increment | Cross-section benchmark |
|---|---:|---:|---:|---:|
| 2020 | 48.45% | 40.35% | +8.10pp | 42.68% |
| 2021 | -7.14% | -9.14% | +2.00pp | -8.07% |

The candidate added relative return in both years but did not deliver a positive absolute return in
2021. This is consistent with the prior interpretation that it may act more as a downside risk filter
than as a persistent positive-return engine.

## Paths, cost stress and placebos passed; DSR failed

| Cost | Portfolio excess | Factor path increment | Positive paths | Median path Sharpe |
|---|---:|---:|---:|---:|
| 1x | 5.10% | 8.10% | 18/20 | 0.7566 |
| 2x | 2.67% | 8.62% | 18/20 | 0.8150 |

- Signal-shuffle placebo: p=0.005.
- Return-permutation placebo: p=0.005.
- Empirical skewness: -0.26654; excess kurtosis: 0.58895.
- Cumulative recorded Trials: 1,105.
- DSR: 0.025975 versus the frozen 0.95 threshold.

The DSR failure means that, despite attractive economic and path behavior, the evidence remains
insufficient to rule out a lucky winner from the project's large cumulative search space.

## Market-index comparison

| Benchmark | Candidate net | Index price return | Outperformance | CNY 3m value advantage |
|---|---:|---:|---:|---:|
| CSI 300 (2020-01-06–2021-12-31) | 37.86% | 19.83% | +18.03pp | 540,911.41 |
| CSI 500 (2020-01-06–2021-12-31) | 37.86% | 36.45% | +1.40pp | 42,142.23 |

The benchmarks are price indexes and exclude cash dividends. Index outperformance also contains
the top-50 liquidity universe's style exposure; the 10.33-point matched-control increment is the
more relevant estimate of factor contribution.

## Conclusion and next step

The backward test did not falsify the candidate's economic direction, but it did not clear the
statistical gate. Keep it classified as a suspected alpha worth discussing, not a deployable alpha.
Retain this result append-only, prohibit tuning on 2020–2021, and continue waiting for at least 25
genuinely new sessions after 2026-08-16 for the official forward continuation.

