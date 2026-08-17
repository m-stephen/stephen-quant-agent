# V3.1 Price-Factor Discovery Result

## Conclusion

This run did not achieve `COURT_PASS`, but it produced the first clear `RESEARCH_CANDIDATE`.
It disproves the claim that daily bars cannot yield even an attractive candidate and confirms that
the earlier bottleneck was the narrow generator and mismatched evaluation pipeline.

The selected candidate is `ohlc_return_close_120_20d_neg`: reverse the trailing 120-session close
return and predict the next 20-session open-to-open return. It is a medium-term reversal signal,
not a deployable strategy.

| Metric | Result |
|---|---:|
| Predeclared candidates | 630 |
| 2022 RankIC | 0.227871 |
| 2023 RankIC | 0.111925 |
| 2024 RankIC | 0.108395 |
| 2023 mean top-bottom return | 0.013055 |
| 2024 mean top-bottom return | 0.024131 |
| Purged/embargoed CPCV paths | 10/10 positive |
| CPCV PBO | 0.000000 |
| Signal / return placebo p-values | 0.005 / 0.005 |
| DSR probability, adjusted for 630 candidates | 0.033388 |
| Mean cost-aware excess Sharpe across 20 offsets | -0.094724 |
| Worst offset Sharpe | -0.814492 |
| Worst drawdown | -0.335469 |

The candidate passes cross-year sign stability, CPCV, PBO and placebo gates, but fails DSR,
economic Sharpe and drawdown. The precise conclusion is: **price contains stable cross-sectional
predictive structure, but the current long-only top-five implementation does not convert it into
acceptable net alpha.**

## What V3.1 fixes

- Freezes 630 candidates at once instead of testing three hard-coded factors per epoch.
- Covers 2/3/5/10/20/40/60/120/240-session windows and 1/3/5/10/20-session horizons.
- Predeclares both signs, so a negative IC becomes an auditable reverse hypothesis.
- Uses 2022 only to rank and freeze Top 60, 2023 to confirm and 2024 as retrospective shadow.
- Evaluates RankIC, top-bottom and top-vs-universe before long-only feasibility.
- Purges overlapping labels and applies a five-day embargo in CPCV; a singleton remains testable
  with PBO reported as not applicable.
- Evaluates every holding-period offset rather than sampling one arbitrary start date.
- Separates candidate-level multiplicity (630) from the audit Trial count.

## Integrity boundary

- Dataset snapshot: `b3a638ceb564292a5a36a577257bfacfbc0db05e5147cb3879bdc68d5c27a68e`
- Search space: `1000e02c4571c3732c8f8239955d11d7035a5e597ff951c4ca47b2ef173b7eed`
- Frozen Top 60: `2c8a38a3963f9368e4cd66b3bcf23bdfd47b3f7f9ab51925d0052f8ddd45c59c`
- CPCV manifest: `e8af653f1d67109c3c7580c512ae66b6666166a73c9ae8f2d3486545b17e70ec`
- 2025/2026 were not read, listed, ranked or used for inference.
- Because this project has inspected 2022–2024 before, this is calibration and retrospective shadow
  evidence rather than a fresh untouched out-of-sample claim.

The next preregistered study should focus on signal-to-portfolio conversion: industry/size
neutralization, portfolio breadth, turnover controls, staggered holdings and capacity tiers. The
DSR or economic gates must not be lowered to relabel this candidate as validated alpha.
