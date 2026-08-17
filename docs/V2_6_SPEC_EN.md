# V2.6: One-shot 2025 validation of the frozen policy

## Objective

V2.6 only tests whether V2.5's preregistered `risk_off_cash` policy generalizes to the
independent 2025 window. It does not reselect factors, parameters, thresholds or portfolio
policies, and it does not open the 2026 final test.

## Frozen contract

- The factor, residualization, Top-5 rule, 20-session horizon and costs are inherited from V2.5.
- The regime remains the decision-time cross-sectional median of five-day momentum, with a
  zero threshold.
- `RISK_ON` trades the residual flow signal; `RISK_OFF` holds cash.
- The validation window is 2025-01-03 through 2025-12-31.
- 2026-01-05 through 2026-12-31 remains sealed.
- The historical ledger contains 47 trials; this run may add exactly one, for a total of 48.

## Data-readiness gates

Before the formal trial, the workflow requires at least 230 daily sessions, at least ten
non-overlapping validation periods, five eligible securities per period, a point-in-time
dynamic universe, and no input later than 2025-12-31.

## Validation gates

Net return must be positive, annualized net Sharpe at least 0.5, maximum drawdown no worse
than -15%, minimum rolling six-period Sharpe at least -0.25, and top-decile absolute-return
contribution no more than 50%. Both regimes need at least three periods, both placebo p-values
must be at most 0.05, and the combined 2022–2025 DSR must be at least 95%.

There is no current policy selection in a frozen single-policy test, so PBO is not reset; the
V2.5 value of 46.83% is retained as a historical warning. Any failed gate produces
`VALIDATION_FAIL_STOP` and forbids retries, post-hoc tuning and access to 2026.
