# V1.8.7 reference validation result

This is the frozen decision from the first V1.8.7 validation-only run of `ret_60@1.0.0`. It is
recorded to prevent later reinterpretation of the evidence.

## Lineage

- Workflow: `qmt-backtest-workflow-1.3.0`
- Code: `689c6d9`
- Snapshot: `snap_ee27eef1d50fdcb2`
- Experiment: `exp_422609c8d77a4957`
- Trial: `trial_05331649a5124331` (Trial 1)
- Evaluation window: 2024 validation only
- Reserved final test: 2026, unopened

The snapshot contains 727 date partitions from 2022-01-04 through 2025-01-02. The final date is
only the next-open label boundary for the 2024-12-31 signal. No later 2025 partition and no 2026
partition was loaded or hashed.

## Results

| Measure | Result |
|---|---:|
| Strategy net return | 5.38% |
| CSI 300 return | 14.76% |
| Excess total return | -9.37% |
| Net Sharpe | 0.331 |
| Maximum drawdown | -18.97% |
| Total costs | CNY 20,645.26 |
| Mean RankIC | -0.0067 |
| Signal-shuffle p-value | 0.740 |
| Return-permutation p-value | 0.660 |

The data audit identified 20 upper-limit opens and 5 lower-limit opens across the loaded panel.
None coincided with a desired rebalance order, so blocked notional was zero in this run.

## Frozen decision

**REJECT `ret_60` as an independent alpha candidate.** It underperformed the benchmark in the
validation window and failed both placebo tests. The 2026 final-test window must remain unopened
for this candidate. Any successor must be a new, predeclared hypothesis and a new Trial; it must
not be a parameter adjustment chosen to repair the already observed 2025 result.
