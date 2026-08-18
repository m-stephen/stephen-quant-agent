# V4.5 Candidate-Level 2025 Validation Result

## Final decision

The V4.4 candidate clearly fails in 2025: `REJECT_ALPHA_COURT`. It remains an historically
interesting effect, but it is not a currently reliable or deployable alpha.

| Metric | 2025 result |
|---|---:|
| Full portfolio excess return | -1.64% |
| Full portfolio excess Sharpe | -4.0858 |
| Selection increment vs matched control | -1.38% |
| Median / Q25 path Sharpe | -1.0253 / -1.3620 |
| Positive paths | 6/20 |
| Maximum drawdown | -2.08% |
| Positive stress cells | 0/27 |
| 2x / 3x cost return | -2.50% / -3.36% |
| CNY 20m return | -1.64% |
| Signal / return placebo p-value | 0.040 / 0.065 |
| DSR | 0.000000 |

Capacity clipping was zero, so capital size did not cause the failure. Post-result diagnosis
shows mean `mixed`-regime RankIC decaying from 0.163 in 2022, 0.079 in 2023 and 0.091 in 2024 to
0.024 in 2025. The 2025 third-quarter selection increment was about -1.92% and explains most of
the sign reversal. Factor decay or a market-structure change is more plausible than a cost error.

## Recommendations and next test strategy

1. Freeze and retire this candidate. Do not use 2025 to change its window, breadth, direction or
   regime.
2. Treat limit-up persistence as a risk/crowding feature rather than a standalone alpha. Test its
   incremental information alongside orthogonal chip, fund-flow, auction and margin domains.
3. Require nested temporal validation for new candidates: expression and parameter selection in
   inner training folds, purged/CPCV research validation outside them, then walk-forward deployment
   simulation. Every attempt continues to increment the Trial Ledger.
4. Add quarterly decay gates. Two consecutive deteriorating quarters in RankIC, profitable-path
   fraction or incremental return automatically downgrade a candidate.
5. Standardize execution gates: 20 non-overlapping paths, exposure-matched controls, 1x-3x costs,
   CNY 3m-20m capacity, adjacent breadth, permutation tests, DSR/PBO and capacity audit.
6. Because V4.5 has now opened 2025, it cannot be a final test for future candidates. Truly
   independent evidence must come from the frozen forward shadow starting 2026-08-19 and should
   accumulate for at least 6-12 months.

Research may continue on 2022-2025 with nested walk-forward to improve the method, but such output
is development evidence and cannot be presented as a new independent alpha validation.
