# V11.21 continuation / 续接记录

## Phase A checkpoint; NOT a completed market epoch

Branch codex/v11.21-flow-response is based on final V11.20 commit339014a7a1ed2a79ab99d9c615fbc2cd71f14ef3. PR198 finalCI34067387982 was checked SUCCESS and PR198 marked Ready; no merge. PR196/197 already Ready. Do not rerun any V11.20/V11.19 operation, audit or report.

Read V11_21_PLAN.md, V11_21_STATIC_REVIEW.zh.md/.en.md and V11_21_VERIFICATION.md. Source-only inventory command already produced artifacts/flow-response/static-inventory-001.json:15files/337units/hash78908c062133d6d3e5f53e23fc30976d2913781a8b807d66ace2869f4507f6c4. Do not overwrite it. This is not a full runtime candidate expansion. New stdlib-only module is src/stephen_quant/mechanism_inventory.py, NOT inside discovery (whose package initialization imports generators).

The new additive family/expression/policy keys omit narrative and carry legacy IDs/debt. Synthetic test reproduces the old narrative-ID issue, but old mechanism_lineage and freeze_proposal_packet are UNMODIFIED; production dedup integration is still pending. Do not rewrite old identifiers, lost-trial debt or tombstones.

flow_response.py contains only an in-memory within-stock response prototype.60contiguous global sessions strictly before cutoff, population zscores,beta=corr/1.01,raw standardized flow and standardized return residual. Model binds asset/snapshot/observation hash/window/prediction session. Strict adjacent-session application, no stale-fit fallback, unavailable/future numeric values excluded before inspection, invalid values may roll off after60clean sessions. Synthetic reverse-pairing counterexample proves distinction from old aggregation,not Alpha or causality.50targeted tests pass; see VERIFICATION for final full suite. No market read, fit ledger, preregistration or new empirical Trial exists; debt remains3660 and package11.20.0.

## Resume useful work

Finish native label-free rolling-fit evidence and source bridge before supervised fitting. Existing integrity/fit_lineage.py supports UnsupervisedFitStage, but the prototype is NOT connected. Keep per-stock/day model evidence and consuming Trial relationships honest; do not invent label dates. Consider deterministic per-signal-day model bundles so a shared fit is persisted once rather than repeated for costs/controls. Annual supervised fitting must consume only historically available response features with mature future labels and purge/embargo. Calendar support, missingness and original source-adjusted prices must remain aligned.

Complete the finite family/common-support controls and native budgets exactly, then synthetic planted/null and adversarial runtime tests. Only after runtime is committed and Issue184 fully preregistered may one exclusive real2022–24operation run. Current prototype alone is not authorization to start an epoch. Use only original frozenV11.4 inputs snapshotb813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51; no freshwarehouseor2025/26reads. Preserve originalV11.11card/targets from originaltree,notCRLFcopies.

Keep300万,82/164bps,capacity/limit/suspension/writeoff semantics,rawflow/risk/fixedshuffle and oldstable/lowvol controls. Reused2023/24isnotfreshOOS. Carry3660historicalTrials; costs/controls/failedrun attempts count. Exploration gates bothyearspositive,SR>=.7,MDD>=−25%,>=3pp total and>=−5pp annual increment versus every required control,predeclaredcoverage and complete audit. CourtDSR>=.95,PBO<=.05,placebo<=.05 and all existing independent-evidence/path requirements stay unchanged. No promiseAlphaexists; don't certify with unsupported stats.

Do not modify root codex/v4-8-sealed-alpha-court's23unrelateddirtyfiles. No subagents,newtask,newautomation,mainmerge,tradingorpurchase. Existing v10-alpha30-minute heartbeat continues quietly; preserve actual PR/CI/checkpoint state in its prompt. Strip AlphaPai credentials from research/test child environment without printing values. Only usableAlpha,seriousfailure or requireduseraction warrants notification. Check Git/PR/process/output before resuming; never duplicate reservations or overwrite completed evidence.
