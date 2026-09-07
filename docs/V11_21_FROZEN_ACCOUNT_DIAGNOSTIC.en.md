# V11.21 B17: frozen-account root-cause diagnostic

## Decision and limits

B16 commit b041460 passed CI34114709041. This diagnostic reconstructs only the failed plan003 risk-82 account. No refitting, alternative targets or selection from partially completed accounts. Synthetic evidence proves a nonzero tiny-fill audit defect, not yet the unique cause of the actual failure.

Version11.21-risk-account-diagnostic-1 uses one exclusive claim derived from the shared Git common directory. Changing worktrees/output paths cannot replay it. One new native no-fit frozen-target account attempt inherits debt3660+23failed002+23failed003=3706; debt becomes3707 only when the new claim is consumed. Failures retain budget, actual native state and terminal evidence.

## Inputs and execution

- Only existing plan003 history/history.json,targets/risk.json and native lineage. Old artifacts and both failed23-attempt epochs remain immutable.
- Verify actual SHA/size of the37-file failure inventory, both failures' claim/terminal evidence, original parent, old auditor source and runtime code. Other account reports are hashed, never decoded for performance.
- Obtain original3e9fd0d auditor bytes from Git. An AST comparison permits only abs(notional)>1e-12 to become notional!=0. Execution engine, sessions and account configuration remain byte-identical to the old runtime.
- The complete plan binds clean commit, all src files,two drivers,Python/package versions,limits,input SHA,purpose and native replay contract. Verify the actual Issue184 comment through the fixed GitHub API; then claim and reserve before any numerical history read.
- History2022–2024; account2023–2024; CNY3m,82bps,target_changes,unchanged capacity/timing/suspension/limit/writeoff rules. No2025/2026,new sources,target generation or refit.
- One owned hidden child:private10GiB,freeRAM>=4GiB,4hours,poll0.2seconds;no automatic retry. Polling is not an OS hard resource boundary.

## Acceptance

1. Generate one account and exclusively persist UNVERIFIED_ACCOUNT before either audit.
2. Original audit must reproduce held-name set differs from fill reconstruction. Save the first exception-frame date,identity,quantities,notionals and opening price locally.
3. Every first-stop identity difference must be explained by same-day nonzero tiny fills skipped by the old audit. Corrected full-account order/cash/share/NAV reconciliation must pass. Save all tiny fills locally.
4. If unreproduced,unexplained or corrected audit fails,report UNRESOLVED. Never relax epsilon,automatically replay or begin a full research epoch.
5. engineering_pass is account diagnostic evidence only,not Alpha,source reconstruction/independent target selection or Alpha Court. The old audit stops at its first exception; later old audit states are not claimed compared.

## Operation and evidence

scripts/diagnose_flow_response_account.py exposes prepare,run and internal supervised child. prepare hashes bytes/metadata without consuming a Trial; run requires an actual preregistration comment ID. child is not authorization to bypass run. All artifacts use ignored artifacts/flow-response/account-diagnostics.

This document specifies execution,not an empirical verdict. Tests,actual commit/CI,full hashed preregistration and final diagnostic result are recorded separately. No claimed empirical execution before claim consumption.
