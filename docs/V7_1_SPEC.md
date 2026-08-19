# V7.1 — Non-degenerate Automatic Factor Validation

## Objective

Continue automatic factor discovery on the frozen 2022–2024 research window while replacing the
non-informative full-path average used for fixed factors in V7.0.

## Frozen search

- Research labels: 2022–2024 only.
- Validation/final test: 2025/2026 remain sealed.
- Point-in-time dynamic universe: at most 300 stocks per decision date.
- Automatic grammar: 16 formula identities selected without labels, both directions, 32 training
  Trials maximum.
- CPCV shortlist: at most 16 candidates.
- Six temporal groups, three test groups and five-day embargo.
- No execution, cost, placebo, DSR or Alpha Court claim in this research-only stage.

## Fold-selection PBO

For every audited CPCV fold and candidate, V7.1 computes the mean RankIC separately on the purged
training IDs and the complementary OOS test IDs. The training-side winner is selected independently
inside each fold, then ranked against all candidates on that fold's OOS scores. PBO is the fraction
of selected candidates whose OOS relative-rank logit is non-positive.

This avoids treating full combinatorial paths as independent when a fixed formula is not refitted
and every path traverses all temporal groups exactly once. Incomplete matrices, failed purge or
embargo audits, non-finite scores and fully degenerate fold matrices fail closed.
