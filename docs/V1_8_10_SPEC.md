# V1.8.10 — Exploratory Composite CPCV

## Integrity status

This experiment was proposed after observing the V1.8.9 2024 validation results. It is therefore
an explicitly post-validation exploration, not independent confirmation. The consumed 2024
window is moved into the research interval. Calendar year 2025 becomes the new untouched
validation window; 2026 remains the final sealed test window.

## Frozen research design

- Data history: 2021-07-01 through the first session after 2024-12-31.
- Exploratory research: 2022-01-04 through 2024-12-31.
- Fresh validation reservation: 2025-01-03 through 2025-12-31.
- Final test reservation: 2026-01-05 through 2026-08-14.
- CPCV: 6 chronological groups, 3 test groups, 20 folds, 10 OOS paths.
- Purge: closed next-open label intervals.
- Embargo: 5 calendar days.
- Component transforms: direction-adjusted daily cross-sectional ranks.
- Fold-learned weights use positive mean training RankIC only. If every training RankIC is
  non-positive, the fold falls back to equal weights.

All transforms and learned weights are fitted inside each fold. The 2025-01-02 open is loaded only
as the endpoint of the final 2024 next-open research label. It is excluded from validation, which
starts on 2025-01-03. No later 2025 partition and no 2026 partition may be loaded or hashed by this
command.

## Predeclared configurations

1. `volume_control`: volume surprise only.
2. `volume_trend_lowvol_equal`: equal-weight volume surprise, trend efficiency, and low Parkinson
   volatility.
3. `volume_trend_lowvol_train_ic`: the same three components with fold-local positive-RankIC
   weights.
4. `all_five_train_ic`: fold-local positive-RankIC weights over volume surprise, trend efficiency,
   low Parkinson volatility, skip-recent momentum, and range position.

These are four Trials in one Experiment. No additional weight rule or component subset may be
added after results are observed.

## Research gate

The highest mean OOS-path RankIC configuration may advance to the untouched 2025 validation only
if all conditions pass:

1. CPCV hygiene audit is fully clean.
2. Mean path RankIC is at least 0.02.
3. At least 8 of 10 OOS paths have positive RankIC.
4. PBO is at most 0.20 across all four recorded configurations.

Passing this gate authorizes one frozen 2025 cost-aware backtest. It does not authorize opening
the 2026 final test.
