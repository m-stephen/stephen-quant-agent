# V2 M5 Test Results (English)

## Final conclusion

- **V2.0 shadow-mode engineering acceptance: passed.** One command completed proposal, audit, novelty, diagnostics, marginal value, failure learning and decision.
- **Autonomous-loop objective: passed.** The system proposed three initial hypotheses and generated one single-dimension revision from failure, registering four candidates in total.
- **All four decisions are present:** at least one each of `REJECT`, `REVISE`, `PROMOTE_FOR_FUTURE_VALIDATION` and `STOP_FAMILY`.
- **Dual-ledger integrity: passed.** The run wrote eight Search Ledger entries, and each of four numerical-feedback actions links its own Inferential Trial.
- **Budgets and stopping: passed.** Usage was candidate 4/6, compute 4/4, statistical trial 4/4 and token 0/1000; the exhausted family receives zero next-epoch budget.
- **Holdout and replay: passed.** Access to 2025 validation / 2026 final test was zero; Replay audit passed; offline replay made zero model requests.
- **This is not an alpha conclusion.** The promoted candidate enters only the future-validation queue; Alpha Court was explicitly not run on the synthetic fixture.

## Frozen formal run

- Implementation commit: `ae90efb825066b86ec47817657ed9be60635af81`
- Experiment: `exp_d1ad1036c3b74c25`
- Snapshot: `snap_7cef53a4ce05c38b`
- Snapshot SHA-256: `7cef53a4ce05c38b561251c8e1e3a0034d7f5b9a68a0ad037180c6e2a05e33ba`
- Replay Manifest SHA-256: `6e6e0b090d30b3ef5d25f176ffcbabdfb4823ef2feeb8aa7d152529b8790f497`
- Semantic Decision SHA-256: `c4234f283b946722e0617ecbca450a7c0c05534b04dbcbfaf8e29d02f90e9784`

## Decisions

| Family | Decision | Reason |
|---|---|---|
| flow_price_divergence | REJECT | EXACT_AST_DUPLICATE |
| margin_financing | REVISE | LOW_COVERAGE |
| margin_financing (revised) | PROMOTE_FOR_FUTURE_VALIDATION | POSITIVE_ORTHOGONAL_ENGINEERING_FIXTURE |
| large_flow_surprise | STOP_FAMILY | FAMILY_EXHAUSTED |

## Automated validation

- Focused M5 tests: 6 passed.
- Full test suite: 218 passed.
- Ruff, compileall and git diff check: passed.
- Registry audit: snapshot, experiment and trial counter all passed.
- Offline replay: verified=true, sealed access=0, model requests=0.

## How to test

```text
stephen-quant --db artifacts/v2-shadow.sqlite3 v2-shadow-validate --config configs/v2.0-m5-shadow.json --output reports/v2.0-shadow
```

The next phase should connect real QD data through a new preregistered research experiment and run formal cheap diagnostics, CPCV, placebo, DSR/PBO and cost gates without opening the 2025/2026 sealed windows.
