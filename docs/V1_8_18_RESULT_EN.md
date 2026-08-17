# V1.8.18 Test Results (English)

## Decision

- **Engineering acceptance: PASS.** The 20-day flow-divergence pipeline now covers candidate generation, screening, CPCV, execution, stability diagnostics, capacity stress, and bilingual reporting.
- **Alpha acceptance: REJECT.** The formal decision is `REJECT_ALPHA_COURT`; the candidate must not enter production or unlock the sealed test windows.
- **Data integrity preserved.** The existing frozen snapshot was used and the 2025/2026 validation and final-test windows remained sealed.

## Frozen run

- Snapshot: `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Research period: 2022–2024
- 8 candidates generated, 4 shortlisted, 3 execution-tested
- Global Trials: 242 before, 260 after; DSR used all 260 recorded Trials
- Formal selection: `price_reversal_control_60_20d`

## Formal result

| Metric | Result |
|---|---:|
| Net return | 8.59% |
| DSR | 0.285 |
| PBO | 0.000 |
| Placebo p-values | 0.005 / 0.005 |
| Walk-forward net return | 41.51% |
| Walk-forward annualized Sharpe | 0.482 |
| Walk-forward maximum drawdown | -35.78% |

Some local statistical gates passed, but risk-adjusted performance, drawdown, and multiplicity-adjusted evidence were insufficient. The overall candidate was therefore rejected.

## 20-day flow-divergence diagnostics

For `flow_price_divergence_parent`:

- RankIC 0.1302; positive annual RankIC ratio 100%; turnover 3.84%.
- Execution net return 3.32%; annualized Sharpe 0.178; maximum drawdown -38.10%; cost CNY 47,146.40.
- RankIC was positive in all prior-information regimes: down/high-vol 0.1665, down/low-vol 0.1904, up/high-vol 0.0868, up/low-vol 0.0852.
- ADV-tercile RankIC: low 0.1000, mid 0.1215, high 0.1606; the signal strengthened with liquidity.

The surprise and interaction variants did not improve efficiency. The 5/60 and 20/60 flow surprises, large-flow surprise, and reversal interaction failed screening. Extra-large-flow surprise was shortlisted but produced only 0.0059 RankIC.

## Capacity and industry neutralization

- At CNY 1 million initial NAV, the 1%, 5%, and 10% participation tests were identical and clipped no notional.
- This only shows that the current NAV does not bind capacity; it **does not establish unlimited capacity**. The next test should trace the frontier at CNY 1m, 10m, 50m, and 100m.
- Industry neutralization was not run because no point-in-time stock-level industry membership covering 2022–2024 was available. The system failed closed instead of backfilling history with current classifications.

## Known limitations and next steps

1. Static factors are not retrained inside each CPCV fold. Complete OOS paths cover the same research observations, so path RankIC repeats. Purge/embargo remains effective, but retraining instability is not tested yet.
2. Add stock-industry history with effective and availability timestamps, then rerun neutralization.
3. Build a NAV capacity frontier and locate return, turnover, slippage, and clipping breakpoints.
4. Preregister the hypothesis that flow divergence is stronger in down markets and test it on a new research window without tuning against the sealed 2025/2026 windows.

