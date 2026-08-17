# V2.5: Preregistered Regime-aware Portfolio Epoch

## Objective

V2.5 does not change the V2.3 factor formula or open 2025/2026. It tests whether the frozen
residualized fund-flow signal should be used differently under a point-in-time market regime.

The regime is fixed before execution as the cross-sectional median of oriented five-day price
momentum among eligible instruments. A median above zero is `RISK_ON`; otherwise it is
`RISK_OFF`. The zero threshold is neither trained nor searched.

## Frozen policies

Exactly two candidates are allowed:

1. `risk_off_cash`: residualized flow Top-5 in risk-on; liquidate to cash in risk-off.
2. `risk_off_momentum_fallback`: residualized flow Top-5 in risk-on; price-momentum Top-5 in risk-off.

The V2.3 baseline is an exact replay, not a new trial. Each candidate creates one inferential
trial, moving the cumulative ledger from 45 to 47. No threshold or third policy may be added
after seeing results.

## Multiplicity boundary

DSR uses 47 cumulative inferential exposures and the selected candidate's actual return moments.
Strategy-family PBO compares the baseline and two candidates on their common 35-period return
matrix, but its scope is explicitly `PORTFOLIO_POLICY_SELECTION_ONLY`. It is not complete
adaptive-search correction.

## Gates

Engineering gates cover exact replay, PIT regime inputs, common dates, two new trials, zero
capacity clipping, explicit PBO scope, offline replay, and zero sealed-window access.

Alpha gates require at least +0.10 Sharpe improvement, drawdown no worse than -25%, at least
two-thirds positive years, worst-year return at least -10%, annual and rolling Sharpe at least
-0.25, top-decile absolute-return contribution no more than 50%, placebo p-values no more than
0.05, PBO no more than 0.20, and DSR at least 0.95.

The concentration gate is an inherited V2.4 guardrail. Its omission from the Issue was found
during release audit and conservatively corrected without changing candidates, threshold,
selection, or trial budget; the correction can only add a failure.
