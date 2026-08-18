# V5.4 Alpha Conversion Diagnostics and Constrained Generation Protocol

## Purpose

V5.4 addresses the observed gap between positive cross-sectional RankIC and negative costed
portfolio excess. It is a development-only study on reused 2022–2024 evidence. It cannot promote
an Alpha to final or deployable status.

## Phase A — fixed-formula conversion diagnostics

The formulas and directions are frozen from V5.3 before this run:

1. `limit_up_seal_strength_5_20_20d_negative`;
2. `auction_price_absorption_5_20_20d_positive`;
3. `margin_crowding_reversal_20_20_20d_negative`.

The diagnostic grid contains exactly 36 inferential Trials:

- 3 frozen signals;
- horizons 1, 5, 10 and 20 sessions;
- BUY breadths 20, 50 and 100;
- CNY 3m NAV;
- zero-cost and standard-cost results are paired inside the same Trial.

Each Trial records annual RankIC, gross and net excess return, gross-to-net cost drag, mean
turnover, active days, capacity clipping, positive offset paths, cross-sectional coverage,
quantile monotonicity and the ratio of gross alpha to standard-cost drag. No grid cell may alter a
formula. Diagnostic rankings do not rewrite V5.3 or the V5.2 forward candidate.

## Phase B — constrained candidate generator

The generator emits exactly 12 fingerprint-unique, direction-complete hypotheses from six
predeclared economic templates. It does not use Phase A results to add formulas:

- margin net-demand intensity, both directions, 20-session horizon;
- margin balance-price divergence, both directions, 20-session horizon;
- auction liquidity pressure, both directions, 5-session horizon;
- auction amount/price absorption, both directions, 5-session horizon;
- limit-seal retention, both directions, 5-session horizon;
- limit-event main flow relative to float capitalization, both directions, 5-session horizon.

Screening uses the frozen roughly 300-name/day market-wide balanced panel, BUY50, CNY 3m and
standard costs. A candidate is stable only if 2023 and 2024 RankIC are positive, net excess is
positive in both years, each year has at least 60% positive non-overlapping offset paths (1/1,
3/5, 6/10 or 12/20 according to the horizon), and no severe decay is present. At most one
candidate per domain may proceed.

Every generated hypothesis consumes one Trial. Stable candidates may consume one additional
standard, doubled and conservative execution Trial each, capped at nine validation Trials. No
formula, direction, horizon, breadth, cost or gate may be changed after results are observed.

## Trial and evidence policy

- Initial runtime starting count: 1,232; its 48 Trials remain in history after the path-gate defect.
- Corrected v1.0.1 replay starting count: 1,280.
- Fixed Phase A budget: 36 Trials.
- Fixed Phase B candidate budget: 12 Trials.
- Maximum Phase B stress budget: 9 Trials.
- 2021 is lookback only; 2022–2024 are reused development evidence.
- 2025–2026 remain outside this search and cannot be used for optimization.
- All input paths remain local and Git-ignored; only code, protocol and aggregate reports may be
  committed.

The only permitted positive conclusion is `DEVELOPMENT_LEAD`. Otherwise the decision is
`NO_CONVERTIBLE_ALPHA`. Neither conclusion authorizes live trading.

### Protocol correction before final acceptance

The first runtime exposed that a fixed 12-path gate is unreachable for a five-session horizon,
which has only five non-overlapping offsets. The empirical results were retained as 48 Trials.
Version 1.0.1 replaces that dimensionally invalid gate with the predeclared 60% fraction above and
requires a complete append-only replay starting from cumulative Trial 1,280. No formula, direction,
horizon, breadth or observed result changed; all five-session candidates had zero positive paths
and negative net returns in the first runtime.
