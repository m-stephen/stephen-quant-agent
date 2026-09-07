# V11.21 B16: account audit correction and a frozen diagnostic

## Conclusion: no complete Alpha result

Consumed plan003 failed at 2026-09-07 10:20:12 UTC after 4186.89 seconds. All23 native attempts remain counted; cumulative debt3706. Native evidence retains664 provider bindings,28 supervised consumer bindings,14 actual annual models and4 completed accounts. Five completed native results include the provider. No complete RESULT or independent audit exists; partial accounts cannot select a winner.

A read-only SHA-256 inventory preserves the registry,claim,terminal,logs,history,14 models,5 target files and4 account reports. No old operation is deleted or replayed.

## Proven defect and minimal correction

The auditor updated shares only when abs(notional)>1e-12, whereas execution applies every nonzero fill. Currency and share thresholds are dimensionally different.

Synthetic witness: buy CNY75,000 at0.15, liquidate at0.07, leaving5.820766091346741e-11 shares through floating-point arithmetic. A subsequent liquidation at0.01 has notional-5.820766091346741e-13. Execution removes it; the old auditor ignores the fill. The same defect can falsely accept an omitted tiny position mark.

The correction uses notional!=0 for share reconstruction. It does not change the engine, share threshold,costs,targets,universe or research gates. Trading restrictions and exact held-name checks remain. Audit exceptions now preserve an exclusively created unverified account report and ACCOUNT_AUDIT_FAILURE receipt with completed_result=false; no completed native result is recorded.

New synthetic regressions before correction:9 failed/3 passed. After correction with existing replay checks:38 passed; subsets overlap and are not additive. Ruff src/tests passed. Full regression:1448 passed/2 skipped in542.25 seconds; session59960 exited0. New-commit CI remains pending; old CI is not evidence for this change.

Limitation: the actual failing account was not persisted. Fixed loop order and the ABORTED completed list imply risk-82, but its exact first discrepancy is unconfirmed. Synthetic reproduction does not uniquely prove the actual failure's cause.

## Next: preregister one account diagnostic, without retraining

1. Complete full regression,commit and actual CI. Never run consumed plan003 or use the old prepare path without inheriting the latest debt.
2. Implement/test one exclusive diagnostic using only plan003 history/history.json,targets/risk.json,native lineage and the original3e9fd0d auditor bytes. Verify actual hashes; do not modify old artifacts.
3. Budget one new account attempt,3706→3707. Publish exact runtime/input hashes,purpose,resource limits,time scope,claim and ledger in Issue184 before execution; verify the actual comment through the fixed GitHub API. No new diagnostic budget is consumed yet.
4. Reconstruct frozen risk-82 once: CNY3m,82bps,target_changes and original capacity contract. No model refit,alternative targets,parameter selection,2025/2026,new sources or outcome-based selection from other candidates.
5. Apply old and corrected auditors to the same account. Preserve the first divergent date,exact quantities/notionals and controlled local identity evidence plus the unverified complete account. The account-generation process is unchanged.
6. Require the original failure to reproduce,each difference to be explained,and all corrected order/share/cash/NAV/source checks to pass. If unreproduced or another discrepancy appears,record unresolved; do not relax numerical precision or resume the full epoch.
7. One owned child:private10GiB,freeRAM>=4GiB,wall4h,poll0.2s; preserve debt on failure, no automatic retry. Only then preregister a finite full-account continuation,preferably reusing immutable models rather than retraining without cause.
8. Diagnostic PASS is engineering evidence,not Alpha. Usability still requires every frozen double-cost/control and Alpha Court requirement.

Inspectable gitignored companions: artifacts/flow-response/checkpoints/b16-failed-account-inventory.json,b16-tiny-fill-diagnostic.ipynb,b16-targeted-final.xml. All3 notebook code cells ran sequentially in one fresh plain-Python process; Jupyter,nbformat and nbclient are unavailable,so no Jupyter-kernel verification is claimed.
