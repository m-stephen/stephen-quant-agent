# V1.8.14 — Predeclared Microstructure Candidate Gate

## Objective

Start a genuinely new, economically motivated feature family after the V1.8.10 composite was
rejected. Freeze the candidate count, formulas, time windows, CPCV design, and acceptance gates
before observing any candidate return.

## New registered factors

1. `overnight_gap_reversal_20@1.0.0`: the mean open-to-previous-close gap over 20 sessions,
   interpreted contrarian. The hypothesis is that repeated opening overreaction partially reverts.
2. `close_location_20@1.0.0`: the mean normalized location of the close inside the daily range
   over 20 sessions. It proxies persistent intraday buying or selling pressure.

Both use only OHLC values available by decision close. Their formulas and directions are immutable
factor-registry entries and are tested for determinism and timing hygiene.

## Sequential implementation

1. The signal stage evaluates all four Trials with day-level cross-sectional CPCV and produces
   detailed English and Chinese reports. Every stock from one trading day stays in the same fold.
2. A failed signal gate ends the family immediately. No cost backtest, DSR, placebo, or validation
   access is permitted.
3. A passed signal gate authorizes a second in-research-window stateful execution and
   falsification stage. It still does not open 2025.

## Four frozen Trials

The machine-readable declaration is `configs/v1.8.14-candidates.json`:

- SHA-256: `b11a97334b3eee5500b83c9a6178990c198287c5fc7f49d3e586c833ba115b3c`.

1. overnight-gap reversal alone;
2. close-location value alone;
3. equal-rank combination of both;
4. fold-local positive-RankIC weighting of both.

No fifth subset, weighting rule, lookback, or sign change may be added after results are observed.
Any such change starts a new Experiment and increments the Trial ledger.

## Evaluation design

- Research only: 2022-01-04 through 2024-12-31.
- Validation reservation: 2025-01-03 through 2025-12-31.
- Final test reservation: 2026-01-05 through 2026-08-14.
- Frozen V1.8.11 point-in-time Top-300 membership.
- CPCV: six chronological groups, three test groups, 20 folds, ten reconstructed OOS paths.
- Purge: closed next-open label intervals; embargo: five calendar days.
- Every transform and learned weight is fitted inside its training fold.
- Cost-aware stateful execution uses the V1.8.13 rules only after the signal gate passes.

## Advancement gate

A candidate may reach the untouched 2025 validation only if the complete family passes:

1. mean OOS-path RankIC at least 0.02;
2. at least eight of ten OOS paths have positive RankIC;
3. PBO no greater than 0.20 across all four Trials;
4. DSR probability at least 0.95 after explicit costs;
5. signal and return placebo p-values no greater than 0.05;
6. all leakage, lineage, sparse-accounting, and data audits pass.

Failure at any gate rejects the family for 2025. Thresholds may not be relaxed after observation.
