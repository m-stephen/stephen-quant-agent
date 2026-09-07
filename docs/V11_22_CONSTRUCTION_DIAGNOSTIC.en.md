# V11.22: Portfolio-construction diagnostic

Question: on the identical eligible cross-section, is stratified versus global construction an important contributor to membership churn and net-return loss? These are diagnostic controls, not new primary Alpha candidates or weaker gates for a failed signal.

## Frozen design

| Item | Only permitted definition |
| --- | --- |
| New accounts | global_lowvol / global_hash, each at 82 and 164 bps: four accounts |
| Selection | Global top40; retain previous names within top60; vacancies stay cash |
| Hash | Original `v11.21:184:<name>` identity, no new seed |
| Support | Original daily/fund-flow snapshots and audited history; same-date eight-finite-feature support |
| Timing | Previous-session signals; 20 global sessions; phases 0/5/10/15 |
| Capital | One continuous CNY3m account, no annual reset, four netted desired-weight sleeves |
| Execution | Unchanged target_changes, capacity, suspension/limits, writeoff/recovery and costs |
| Window | Original 2023–2024 development window; no 2025/2026 or new source |
| Comparators | Completed lowvol/hash at both costs, read-only and never re-executed |
| New fitting | Zero; no refitting the 14 original models or historical provider |
| Trial debt | Actual lower bound3729 before launch;3733 after all four attempts are committed, including failures |

Forty names per sleeve does not mean forty actual netted holdings. Membership replacement is not traded-notional turnover. Global construction jointly changes risk allocation and retention, so differences are not a single-variable causal effect.

## Implemented chain

1. Preserve B22's original commit/runtime bytes, native results, shared terminal and independent assessment. Do not regenerate its old plan at new HEAD. Original file bytes and tracked Git history must remain unchanged; new modules cannot overwrite the archive.
2. Prepare binds completed evidence, actual hashes and date-only coverage. Before new numerical work, verify the exact V11.22 Issue184 preregistration, exclusively consume a shared claim, and natively reserve all four accounts.
3. The producer loads one verified immutable history and saves complete targets, accounts, fees, fills, cash and holdings. Each refresh records new membership, selected mean volatility and counts across the original20 cells.
4. The independent stage checks sources through historical features, separately reconstructs global ranking/retention/four-sleeve targets, and reconciles saved fills, fees, shares and NAV. It never uses production selection, aggregation or execution as its independent numerical reference.
5. Sequential, separately supervised producer/auditor processes: four hours per stage,10GiB private commit and at least4GiB free physical RAM. Retain exits, refusals and failures; no automatic retry or alternate-output replay.

These are single-user research-integrity controls, not a multi-user permission system or OS security sandbox. Raw sources, numerical artifacts and local paths remain gitignored.

## Testing and launch conditions

Small synthetic tests cover top60 boundaries, phases/annual continuity, future-value isolation, empty-support cash, complete native reservations, changed code/snapshots/accounts, failed-attempt debt and replay refusal. End-to-end tests use existing synthetic sources and actually execute all four accounts and independent source/target/account verification. OS monitoring is simulated in the orchestration test; the real supervisor is tested separately.

The first end-to-end run exposed a test assertion using `pass` instead of `source_history_audit_pass`. Account execution and numerical audit completed; the corrected assertion must be rerun, not retroactively marked green.

Real execution requires all three full CI groups for the final commit, a clean worktree and complete actual plan/hash preregistration. This design, progress comments and synthetic results are not an empirical preregistration. Entry point: `scripts/run_portfolio_construction.py`, with no cost/year/seed/universe overrides.

## Interpretation and next step

Report all four new accounts and four fixed completed controls: both years and full-period net returns, Sharpe, drawdown, fees, trading, cash, style and membership changes. No fee-addback counterfactual or best-year/cost cherry-picking.

Statistics remain `NOT_RUN_DIAGNOSTIC`, DSR/PBO/placebo null and `validated_alpha=false`. A complete audit means `COMPLETE_DIAGNOSTIC_AUDITED`, never Alpha Court PASS.

If construction materially matters, separately preregister a finite experiment separating style allocation, within-style signals and holding maintenance before testing signal increment. Otherwise retain the negative evidence and move to another mechanism. Every new strategy/direction/cost variant remains counted. Usable Alpha still requires independent evidence, historical multiplicity and unchanged DSR/PBO/placebo/path/capacity gates; reused development years are not first-seen out-of-sample evidence.

Parent results: [V11.21 frozen results](V11_21_FROZEN_RESULT.en.md). Until the real four-account diagnostic executes, this version adds no market Alpha conclusion.
