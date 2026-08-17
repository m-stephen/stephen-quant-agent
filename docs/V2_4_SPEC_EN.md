# V2.4: Frozen Temporal Stability and Research-Preview Release Candidate

## Objective

V2.4 freezes the V2.3 factor, controls, residualization, Top-5 mapping, costs, capital, and
holding period. It performs no new factor or parameter search. The only registered trial is a
temporal-validation audit of the exact 35 previously observed non-overlapping execution
periods, increasing the cumulative ledger from 44 to 45.

## V2.3.1 hardening

- Shared canonical hashing, panel timing, non-overlap, replay hashing, and return-moment tools
  are public research-epoch utilities rather than cross-workflow private imports.
- OLS residualization is a public evaluation primitive reused by attribution and portfolio
  workflows.
- DSR uses bias-corrected skewness and excess kurtosis estimated from actual net period returns.
- Inherited PBO is labelled `SIGNAL_SELECTION_ONLY`; it is not presented as a fresh PBO for the
  residualized portfolio mapping.
- V2.2 and V2.3 replay contracts remain supported.

## Temporal diagnostics

- calendar-year net return, annualized Sharpe, drawdown, period count, and cost;
- rolling 12-period Sharpe and drawdown;
- positive-year fraction and worst-year metrics;
- top-decile absolute-return contribution;
- exact V2.3 execution replay, capacity, point-in-time, ledger, and sealed-window checks;
- moment-corrected DSR with 45 recorded trials.

## Frozen Alpha gates

At least two of three years must be positive. Worst-year return must be at least -10%,
worst-year Sharpe and minimum rolling Sharpe at least -0.25, rolling drawdown no worse than
-25%, and top-decile absolute contribution at most 50%. Existing placebo p-values must remain
at most 0.05, signal-selection PBO at most 0.20, and DSR at least 0.95.

Thresholds are not changed after observing the result. Failure yields
`RESEARCH_PREVIEW_ONLY`.

## Main-release boundary

An engineering release may be `RESEARCH_PREVIEW_READY` even when Alpha gates fail, provided
exact replay, point-in-time controls, capacity, trial count, sealed windows, offline replay,
tests, CI, and secret/path audits pass. Research preview is non-trading and disabled for
autonomous live execution.
