# V2 M3 Test Results (English)

## Conclusion

- **Engineering acceptance: passed.** Marginal scorecards cover residual/conditional IC, long-only and long-short increments, costs, Sharpe, drawdown, turnover, tail return, capacity, complexity and data cost.
- **Ranking objective: passed.** In the frozen fixture, the lower-standalone-IC but orthogonal candidate ranks above the higher-IC redundant candidate.
- **Fold-local acceptance: passed.** Every residual model fits only its fold's train rows; changing test rows does not alter fitted coefficients.
- **Determinism acceptance: passed.** Identical frozen inputs produce identical scorecards and rankings.
- **Status boundary: passed.** V1.8.21 remains `reference_only`; the engine cannot promote a research-only record to validated alpha.

## Interpretation

This corrects the search bias toward standalone IC. When a candidate is largely contained in the reference portfolio, high standalone IC may add little portfolio value. An orthogonal candidate receives priority through residual IC and incremental portfolio metrics.

## Validation record

- Focused M3 tests: 4 passed.
- Full test suite: 208 passed.
- Static checks: passed.
- Python compilation check: passed.
- 2025 validation / 2026 final test: unopened.
- The fixture validates ranking behavior only and is not alpha evidence.

## Next step

Proceed to M4: store failures, lineage and decisions in an append-only structured failure graph; freeze budgets and policy at epoch start and permit prior updates only after epoch closure.
