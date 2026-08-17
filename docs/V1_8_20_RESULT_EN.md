# V1.8.20 Test Results (English)

## Decision

- **Engineering acceptance: PASS.** Incremental RankIC, decile attribution, leg decomposition, date concentration, failure labels, and bilingual artifacts are operational.
- **The factor contains independent information.** Raw RankIC is 0.1302 and residual RankIC remains 0.0852 after removing price reversal and `log(ADV)`, above the frozen 0.02 gate.
- **Most value lies in avoidance.** The bottom decile averages -3.07% over the next 20 days, while the top decile averages only +1.09%, producing a 4.16% spread. The signal identifies stocks to avoid better than strong long-only Top-K selections.
- **Stop adjacent-window mutation.** The formal recommendation is `STOP_OR_REDESIGN`, with `LOW_EXECUTION_SHARPE` and `EXCESSIVE_DRAWDOWN` failure labels.
- **Alpha Court: REJECT.** Capacity and statistical incrementality do not overcome weak Sharpe and large drawdown. Live use is not authorized.

## Frozen run

- Snapshot: `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Research period: 2022–2024
- Attribution dates: 645; observations: 32,152
- Trials in this Experiment: 16; global Trials at DSR: 334
- 2025/2026 windows: unopened

## Incremental value

| Metric | Result | Frozen gate | Decision |
|---|---:|---:|---|
| Raw RankIC | 0.1302 | — | Reference |
| Residual RankIC | 0.0852 | ≥0.02 | Pass |
| Decile monotonicity | 0.6121 | ≥0.50 | Pass |
| Top 10% absolute date contribution | 30.76% | ≤50% | Pass |
| Top-decile return | +1.0885% | >0 | Pass but weak |
| Bottom-decile return | -3.0702% | — | Main contribution |
| Long-short spread | +4.1587% | — | Strongly asymmetric |

The middle of the decile curve is not fully monotonic: deciles 4–7 remain negative and only deciles 8–10 turn positive. A high continuous RankIC therefore does not imply a strong simple Top-K long-only portfolio.

## Execution and falsification

- At CNY 3m, the flow-divergence parent returns 3.29%, with annualized Sharpe 0.178 and maximum drawdown -38.11%.
- Alpha Court: `REJECT_ALPHA_COURT`; DSR 0.275; PBO 0; walk-forward Sharpe 0.481.
- Failure labels: `LOW_EXECUTION_SHARPE`, `EXCESSIVE_DRAWDOWN`.

## Research decision

Stop neighboring-window and flow-surprise formula mutations. The next iteration should change how the signal enters the portfolio rather than enlarge formula search:

1. Use flow divergence as an exclusion or underweight signal for the bottom decile instead of only buying the highest Top-K.
2. Compare top-decile, top-30%, and benchmark-enhancement portfolios that exclude the bottom decile.
3. Combine residual price-reversal and flow-divergence weights with industry, volatility, and liquidity limits.
4. Add regime-aware cash or risk budgets to address the -38% drawdown.
5. Preregister these portfolio variants as a bounded execution campaign without tuning on 2025/2026.

