# V2 M2 Test Results (English)

## Conclusion

- **Engineering acceptance: passed.** Novelty Gate and Cheap Diagnostics are implemented, with a typed reason code for every rejection.
- **Duplicate benchmark: passed.** Exact duplicate recall is 100%; empirical duplicate precision and recall are both 100%.
- **Workload target: passed.** Four of six frozen-fixture candidates are rejected before CPCV, reducing expensive workload by 66.7%.
- **Known-valid engineering fixtures: passed.** Both known-valid fixtures are retained, for 100% recall.
- **Important limitation:** fixture metrics verify engineering regression only; they do not represent statistical recall or profitability for real alpha.

## Diagnostic coverage

Typed reports now cover coverage, missingness, staleness, daily IC/RankIC, residual IC, quintile shape, long/short decomposition, rank turnover, holding decay, style/industry exposure, date/regime concentration and simplified cost-adjusted spread.

## Validation record

- Focused M2 tests: 5 passed.
- Full test suite: 204 passed.
- Static checks: passed.
- Python compilation check: passed.
- 2025 validation / 2026 final test: unopened.
- No fixture result was registered as alpha.

## Next step

Proceed to M3: calculate leakage-safe residual/conditional IC and marginal portfolio value against a versioned reference portfolio, demonstrating that a lower-standalone-IC but more orthogonal candidate can outrank a higher-IC redundant candidate.
