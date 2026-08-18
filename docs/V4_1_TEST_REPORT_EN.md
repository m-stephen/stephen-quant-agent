# V4.1 A-share Semantic Alpha Search Test Report

## Decision

V4.1 is implemented and was run once on the frozen local dataset. The final decision is
`NO_DEPLOYABLE_ALPHA`. The system found a candidate and economic mapping that looked unusually
strong in 2022/2023, but the frozen 2024 shadow result reversed. It is neither reliable alpha nor
deployable.

This resolves the earlier inability to find even an overfit-looking signal while demonstrating
that the falsification gates reject a spectacular selection-period result that collapses out of
selection.

## Frozen design

- 2021: lookback warm-up only.
- 2022: candidate discovery, economic-shape diagnosis and redundancy control.
- 2023: select `BUY`, `AVOID` or `TIMING` use and portfolio mapping.
- 2024: frozen retrospective shadow; diagnosis is allowed, reselection is not.
- 2025/2026: `SEALED` and excluded from selection and tuning.
- 288 semantic proposals; every proposal and portfolio attempt enters the Trial Ledger.

## Added capabilities

1. Semantic candidate identities use `Event / Context / Quality / Direction / Output`, with
   `Output=UNASSIGNED` before evaluation.
2. IC-to-economics diagnostics report RankIC, decile returns, monotonicity, long and short legs,
   date concentration, regimes, and positive-IC/negative-long-leg contradictions.
3. Prediction is separated from `BUY`, `AVOID` and `TIMING` economic use.
4. A-share mechanisms cover T+1 delayed feedback, negative-return asymmetry,
   overnight/intraday divergence, gap fill, price-limit proximity and exhaustion, auction,
   fund-flow, margin and limit-event persistence.
5. Regimes use only the previous 20 completed sessions: trend, breadth, volatility, correlation
   and liquidity shock. Decision-day observations cannot alter that day's state.
6. The final audit includes CNY 1m/3m/5m/10m/20m capacity, CPCV/PBO, DSR, signal shuffle and
   return permutation.

## Real-data result

| Metric | Result |
|---|---:|
| Snapshot SHA-256 | `fc74aa4f5bead9db3b09d5df7fabb24475c662d26e25d3a9863b74383712f38d` |
| Proposed / evaluated | 288 / 288 |
| Effective mechanism clusters | 85 |
| Audited Trials | 617 |
| Selected candidate | `limit_exhaustion_60_20d_pos` |
| Economic use | `TIMING / breadth=5 / risk_off` |
| PBO | 0.000 |
| Signal-shuffle / return-permutation p | 0.005 / 0.005 |
| DSR probability | 0.1796 |

All four enhanced sources were loaded under explicit visibility rules: auction 969 files and
393,040 rows; fund flow 969 and 393,035; margin 969 and 326,978; limit events 969 and 398,259.
Close-derived sources are usable only from the next session. Auction observations are usable for
09:30 decisions only after the adapter proves 09:26 availability.

## Economic conversion

| Window | Excess Sharpe | Cumulative excess | Max drawdown | Active days |
|---|---:|---:|---:|---:|
| 2023 usage selection | 6.0482 | 32.38% | -5.41% | 125 |
| 2024 frozen shadow | -4.5646 | -31.71% | -34.01% | 75 |

The underlying cross-sectional shape remained positive in 2022, 2023 and 2024: RankIC was about
0.0656, 0.0344 and 0.0617, while top-leg excess return was about 0.89%, 1.87% and 1.00%.
What failed was the 2023-selected `risk_off + TIMING` conversion. Predictive ranking therefore did
not imply a stable frozen trading rule.

No capacity clipping occurred from CNY 1m through CNY 20m, but every size produced the same
-31.71% shadow excess return. The failure is regime/mapping instability, not capital capacity.

## Alpha Court

Failed gates:

- `dsr`: 0.1796 versus the required 0.95.
- `shadow_sharpe`: -4.5646 versus the required 0.50.
- `shadow_drawdown`: -34.01% versus the 25% limit.

Passing PBO and placebo tests cannot override those failures. V4.1 does not present this candidate
as deployable alpha.

## Boundaries

- The project inspected 2022–2024 in earlier versions, so this remains retrospective evidence,
  not a new blind test.
- The static 10%/20% board-code limit proxy does not fully identify historical ST or IPO no-limit
  intervals.
- Historical industry PIT and authoritative corporate-action inputs remain incomplete; missing
  fields were not fabricated.
- The next experiment should predeclare simpler, more stable state conversion and wait for a truly
  untouched holdout or forward paper-trading evidence instead of reselecting on 2024.
