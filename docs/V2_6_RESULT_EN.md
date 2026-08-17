# V2.6: 2025 independent validation result

Final decision: **`VALIDATION_FAIL_STOP`**. The frozen policy did not generalize to the
independent time window. It may not enter the 2026 final test or live trading.

## Core results

| Metric | Result | Gate | Outcome |
|---|---:|---:|---|
| Net return | -11.87% | > 0% | FAIL |
| Annualized net Sharpe | -0.1854 | >= 0.5 | FAIL |
| Maximum drawdown | -25.05% | >= -15% | FAIL |
| Minimum rolling six-period Sharpe | -0.8505 | >= -0.25 | FAIL |
| Return concentration | 70.79% | <= 50% | FAIL |
| Signal placebo p-value | 0.14 | <= 0.05 | FAIL |
| Return placebo p-value | 0.17 | <= 0.05 | FAIL |
| Combined DSR | 39.83% | >= 95% | FAIL |

The run completed 12 non-overlapping validation periods: seven `RISK_ON` and five
`RISK_OFF`, so regime coverage passed. Capacity clipping was zero. PBO is not applicable to
the frozen single-policy test; V2.5's 46.83% value remains a historical warning.

## Integrity conclusion

Readiness passed with 242 daily sessions, 243 dynamic-universe dates, a mean universe of 50,
at least 47 securities in every validation cross-section, and no input after 2025-12-31.
Exactly one new trial was registered, bringing the cumulative count to 48; a second run was
automatically rejected. Offline hash replay passed for all four formal artifacts.

This is evidence to stop the current candidate, not permission to tune its threshold. A new
research epoch must preregister genuinely new factor hypotheses while keeping 2026 sealed.
