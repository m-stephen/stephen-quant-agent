# V11.21 B20: frozen-model continuation launcher

Date: 2026-09-07. **This increment is engineering and synthetic testing, not a new market backtest. The actual cumulative Trial lower bound remains 3707; there is no new usable-Alpha conclusion.**

## Implemented

1. Bind both failed experiments, the original B17 diagnostic, its zero-Trial append-only explanation, historical native ledgers, inputs, original anchors and the current clean commit. Never promote the original B17 `UNRESOLVED` to PASS.
2. Preparation reads hashes, archived evidence and date-only coverage metadata; it does not decode accounts or execute numerical backtests. No caller-selectable costs, years, strategies or thresholds.
3. Before launch, verify actual Issue184 preregistration and resource conditions, then exclusively create one cross-worktree shared claim. Reserve all22 native account Trials before numerical work. Failure preserves the full budget and actual reserved count, without automatic retry.
4. Run producer and independent auditor in separate bounded children. Retain each stage's four-hour maximum, 10 GiB private-memory cap and 4 GiB available-system-memory floor. Only actual supervision can establish empirical resource sufficiency.
5. Reuse14 annual models and28 historical cost bindings without production refits. Execute all22 frozen accounts, not selected winners. Previously saved targets and both exact original anchors must match.
6. The parent verifies actual child exit, complete native results and byte hashes before auditing. Results, database and audit are not overwritten; an independently audited `ASSESSMENT.json` remains `validated_alpha=false` with statistical tests NOT_RUN.

These are single-user research-integrity controls, not multi-user identity management or an OS security sandbox.

## Usage order

In the clean dedicated worktree, after this commit's tests and all required CI groups pass:

```text
python scripts/run_flow_response_continuation.py prepare --output artifacts/flow-response/checkpoints/continuation-plan.json
```

Review the complete plan and preregister its canonical SHA-256, full22-account budget and frozen contract on Issue184. Then use the actual comment ID:

```text
python scripts/run_flow_response_continuation.py run --plan artifacts/flow-response/checkpoints/continuation-plan.json --preregistration-comment <actual-comment-id>
```

This does not authorize replaying consumed historical experiments. Never rerun the old002/003/B17 launchers. If the new shared claim exists, inspect its state; do not change the output directory or delete receipts to bypass once-only execution.

## Test evidence

The preceding `d31c04c1` commit completed [CI34126141549](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34126141549):

| Group | Result | Seconds |
|---|---|---:|
| Python3.10 / trace120 |1524 passed, 2 skipped|600.15|
| Python3.10 / trace0 |1524 passed, 2 skipped|535.68|
| Python3.12 / trace120 |1524 passed, 2 skipped|511.91|

All JUnit completion checks and Ruff checks passed. The3.10/trace120 group emitted an actual120-second stack dump and completed. Both earlier native SIGSEGV failures remain archived; their root cause is unproven, not permanently fixed by these passes.

New launcher boundary tests:44 passed in6.30s. Coverage includes shared claims, plan binding, actual native reservations, retained failure debt, modified evidence, original diagnostic semantics, missing supervision and invalid promotion.

Complete numerical-chain test module:45 passed in329.52s. The new launcher integration test executes actual synthetic numerical backtests and independent auditing (80.72s), stubbing only host supervision and external preregistration. It creates the independent ASSESSMENT, matches every account to the frozen synthetic reference and rejects all post-terminal replays. This is neither a real-market run nor a new empirical Windows supervisor measurement.

Keep the intermediate35/42-test boundary results; do not add overlapping counts to the final44. Final Ruff/JUnit completion checks are recorded separately. This commit still needs complete remote CI; preceding-commit success is not interchangeable evidence.

## Interpretation and next step

- No new real preregistration, shared claim or22-account operation has occurred. 3729 is the required post-launch lower bound, not the observed current count.
- Verify this increment's tests and CI first; only then prepare/preregister a real plan and execute one bounded continuation. Preserve failures instead of retrying for a preferred result.
- Reused2023–2024 data remains development evidence. No2025–2026 tuning. Engineering reproducibility or a development-screen pass is not Alpha Court approval.
- A genuine candidate still needs all-history multiplicity, empirical skewness/kurtosis, DSR/PBO/placebo, paths, capacity, credible execution and independent evidence. One shuffle control is not a statistical p-value. Do not lower gates, trade automatically or merge main.

The Chinese version states the same conclusions.
