# V11.19 continuation

## Current correction state

Original runtime2d57e2d / preregistration5562552983 / PR197: epoch-001 is ABORTED,24Trials charged,0accounts,9model artifacts. Do not run its old config again. OPTIMIZER_DIAGNOSTIC.json proves final Armijo cancellation; its SHA891b2db319065f1b6865b0b539f0d29a20dd497d98248d289a8792f710dd08f5. See numerical amendment in DESIGN. V11.19.1 is the same economic plan with only terminal floating-roundoff acceptance, unchanged gradient1e−9.

Next: full regression, freeze corrective code and publish separate Issue184 correction preregistration. Then create configs/v11.19.1-run.local.json with aborted_dir=artifacts/pairwise-ranking/epoch-001 and output_dir=artifacts/pairwise-ranking/epoch-002; keep original parent/input/card references. New24reservations increase3624→3648. Run corrected epoch-002 once, never epoch-001. All old operation files enter the protected manifest. After completion run the independent auditor on epoch-002, then build_pairwise_report.py. Reports must disclose the first failed24trials. Instructions below describe historical premaket status only and do not authorize replaying epoch-001.

Status at runtime commit: PREMARKET. Read V11_19_DESIGN and VERIFICATION. Branch codex/v11.19-pairwise-ranking descends from V11.18 final ab642020298448932f85ace79e6be06e11c17a4e; PR196 is Ready with successful CI34061508620. No main merge.

First publish this runtime and exact Issue184 preregistration. Then local ignored run.local.json identifies original V11.4 frozen inputs, original V11.11 tree, completed V11.18 epoch-001 parent and new artifacts/pairwise-ranking/epoch-001. Do not invent a comment ID, run twice or bypass claims. All24 Trials must be reserved before numerical reads. Parent debt3600 becomes3624 even on an aborted experiment.

Run scripts/run_pairwise_ranking.py --config configs/v11.19-run.local.json once; then scripts/audit_pairwise_ranking.py --output artifacts/pairwise-ranking/epoch-001 --inputs <configured frozen inputs>. Preserve RESULT/ABORTED, protected12files, registry, feature/rank/pair/model/target/account evidence. Do not alter runtime during either process.

After independent audit: produce all24 aggregate records, separate bilingual reports, reviewed report artifact and notebook. Report DSR/PBO/placebo as NOT_RUN, notPASS. If no complete exploratory survivor, archive the negative evidence and develop the next genuinely different bounded mechanism under the same Issue. If one survives, freeze exactly and preregister deeper falsification; reused2023/2024 are not independentOOS. Keep2025/2026 unread. Update the existing v10-alpha heartbeat recovery prompt only, retaining its30-minute schedule and quiet ordinary outcomes.

Root worktree has23 unrelated old edits; do not stage/reset/edit them. Do not start subagents, create duplicate automations, merge main, trade or purchase. Clear AlphaPai secrets from test/research child environments without printing values.
