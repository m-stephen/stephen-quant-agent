# V11.21 B8: once-only empirical launch entrypoint

## Purpose and evidence status

`scripts/run_flow_response.py` and `flow_response_launch.py` connect the existing numerical backend to fixed evidence, a complete budget and recoverable execution records. They add no factor parameters, cost tiers, years or promotion shortcuts.

Current evidence concerns engineering gates and synthetic tests, not new market returns or certified Alpha. See the latest VERIFICATION and CONTINUATION entries for exact full-test counts/hashes and actual preregistration/run status.

## Three-stage workflow

1. **Prepare.** Require a clean committed worktree; bind actual source bytes, auditor and driver code, commit, Python executable and NumPy/DuckDB versions. Check fixed V11.20 RESULT/AUDIT, audit-bound native registry, inherited lineage and all twelve parent outcomes. Check the original V11.4 manifest and only daily/flow file bytes, plus original V11.11 anchor bytes. Project only daily dates for the 2022–2024 calendar; do not decode target weights or financial columns.
2. **Preregistration and exclusive claim.** Query the actual comment through a fixed GitHub API endpoint for Issue #184. Verify its identity, issue, timezone-aware timestamps and exact complete-plan SHA-256 marker; save the fetched evidence and timestamp. No caller-supplied authorization callback exists. Derive the shared claim directory from actual `git-common-dir`, keyed by fixed parent/version. A new worktree or plan output name cannot retry this study. Claim first, reserve all 23 native Trials, then allow numerical execution only after complete checks.
3. **Production then audit.** Sequential, separately supervised Python children reclaim the producer's memory before audit. Require observed successful producer exit, then bind RESULT/registry bytes. Audit uses SQLite `mode=ro` and `query_only`, without schema initialization or writes. Append AUDIT and ASSESSMENT; preserve the original RESULT's pending-audit state instead of editing history.

This is a single-user reproducibility workflow, not a new multi-user permission system. The global claim is shared within one Git common repository, not a guarantee against deliberate whole-repository copying, evidence deletion or code modification.

## Frozen resources and failure semantics

Each child is fixed to 10 GiB private commit, at least 4 GiB free physical RAM, at most four hours and 0.2-second sampling before any empirical read. Four hours is a stop boundary, not a performance prediction. The stages cannot overlap; their limits are not measured runtimes.

Prelaunch resource refusal creates no claim or Trials. Once claimed, the full 23-attempt commitment cannot vanish. Partial native reservation failures retain the committed budget and separately report actual native count; unavailable counts remain null with an error type, not a fabricated full reservation. Numerical access requires all native reservations.

Resource stops, process/audit failures and interrupts preserve claims, ledgers and terminal receipts without automatic retry. A subsequent attempt needs an explained, newly bounded preregistration, not deletion of the old claim. Polling is not an OS hard limit and controls only the owned child handle, not arbitrary descendant processes or certified whole-pipeline memory.

## Test scope and limitations

Synthetic parent ledgers and date-only usable Parquet test the entrypoint. The other three sources deliberately do not exist; anchor files deliberately cannot be decoded as JSON, demonstrating prepare's restricted hash/date behavior. Coverage includes changed evidence, missing controls, changed code, invalid budgets, resource refusal, preregistration identity/time/hash, complete 23 reservations, partial reservation failure, cross-worktree duplicate claims, read-only DB write rejection, tampered child evidence and an actual temporary Git worktree pair sharing a claim.

Lifecycle tests stub the numerical backend/audit to check ordering; **they are not new numerical recovery or statistical-power experiments**. The existing complete synthetic epoch audit now uses a genuinely read-only database connection and checks unchanged RESULT/registry bytes. B7's actual hidden Windows child measurement test remains in the suite. Exact final regression evidence is recorded in VERIFICATION.

## CI correction

B7's YAML change from 20 to 40 minutes did not fix cancellation: run34086974315 started at05:29:05Z and cancelled at05:44:17Z, around73% of tests. Official documentation confirms the **15-minute hard limit of ubuntu-slim**. The earlier attribution to a configurable 20-minute job timeout was inaccurate.

Both the GitHub connector and approved host-network CLI verified the repository is currently public. B8 switches to standard `ubuntu-24.04`, retaining all tests and a 40-minute job limit. This is not a paid larger runner; standard runners are free for public repositories. If repository visibility later changes to private, included minutes and billing must be checked again.[GitHub documentation](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

## Operation and next step

From the clean committed dedicated worktree:

```powershell
python scripts/run_flow_response.py prepare --output artifacts/flow-response/launch-plan-001.json
```

Publish the complete research contract and generated plan digest on Issue #184. Only after actual CI and preflight verification:

```powershell
python scripts/run_flow_response.py run --plan artifacts/flow-response/launch-plan-001.json --preregistration-comment ACTUAL_COMMENT_ID
```

Replace the placeholder with an actual numeric comment ID. Do not manually invoke internal backend/audit commands or remove a claim to resume.

The contract still contains only original 2022–2024 daily/flow, two primaries, nine controls per cost, 82/164 bps, CNY3m, fourteen actual annual models and twenty-eight cost-consumer bindings. The empirical lower bound changes from3660 to3683 only on a real committed attempt, not from temporary test databases. Even a complete exploratory survivor needs deeper falsification; it is not automatic Alpha Court, fresh OOS or live deployment approval.
