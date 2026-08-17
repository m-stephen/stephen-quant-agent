# V2 M4 Test Results (English)

## Conclusion

- **Structured failure storage: passed.** Failure nodes, edges, events, epochs and decisions are stored in SQLite with a versioned query interface.
- **Immutability: passed.** Triggers reject UPDATE and DELETE against failure/history/epoch/decision records.
- **Epoch freezing: passed.** An open epoch cannot replace policy, and a next epoch can start only after closure.
- **Stopping rule: passed.** A family reaching the exhaustion threshold receives zero next-epoch budget and `STOP_FAMILY / FAMILY_EXHAUSTED`.
- **Explainable adaptation: passed.** High cost maps to Mutate, multiple failure types map to Recombine, and no failure maps to Exploit; every decision retains source failure-node IDs.
- **Determinism: passed.** The same failure graph produces identical budgets and decisions even when family input order differs.

## Validation record

- Focused M4 tests: 4 passed.
- Full test suite: 212 passed.
- Static checks: passed.
- Python compilation check: passed.
- 2025 validation / 2026 final test: unopened.

## Next step

Proceed to M5: orchestrate proposal, audit, novelty, cheap diagnostics, marginal value, validation gates and failure learning into a killable, replayable, default shadow-mode one-command workflow.
