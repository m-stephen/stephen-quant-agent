# V7.3 — Frozen Survivor Full Alpha Court

## Objective

V7.3 tests the complete deduplicated union of the V7.1 and V7.2 CPCV survivors. It does not
generate, mutate or re-rank formulas using new labels. The 7 and 10 survivor sets share one
candidate, leaving 16 frozen identities.

## Frozen protocol

- Labels: 2022–2024 only. The 2025 validation and 2026 final-test windows remain sealed.
- Universe: prior-only dynamic Top 300.
- Portfolio: Top 10, CNY 3 million initial NAV.
- CPCV: 6 groups, 3 test groups, 5-day embargo, PBO no greater than 0.05.
- Candidate path gate: at least 15 of 20 folds positive.
- Standard costs: 3 bps commission, 5 bps sell tax, 5 bps slippage and 10 bps impact coefficient.
- Stress: all four cost terms doubled; return must remain positive.
- Falsification: 199 signal-shuffle and 199 return-permutation repetitions per candidate.
- Multiplicity: empirical-skewness/kurtosis DSR at least 0.95, carrying 81 prior V7.1/V7.2 Trials.
- Economics: annualized net Sharpe at least 0.50, maximum drawdown no worse than -25%, and zero
  capacity clipping.
- Walk-forward: the same Sharpe and drawdown thresholds apply to the expanding selector.

Each standard and doubled-cost execution is a distinct Trial. A hygiene-passing candidate set may
continue through diagnostics after a signal-gate rejection, but the failed gate remains explicit
and makes promotion impossible. No single strong return can override PBO, DSR, placebo, path,
walk-forward, cost or capacity failures.

## Outputs

`test-alpha-candidates` writes deterministic JSON and Chinese/English Markdown, per-candidate
execution artifacts, candidate-wide Court evidence and the complete Trial lineage. Local data paths
and real-data artifacts remain ignored by Git.
