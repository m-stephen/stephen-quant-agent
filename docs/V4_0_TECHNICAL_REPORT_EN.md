# V4.0 OHLCV Alpha Research and Paper Platform — Technical Report

## Technical summary

V4.0 completes the single-user research, portfolio-conversion, audit-memory, sealed-release and
historical paper-replay scope frozen in Issue #105. The system no longer fails to surface
attractive structure: 990 preregistered candidates reduce to 218 effective mechanism hypotheses,
and 15 orthogonal representatives retain positive raw and residual RankIC in both 2023 and 2024.
The final decision is nevertheless `NO_DEPLOYABLE_ALPHA`. The portfolio selected on 2023 produces
negative excess performance in the untouched 2024 shadow step, and DSR fails its multiplicity gate.

This is a material research-capability improvement, not a trading authorization. The 2025/2026
windows remain `SEALED` and were not read, enumerated or used for selection.

## Statistical diversity improved, but economic stability did not

| Item | Result |
|---|---:|
| Preregistered candidates | 990 |
| Effective mechanism hypotheses | 218 |
| Representatives with positive raw/residual IC in 2023 and 2024 | 15 |
| Audited Trials | 1,239 |
| Agent memory nodes | 990 |
| PBO | 0.000 |
| Signal/return placebo p-values | 0.005 / 0.005 |
| DSR probability | 0.180348 |
| Final decision | `NO_DEPLOYABLE_ALPHA` |

Correlation clustering and family quotas prevent the V3.1 variants of 120-session reversal from
monopolizing Court. Drawdown recovery, intraday return, upside volatility, range volatility and
breakout-position families also contain stable residual candidates. The bottleneck has moved from
candidate poverty to unstable signal-to-portfolio conversion.

## The frozen portfolio fails in 2024

The selected candidate remains `ohlc_return_close_120_20d_neg`. The portfolio is selected only on
2023: top five, equal weight, no buffer and 20 equal-capital staggered sleeves at the primary CNY 3m
NAV.

| Window | Net excess Sharpe | Cumulative excess | Maximum drawdown | Mean turnover |
|---|---:|---:|---:|---:|
| 2023 confirmation | 3.9095 | +25.09% | -9.14% | 3.96% |
| 2024 shadow | -1.1410 | -6.95% | -16.43% | 4.24% |

The failed gates are `dsr` and `shadow_sharpe`. Passing PBO, placebo and drawdown gates does not
override the loss of economic stability.

## Simple ensembles do not repair the failure

Equal, IC-weighted, risk-parity and shrunk ensembles use five same-horizon orthogonal
representatives. Their 2023 net excess Sharpe ranges from 2.34 to 3.38, but every 2024 value is
negative, from -0.30 to -0.58. Deep networks and PPO therefore remain disabled: added complexity
would expand selection bias without a passing simple baseline.

## Capacity is not the binding problem

The same frozen configuration has no five-percent prior-day-amount clipping at CNY 1m, 3m, 5m,
10m or 20m. This only indicates approximate executability. Every NAV inherits the negative 2024
direction, so changing capital does not solve the alpha failure.

## Scope, data and metric definitions

- QD daily OHLC, volume, amount, open tradability and frozen dynamic membership.
- 2021 warm-up; 2022 discovery; 2023 confirmation; 2024 retrospective shadow.
- RankIC is daily cross-sectional Spearman correlation.
- Residual IC is decision-local orthogonalization against momentum, volatility, Amihud liquidity
  and price-level proxies.
- Each holding-period sleeve receives `1/horizon` of capital and is merged by actual maturity date;
  commission, tax, slippage and impact are explicit.
- Capacity uses five percent of prior-session amount as a frozen approximation.

## Method, validation and counterevidence

1. All 990 formulas, signs, windows and horizons are frozen before observing outcomes.
2. Discovery-only daily RankIC is clustered at absolute correlation 0.85, then capped at four
   representatives per family.
3. Only frozen representatives reach 2023/2024; residualization is within the decision-day cross
   section.
4. Top K, weight and buffer selection uses 2023 only; 2024 cannot reselect.
5. Every holding offset runs with its correct capital share.
6. Validation caught an initial full-capital duplication across sleeves. After correction, two
   independent operations reproduced the snapshot, shortlist, selection, metrics and decision.
7. Final engineering validation: Ruff passed; 411 tests passed and one skipped.
8. The aggregate paper-broker ledger contains 222 immutable period records for cash, planned
   orders, fills, mark-to-market PnL and NAV; every record has `live_order=false`.

## Integrity and sealed evidence

- Dataset snapshot: `b3a638ceb564292a5a36a577257bfacfbc0db05e5147cb3879bdc68d5c27a68e`
- Candidate/shortlist: `058352c763225f6b4b29b396afb51de2341e61fb1827342905de9c9ed33d0509`
- Portfolio: `f8711679b8d837ca7beae50f0bfb8433073c548db8415f5760a5bafeab8ac0f2`
- Gates: `62d9ea2eca22b95f6a40f946d8b04e7cb713052ba5b31ffc91aebb2ea4fbb920`
- Release manifest: `206d4f9ead602f6870fbb8034c3ee183595bd9564bf169146dcf7e1072269a12`
- Allowed years: 2022–2024; sealed years: 2025 and 2026.

## Limitations and uncertainty

- The project has inspected 2022–2024 before; this is calibration and retrospective shadow
  evidence, not a fresh untouched sample.
- Deferred historical industry PIT and complete corporate actions may change attribution.
- Capacity is a daily-amount approximation without order-book queues or realized impact curves.
- The paper broker is an aggregate historical replay, not an instrument-level execution simulator;
  it submits zero live orders.
- DSR uses 990 candidate-level hypotheses; the 1,239 audit Trials are disclosed separately.

## Recommended next step

Freeze this research space. Do not tune against 2024. The defensible next action is either a
separately authorized one-time 2025 validation of the sealed Release Candidate, or a new candidate
identity and Trial budget after genuinely new data arrives. Gates must not be lowered to relabel the
current result as alpha.

## Further questions

- Does a one-time 2025 out-of-sample test confirm reversal or another orthogonal representative?
- Do the 15 residual candidates survive authoritative industry, corporate-action and flow timing?
- Does realistic queueing and impact further weaken economic performance?
