# V1.8.19 Test Results (English)

## Decision

- **Engineering acceptance: PASS.** All 15 preregistered combinations of five NAV levels and three participation limits completed on real data.
- **CNY 3m reference: operational under the capacity model.** No ADV-capacity clipping occurred for the current universe, Top-K, and execution model.
- **CNY 20m ceiling: supported within this model.** Net return declined by only 0.126 percentage points and Sharpe by about 0.0015 versus CNY 3m.
- **Alpha acceptance: REJECT.** The formal result remains `REJECT_ALPHA_COURT`. Capacity support is not evidence of alpha validity or live-trading approval.
- **Sealed-window discipline preserved.** Neither the 2025 validation window nor the 2026 final-test window was opened.

## Frozen run

- Snapshot: `eb6b8b61030a338f417f79f969d7ebecd60bb3b3ff1103a57b718aabf25e3ccd`
- Research period: 2022–2024
- NAV: CNY 1m, 3m, 5m, 10m, and 20m
- Maximum ADV participation: 1%, 5%, and 10%
- CNY 3m is the same-participation reference; CNY 20m is the hard ceiling
- Global recorded Trials at DSR computation: 318

## Capacity frontier at the primary 5% participation limit

| Initial NAV | Net return | Annualized Sharpe | Maximum drawdown | Cumulative cost/NAV | Capacity-clipped ratio | Return change vs CNY 3m |
|---:|---:|---:|---:|---:|---:|---:|
| CNY 1m | 3.324% | 0.1780 | -38.104% | 4.715% | 0.000% | +0.034% |
| CNY 3m | 3.290% | 0.1776 | -38.109% | 4.745% | 0.000% | 0.000% |
| CNY 5m | 3.267% | 0.1773 | -38.113% | 4.767% | 0.000% | -0.023% |
| CNY 10m | 3.224% | 0.1768 | -38.120% | 4.806% | 0.000% | -0.066% |
| CNY 20m | 3.164% | 0.1761 | -38.131% | 4.861% | 0.000% | -0.126% |

The 1%, 5%, and 10% results were identical at each NAV, showing that even the strictest 1% ADV limit did not bind. The small degradation with NAV came from the square-root impact model rather than capacity clipping.

## Alpha Court

- Formal selection: `price_reversal_control_60_20d`
- DSR 0.277; PBO 0.000; both placebo p-values 0.005
- Walk-forward net return 41.46%; annualized Sharpe 0.481; maximum drawdown -35.79%
- At CNY 3m, the parent flow-divergence factor returned 3.29%, with Sharpe 0.178 and maximum drawdown -38.11%

Local statistical signals and adequate modeled capacity do not overcome weak DSR, low risk-adjusted performance, and large drawdown. Rejection is therefore the correct outcome.

## Engineering finding and limitations

The first real run revealed execution dates with fewer eligible assets than the frozen Top-K, which previously aborted the entire task. The corrected schedule uses only cross-sections with at least five assets eligible at that decision time. The failed attempt remains in the isolated Trial Ledger and contributes to the later global trial count.

This result applies only to the current data, dynamic universe, Top-K, cost assumptions, and impact model. It does not prove CNY 20m capacity under every market condition and does not extrapolate beyond the user-approved ceiling. The next test should apply pessimistic volume haircuts, liquidity shocks, and higher slippage.

