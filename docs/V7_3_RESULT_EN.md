# V7.3 Frozen Survivor Full Alpha Court Report

## Decision

Final decision: `REJECT_ALPHA_COURT`. All 16 deduplicated V7.1/V7.2 survivors received the same
full evaluation. None passed every frozen gate. The inverse 60-session volatility candidate merits
independent forward observation, but it is not deployable.

## Integrity

- Labels were restricted to 2022–2024; neither 2025 nor 2026 was opened.
- Seven V7.1 and ten V7.2 survivors produced 16 unique identities.
- The run recorded 16 screen, 16 CPCV, 16 standard-cost and 16 doubled-cost Trials.
- DSR additionally carries the 81 prior V7.1/V7.2 inferential attempts: 145 Trials in total.
- Shared snapshot: `8e48128cc889baf07a92bd60920db7c3010938ff08d3b17bca2e7a9cd69e8088`.
- Shared fold-selection PBO was `0.0`; every candidate had at least 18/20 positive folds.

## Best candidate: inverse 60-session volatility

The formula is `-volatility(close, 60)`, executed as a Top-10 portfolio from CNY 3 million.

| Metric | Standard costs | Doubled costs |
|---|---:|---:|
| Net return | 37.75% | 30.27% |
| Net profit | CNY 1,132,432 | CNY 907,983 |
| Annualized net Sharpe | 0.785 | 0.661 |
| Maximum drawdown | -19.16% | -20.21% |
| Total cost | CNY 176,072 | CNY 341,591 |
| Capacity clipping | 0 | 0 |

Its mean CPCV fold RankIC was `0.095947`, with 20/20 positive folds. Both placebo p-values were
`0.005`. Those gates passed. Empirical skewness was `0.8349` and excess kurtosis `3.4785`; after
145 recorded Trials, moment-adjusted DSR was only `0.187247`, far below `0.95`.

## Candidate execution summary

| Candidate | Annualized net Sharpe | Net return | Doubled-cost return | Max drawdown | Decision |
|---|---:|---:|---:|---:|---|
| Inverse 60-session volatility | 0.785 | 37.75% | 30.27% | -19.16% | DSR fail; retain for forward observation |
| Inverse 15/60 amount trend | 0.277 | 11.78% | -3.61% | -34.60% | Cost, Sharpe and drawdown fail |
| 20-session reversal | 0.084 | -15.02% | -31.86% | -49.17% | Execution quality fail |
| Inverse 15/60 price trend | 0.063 | -13.53% | -22.52% | -50.86% | Execution quality fail |
| Remaining 12 candidates | -0.367 to -1.060 | all negative | all negative | -38.62% to -86.41% | Reject |

Every signal and return placebo p-value was at most `0.01`, yet every DSR remained below `0.95`.
The cross-sectional relationships are not simple random permutations, but they do not survive the
full multiplicity and portfolio-conversion burden as reliable Alpha.

## Walk-forward

The expanding selector returned `19.86%`, but annualized Sharpe was only `0.399` and maximum
drawdown was `-29.40%`. It failed both the frozen 0.50 Sharpe and -25% drawdown thresholds.

## Next step

Do not tune the windows or directions of these 16 candidates again. Register inverse 60-session
volatility for independent forward observation. The next automatic generation epoch should explore
mechanisms outside the low-volatility/reversal cluster and carry all 145 Trials forward.
