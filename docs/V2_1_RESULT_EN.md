# V2.1 Real-Data Validation Result

Status: **engineering accepted; Alpha Court rejected.** This result uses only 2022–2024 research
data and is neither 2025/2026 out-of-sample evidence nor investment advice.

## Data and integrity

- Snapshot: `99b037baf97721ab438c54392b419ea96c994b68ef616a20b5fa234223928b23`
- 726 research sessions, 50 members per day, and 411 unique historical members.
- 346,389 daily rows; 296,513 fund-flow; 296,514 auction; 256,405 margin; 318,714 industry.
- All 26 candidates were unique, seven reached CPCV, and the complete ledger contains 37 trials.
- Neither sealed window opened; registry audit and four-artifact offline replay passed.

## Outcome

- CPCV signal gate: pass.
- Best executed candidate: `flow_confirmation_20_20d`.
- Research net return 34.74%, annualized net Sharpe 0.43, maximum drawdown -28.42%.
- Walk-forward net return 34.57%, annualized net Sharpe 0.52, maximum drawdown -21.32%.
- Signal and return placebos both p=0.005; PBO=0.
- DSR probability was 45.40%, below the preregistered 95% threshold, so the alpha claim was rejected.

## Interpretation and next step

Flow confirmation contains material cross-sectional information, but absolute risk-adjusted return
is weak and does not survive the multiplicity penalty across 37 trials. Freeze this epoch and open a
new single-variable epoch for risk neutralization, industry/style residuals, holding horizon, and
portfolio construction. Do not lower the DSR gate or open 2025 to repair the result.
