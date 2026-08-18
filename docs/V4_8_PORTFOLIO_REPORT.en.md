# V4.8 Frozen Candidate: 2025–2026 Account and Market Benchmark Report

## Technical summary

Under the existing staggered 20-session cohort accounting, CNY 3 million earned **36.84%** net
from 2025-01-02 through 2026-08-14, equal to **CNY 1,105,111.91**, for a model ending value of
**CNY 4,105,111.91**. Against the same-universe, same-path and same-cost matched control, the factor
added **3.12%**, or **CNY 93,530.77**.

This is model-account performance, not a broker statement. 2025 is consumed development evidence
and 2026 is one-time sealed evidence; the combined curve is descriptive and cannot be relabelled as
wholly out of sample.

Over the common index interval, the candidate beat CSI 300 and CSI 500 by **22.32%** and **7.68%**,
but those gaps include frozen-top-50 universe and style exposure. The more conservative same-universe
factor increment is **3.12%**; not all index outperformance is alpha.

## CNY 3 million account result

| Cost scenario | Net return | Net profit | Matched control | Factor increment | Value add | Max drawdown | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard | 36.84% | 1,105,111.91 | 33.72% | 3.12% | 93,530.77 | -13.15% | 9,952.46 |
| 2x | 36.39% | 1,091,560.32 | 33.31% | 3.08% | 92,305.39 | -13.15% | 19,904.92 |

## Period contribution

Segments are classified by cohort start year; a cohort that matures in the next year remains in its
start-year segment.

| Start year | Net return | Net profit | Matched control | Factor increment | Cross-section benchmark |
|---|---:|---:|---:|---:|---:|
| 2025 | 47.88% | 1,436,290.54 | 48.75% | -0.87% | 49.15% |
| 2026 | -7.47% | -223,956.45 | -10.10% | +2.64% | -10.07% |

The absolute profit came mainly from the frozen universe's strong 2025. The factor did not add value
in 2025; its positive contribution appeared mainly in the falling 2026 segment, where it lost about
2.64 percentage points less than the matched control.

## Market-index comparison

Indexes use first-open to last-open price returns. Local index files stop at 2026-07-30, so index
comparisons are truncated automatically; candidate-only accounting still includes cohorts maturing
through 2026-08-14.

| Benchmark | Candidate net | Index return | Outperformance | Candidate value | Index value | Value advantage |
|---|---:|---:|---:|---:|---:|---:|
| CSI 300 (2025-01-02–2026-07-30) | 38.45% | 16.13% | +22.32% | 4,153,605.23 | 3,483,922.40 | 669,682.83 |
| CSI 500 (2025-01-02–2026-07-30) | 38.45% | 30.77% | +7.68% | 4,153,605.23 | 3,923,097.66 | 230,507.57 |

These index gaps cannot all be attributed to the factor because the candidate uses a frozen top-50
universe with different constituents and style exposure. The primary isolated factor estimate remains
the same-universe matched-control increment: 3.12%, or about CNY 93.5k.

## Metric definitions and method

- Absolute net return compounds each staggered cohort's capital contribution after commission, tax, slippage and impact under the existing system convention.
- The cross-section benchmark is the equal-weight 20-session return of all eligible names in the same candidate universe, not CSI 300.
- The matched control holds all eligible names under the same universe, staggered paths, capital and costs to isolate factor selection value.
- Index outperformance is candidate net return minus index price return over the common covered interval.
- The universe uses the first 50 names in the dynamic membership; after 2024-12-31 the last known membership is carried forward.

## Limitations and robustness

- 2025 is reused development evidence; only 2026 was one-time sealed, so the combined account curve is not wholly out of sample.
- The membership artifact ends on 2024-12-31 and is carried forward through 2025–2026; this is a frozen-universe test, not a refreshed live universe.
- Absolute return uses the existing overlapping-cohort contribution convention, not an independently reconciled daily broker NAV.
- CSI 300 and CSI 500 files end on 2026-07-30, so index outperformance is reported only through that date.
- Index comparisons use price indexes and therefore exclude cash dividends.
- At standard cost, 93.73% of positions were retained by the buffer on average; the result largely reflects initial selection and low-turnover hysteresis rather than continuously refreshed daily signals.
- This report runs continuously from 2025 and carries buffered holdings into 2026; the V4.8 sealed audit reinitialized in 2026, so its prior +5.36% full excess and this report's 2026 segment are not the same account path.
- Outperformance versus market indexes includes the frozen top-50 universe's style exposure; only the same-universe matched-control increment is close to the factor's isolated contribution.
- The candidate still fails the frozen Alpha Court because DSR 0.933929 is below 0.95.

## Next steps

Before deployment, add a daily marked-to-market stateful NAV reconciliation, refresh the 2025–2026
universe, complete August index data, and retain the frozen candidate until roughly 25 genuinely new
sessions after 2026-08-16 are available for the DSR continuation.
