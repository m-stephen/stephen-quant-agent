# V1.8.8 training-only factor screen

This document freezes the first factor-library pruning decision before any new validation returns
are examined.

## Lineage

- Screen method: `qd-factor-redundancy-screen-1.0.0`
- Training window: 2023-01-03 through 2023-12-29
- Instruments: frozen 20-stock V1.8.6 universe
- Source snapshot SHA-256: `644f6d6a89fa23329bc220235b4785ccb5fd834e772633a3ce758251f7c90058`
- Eligible factors: 20
- Pair comparisons: 190
- Daily cross-sections: 242
- Redundancy threshold: absolute mean RankIC correlation at least 0.80
- High-correlation pairs: 11

No forward-return statistic was used by this screen.

## Strongest redundancy findings

| Pair | Mean rank correlation |
|---|---:|
| `ret_20` / `signed_volume_mom_20` | 0.977 |
| `atr_20` / `parkinson_vol_20` | 0.965 |
| `parkinson_vol_20` / `volatility_20` | 0.906 |
| `mom_120_skip_20` / `ret_120` | 0.897 |
| `atr_20` / `volatility_20` | 0.888 |
| `ret_20` / `trend_slope_20` | 0.871 |

## Frozen shortlist

Only these economically distinct new candidates may proceed to separate validation Trials:

1. `mom_120_skip_20` — selected as the long-momentum representative because its recent-month
   exclusion was predeclared before screening.
2. `trend_efficiency_20` — path-quality signal with no threshold-level redundancy finding.
3. `range_position_20` — range-location signal with no threshold-level redundancy finding.
4. `volume_surprise_5_20` — participation-change signal with no threshold-level redundancy finding.
5. `parkinson_vol_20` — the single selected range-risk representative; ATR and close volatility
   must not be tested alongside it as independent hypotheses in the same round.

`dollar_liquidity_20` is retained as an execution/capacity control, not promoted as Alpha.
`intraday_strength_20` and `signed_volume_mom_20` are held back because they overlap strongly with
the existing 20-period momentum family.

## Next validation rule

The five shortlisted factors are five distinct Trials and must all count toward multiplicity. They
will be evaluated on the already declared 2024 validation window with identical universe,
portfolio, costs, benchmark, and placebo settings. No parameter variants are allowed in this round,
and the reserved 2026 final-test window remains unopened.
