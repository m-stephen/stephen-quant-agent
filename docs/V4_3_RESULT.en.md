# V4.3 Test Result

## Decision

`REJECT_ALPHA_COURT`. The historical search is not small by raw candidate count, but it is narrow in independent information domains, directional coverage, and sparse-signal compatibility. Explicit inverse hypotheses recover statistically stable predictive signals, yet the current long-only execution mapping does not convert them into deployable alpha.

## Search breadth

- Historical generation plans: 9.
- Raw proposals: 202.
- Canonical unique candidates: 152.
- Domain-budget admissions: 109.
- Ready domains: price, auction, fund flow, margin, chip distribution, limit events, and cross-source interactions (7 total).
- Main gaps: only 6 unique chip candidates, 3 limit-event candidates, and 4 cross-source candidates.

## Strict discovery experiment

- Research window: 2022-01-04 through 2022-12-30.
- 2023 confirmation window: not opened.
- 2024 final window: not opened.
- New candidates: 9 explicit inverse hypotheses, each counted as a separate Trial.
- Training-screen survivors: 6.
- CPCV: 5 groups, 2 test groups, 20-day purge/embargo, 4 combinatorial paths.
- All six candidates had 4/4 positive paths; PBO=0.
- Signal and return placebo: p=0.005 / 0.005.
- Global recorded Trials: 804, including failed and configuration-correction attempts.

The best candidate was `chip_cost_band_compression_5_20_inverse_20_20d`:

- CPCV mean path RankIC: 0.1246.
- Annualized net Sharpe: -0.2709.
- Net return: -13.52%.
- Maximum drawdown: -32.48%.
- DSR: 0.0139.

The signal gate passed, but Alpha Court rejected the candidate.

## Engineering fixes

1. CPCV now uses only dates with valid cross-sectional IC for every candidate, so sparse or constant-signal dates cannot trigger a `KeyError`.
2. Dynamic membership is bounded by `research_end` before the instrument load set is built.
3. Configuration validation rejects a `minimum_positive_paths` value above the actual CPCV path count.
4. A deterministic domain catalog now provides canonical deduplication, per-domain budgets, and a data-readiness matrix.
5. A local append-only forward-shadow ledger starts on 2026-08-19 and rejects backfilling, future observations, timezone-free timestamps, and operation overwrite.

## Next step

Do not mechanically add more same-family formulas. The next experiment should focus on IC-to-return conversion: test AVOID/cash exposure, event cooldown, holding period, and rebalance frequency. Freeze that mapping inside 2022 before opening the 2023 confirmation window.
