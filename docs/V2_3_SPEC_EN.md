# V2.3: Frozen-Signal Same-Day Style Residualization

## Objective

V2.3 tests one pre-registered hypothesis: removing decision-time price-momentum and liquidity
exposure from the frozen V2.1 signal improves executable Top-5 risk-adjusted performance. It
does not search for a new factor, portfolio width, holding period, or threshold.

## Why industry neutralization is blocked

The available Shenwan files describe industry indices, not historical stock-industry
memberships with effective and availability timestamps. Using current classifications for
2022–2024 would create temporal leakage. V2.3 therefore fails closed on industry
neutralization and uses two supported controls instead:

- frozen `price_momentum_5_20d`;
- the logarithm of trailing 20-day average daily traded value.

OLS is fit independently inside each decision-date cross-section. Forward returns are labels
only and are never used to estimate residual exposures.

## Frozen boundary

- Source snapshot: `99b037baf97721ab438c54392b419ea96c994b68ef616a20b5fa234223928b23`.
- Signal: `flow_confirmation_20_20d`, fingerprint
  `13f4ddc002cb8f0bb59f057895f3fe8ca89eeb4a819820c11041f043ac8c117e`.
- Price control fingerprint:
  `dfa56be1f549e0ad3414e4319ef8a5f4b00cb02186e7ebca293d13334ef458ec`.
- Top-5, 20-session horizon, CNY 3 million, and the V2.1 cost/capacity model.
- Research data: 2022-01-04 through 2024-12-31; 2025/2026 remain sealed.
- Trial ledger: 42 inherited trials plus one candidate and one reversed-ranking negative
  control, for 44 cumulative trials.

The raw Top-5 control must reproduce V2.1 return, Sharpe, and drawdown to machine precision.
All prior evidence is bound into a canonical SHA-256 hash.

## Pre-registered gates

Promotion through Alpha Court requires all of the following:

1. exact raw-control replay and a materially changed residual signal;
2. mean absolute correlation with both controls at or below 0.01;
3. annualized net Sharpe at least 0.5265716607;
4. maximum drawdown no worse than -25%, positive net return, and no capacity clipping;
5. reversed-ranking annualized Sharpe no greater than zero;
6. both placebo p-values at or below 0.05, inherited PBO at or below 0.20, and trial-aware DSR
   at or above 0.95;
7. sealed-window flags remain false.

Passing the execution gates but failing statistical gates yields `PROMOTE_RESEARCH_ONLY`, not
an Alpha claim.

## Modes

- `dry-run`: validate configuration and local source keys without registry mutation.
- `research`: run the frozen control, two registered trials, falsification, and bilingual output.
- `replay`: verify the three artifact hashes and cumulative trial count without data paths.
- `kill`: stop before data or registry access.
