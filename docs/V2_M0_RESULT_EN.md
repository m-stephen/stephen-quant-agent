# V2 M0 Test Results (English)

## Conclusion

- **Engineering acceptance: passed.** V1 factors migrate losslessly into V2 contracts, with hierarchical IDs, dual ledgers and replay auditing connected end to end.
- **Compatibility acceptance: passed.** All 191 tests pass and the V1.0–V1.8.21 capabilities remain in place.
- **Integrity acceptance: passed.** Neither Search Ledger nor Inferential Trial Ledger records can be deleted; Search Ledger records also cannot be modified.
- **Boundary acceptance: passed.** Text-only search does not consume an inferential trial. Any use of returns, labels, IC, backtests or validation feedback must link a registered Trial.
- **Research conclusion: M0 creates no alpha claim.** The V1.8.21 portfolio remains a research-only reference and cannot be labelled validated alpha.

## Verified capabilities

1. The complete V1 FactorSchema JSON and legacy fingerprint are embedded in the V2 contract, enabling reverse recovery and semantic verification.
2. Hypothesis, expression structure, parameter variant and test stage use independent deterministic IDs.
3. Search Ledger records proposals, derivations and feedback exposure; Inferential Trial Ledger continues to record statistical testing attempts.
4. Replay Manifest freezes the dataset snapshot, configuration, code version, seed, reference library, both ledger ID sets, raw LLM input/output and tool calls.
5. Replay audit verifies Experiment, Snapshot, SHA-256, Search entries and Trial relationships, and reports sealed-window access.

## Validation record

- Focused tests: 23 passed.
- Full test suite: 191 passed.
- Static checks: passed.
- Python compilation check: passed.
- 2025 validation / 2026 final test: unopened.
- New empirical trials: 0.

## Next step

Proceed to M1–M2: implement an executable hypothesis graph, evidence-source grading and a deterministic experiment compiler. Before execution, the compiler must enforce budgets, falsification rules, temporal boundaries and required controls.
