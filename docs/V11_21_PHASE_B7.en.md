# V11.21 B7: day-scoped views and owned-child resource supervision

## Conclusion

Full regression: **1365 passed, 2 skipped in 498.90 seconds**. Training/account bar views and an owned-child resource supervisor are implemented. There was no new empirical experiment, market numerical read or Alpha certification. Historical Trial lower bound remains **3660**.

This is engineering verification, not a strategy-return report. The global production launch entrypoint is still incomplete; full-market source-to-independent-audit peak resources remain unmeasured.

## Implementation and equivalence evidence

- Training projects only explicitly scoped dates. Accounts construct the same ordered `StatefulBar` fields per day, with replayable iteration and no retained second full bar-object matrix. Excluded dates fail before accessing their numeric rows.
- Synthetic comparisons against the old materialized structures preserve exact training pairs, complete account reports and canonical SHA-256, including missing bars, blocked orders, capacity clipping and recovery.
- A 60-day × 80-stock lifetime test creates 4800 bars in total, retains at most 160 across adjacent iterator steps and releases them all afterwards. This is an object-lifetime assertion, **not a measured whole-pipeline RAM reduction**.
- Daily/flow indexing now uses nested daily dictionaries instead of full-panel `(date, stock)` tuple keys and a redundant daily index. Duplicate/orphan checks, timing and ordering are unchanged. Flow source rows are released after the bridge and before risk/bar-panel construction.
- The complete synthetic epoch fixture tracks the actual cache via weak references: the producer cache is gone after the backend returns, before independent audits. This check did not rerun old B5b/B6 experiments.

The audit retains independent source/model/target/account mathematics, but shares the non-financial bar-structure adapter and existing infrastructure. It is not a completely independent software implementation.

## Resource supervision and limitations

The new primitive operates only its own Windows child handle: explicit argv, hidden window, no shell and AlphaPai credential variables removed from the child environment. It validates finite positive resource limits and named SHA-256 evidence before launch, then records memory, free physical RAM and actual UTC time.

Success, prelaunch refusal, memory/free-RAM/time guards, measurement exceptions, nonzero exits, interrupts and termination failures retain terminal receipts. There is no automatic retry or operation overwrite. Exit zero without any memory samples cannot be certified complete. Termination failures explicitly remain `TERMINATION_FAILED`, not a false claim that the child stopped.

This is a **supervision primitive, not empirical launch authorization**. Polling is not an OS hard limit; it covers the owned process, not arbitrary descendants. Source rows/history/rank panels can still be fully resident. Power loss or an unwritable disk may leave only START/log/samples. The future launcher must still bind actual parent evidence, original source/target bytes, code, published preregistration, all 23 Trials and a cross-operation exclusive claim before numerical access.

## Tests, CI and next step

- Full JUnit: `artifacts/flow-response/phase-b7-regression-20260907.xml`; 1367 total / 0 failures / 0 errors / 2 skipped, JUnit time 497.712 seconds.
- SHA-256: `85130f405c826734e7f21f51fbf08dc1c3dd82fed061b89fe52401543226d8ae`.
- Skips are the non-Windows capability branch and unavailable local symbolic-link capability, not passes.
- Earlier targeted runs of 63 passed / 61.51 seconds and 28 passed / 1.72 seconds are subsets, not additive. New coverage contains 6 view tests and 22 supervisor tests, including an actual hidden Windows child with measured memory and successful exit.
- Ruff `src tests scripts` and format checks for all 9 changed Python files pass. Initial broad-exception lint findings were addressed with justified boundary-specific suppressions before the final regression; interrupts remain recorded then propagated.
- B6 CI run 34084914378 is **cancelled**, not successful. Logs reached about 80% before cancellation, consistent with the old 20-minute job limit. The same runner and full suite remain; the job limit is now 40 minutes. The next commit's remote status requires separate verification.

B8 should directly complete the once-only production launcher and synthetic refusal/lifetime tests, not rerun storage benchmarks or expand permissions. One bounded empirical run can follow only after launch, preregistration, complete budget and resource guards are ready. Use only the original frozen 2022–2024 daily/flow inputs: no 2021 numerical warmup, 2025/2026, new warehouse sources or altered anchors.

CNY 3m, 82/164 bps, every control, exploratory threshold and DSR/PBO/placebo/path requirement remain frozen. Reused development history is not fresh OOS. Assessment: **engineering evidence is shareable with caveats; Alpha validity has no new evidence.**
