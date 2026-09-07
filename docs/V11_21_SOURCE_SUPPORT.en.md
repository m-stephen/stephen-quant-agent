# V11.21: Same-date source-support correction

## Technical summary

This corrects a pre-model source-join failure. It produces no new market-return result and does not establish Alpha. The strict join remains the default. Only the newly frozen `same-date-daily-supported-v1` policy excludes flow keys lacking a same-date daily record, with independently auditable identity and coverage evidence.

## Scope and definitions

Only the original frozen 2022–2024 daily and fund-flow sources are in scope. The completed key-only diagnostic found 3,731,699 daily keys, 3,588,620 flow keys and 3,588,418 common keys; 202 flow-only keys and 143,281 daily-only keys. A key is a trade-date/instrument pair, not an instrument count.

The 202 flow-only keys represent approximately 0.005629% of flow keys. This explains the strict foreign-key abort, not the vendor's underlying cause. It is neither an eight-feature/risk-eligibility coverage pass nor return evidence.

## No imputation, compressed dates or retrospective selection

The bridge validates unique calendar keys first, then records same-date unsupported identities. Flow-only records create no observation; the bridge does not access their numerical or availability values and fabricates no price or return. The source reader still projects and casts frozen columns over the authorized interval: this is not a claim that the underlying reader never loads orphan-column values. Daily-only records retain the original missing-flow rule. Missing global sessions invalidate adjacent returns and consecutive sixty-session fit windows; missing dates are never compressed away.

Evidence includes daily and total bidirectional counts, common-key coverage, SHA-256 of both unmatched identity sets and the exact flow-exclusion list. Hash encoding is sorted date/instrument compact ASCII JSON pairs with LF line endings. Future instrument presence never determines eligibility. The old default still rejects orphan flow keys.

The independent auditor reconstructs keys, counts, identity hashes and exclusions from the original two sources; it does not trust producer totals alone. Duplicate/calendar/availability/source-hash/model-lineage/cost/capacity gates remain active.

## Failed attempts remain in the new protocol

Consumed plan002 stays terminal and cannot be replayed or have its claim removed. The launcher verifies actual failed plan, global claim, terminal, preregistration, native SQLite, first-read reservations and supervisor evidence read-only. It cross-checks all 23 identities, configuration, code/source bindings and zero completed results/fits.

The fixed parent remains 3,660 attempts. Adding the consumed failed 23 produces 3,683 prior attempts. A new full 23-attempt claim under `11.21-response-epoch-2` produces 3,706. Failed-evidence hashes enter the new specification, composite snapshot and native parameters. The independent audit derives the required total from the frozen protocol instead of a stale literal.

## Validation and unresolved questions

Final local full regression: **1,435 passed, 2 skipped, zero failures or errors, 566.73 seconds**, including the complete synthetic source→model→account→independent-audit pipeline. Ruff passed for CI's src/tests scope and the changed scripts. New-commit CI and the corrected empirical experiment remain pending; local regression cannot substitute for either.

Synthetic/adversarial tests cover strict defaults, explicit exclusions, unreadable orphan values, global gaps, order-invariant identity hashes, independent reconstruction, tampered exclusion identities, omitted failed debt and replay refusal. Temporary synthetic registries are not empirical Trials or investment evidence. Exact full-suite, CI and artifact hashes belong to the latest engineering verification record.

The first full regression found a stale debt literal in the independent auditor; it was replaced with the frozen-protocol total and a regression rejecting omitted failed debt. That failed test run remains evidence, not a pass. The vendor discrepancy, actual eight-feature coverage, complete resources, net increments and stability still require a new bounded empirical run.

## Next steps and limits

After full local regression and actual new-commit CI pass, create exclusive plan003, publish its complete hash-bound preregistration, verify it with the fixed GitHub API, then launch exactly once. Preserve old plans, sources and outcomes. Keep two primaries, nine controls per cost, 22 accounts and one shared provider; CNY3m, 82/164bps and all original eligibility/portfolio rules.

Freeze a complete exploratory survivor before deeper falsification. Otherwise use all negative evidence to justify a new finite proposal. Reused history is not independent out-of-sample evidence; 2025/2026 stay unread. DSR≥0.95, PBO≤0.05, placebo≤0.05, path and independent-evidence requirements remain. Continued searching cannot guarantee usable Alpha. PR #199 stays Draft; no main merge, trades or purchases.
