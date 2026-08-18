# V4.8 Sealed Candidate Alpha Court Result

## Decision

The V4.7 candidate performed strongly in the one-time sealed 2026 window, but the strict decision
remains `REJECT_ALPHA_COURT`. DSR is the only failed gate.

| Metric | Standard cost | 2x cost |
|---|---:|---:|
| Full excess return | +5.36% | +5.11% |
| Full excess Sharpe | 10.8282 | 10.1164 |
| Matched-control increment | +5.61% | +5.60% |
| Profitable non-overlapping paths | 20/20 | 20/20 |
| Median / lower-quartile path Sharpe | 2.4605 / 2.0639 | 2.4577 / 2.0731 |
| Maximum drawdown | -0.87% | -0.87% |

- signal / return placebo p-values: 0.005 / 0.005;
- purged-CPCV PBO over the six V4.7 execution configurations: 0;
- capacity clipping: zero;
- cumulative Trials: 1,103;
- empirical skewness / excess kurtosis: -0.2087 / 0.1368;
- DSR: 0.933929, below the frozen 0.95 threshold.

The initial normal-moment simplification produced DSR 0.945591. Supplying empirical moments from
the same sealed return series reduced it to 0.933929, so the correction did not favor acceptance.

Holding the other statistics constant, reaching 0.95 requires about 154 independent observations;
129 are currently available, leaving roughly 25 genuinely new trading days. The 2026-01-01 through
2026-08-16 window is permanently consumed and may not be used to modify this candidate or generate
a replacement. The next valid step is frozen forward accumulation, not threshold reduction or a
new search on the revealed window.
