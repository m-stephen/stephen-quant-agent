# Issue184 automatic research continuation

## Resume, do not restart

Work from the `codex/v11.8-lead-challenge` worktree, preserving the original dirty
checkout and both V11.7 frozen leads. PR183 remains a dependency until separately
approved/merged. Read Issue184 and its progress comments, then inspect running
Python processes and local operation receipts. Never start a duplicate live job.

The following paths are repository-relative and ignored:

- `artifacts/lead-challenge/epoch-001/RESULT.json`: completed66-account challenge.
- `artifacts/lead-successor/epoch-001/RESULT.json`: completed16-candidate conditional60 epoch;
  zero economic leads. Independent192-account and SQL verification passed.
- `artifacts/lead-successor/claims/`: exclusive predecessor claims; failures retain
  claims and reservations. Do not delete them to restart a research attempt.
- `configs/lead-challenge.local.json`: private parent/input references.

Initial trial lower bounds:3058 before the challenge;3088 after30 new challenge
policies;3184 after96 successor reservations, even if the successor aborts. The
old unused96 V11.7 reservations remain charged. Exact replay adds zero trials.
Every subsequent epoch must carry the complete prior operation chain, including
aborted reservations. Do not derive debt only from the last successful epoch.

Both operations are now complete. Do not rerun them: source result hashes and
the751-pass local test receipt are in `docs/V11_8_VERIFICATION.json`. Current
research debt is3184. Draft PR185 is stacked on PR183; check CI/review status
before calling engineering ready. The automatic follow-up runs every30 minutes.
Next research should explain why all conditional60 combinations lag low-vol;
prioritize timing and continuous-holding mechanisms, not another horizon-only
repeat. Preserve the old chip lead even though its132bps stress is fragile.

## Decision tree

1. Repair any engineering/accounting mismatch before additional label exposure.
2. Review the COMPLETE conditional60 family, not its first attractive candidate.
   Preserve all failures and run independent accounting/SQL checks.
3. If an economic lead appears, freeze it; test real continuous capital, raw-price
   shares, trading lots/minimum commission, corporate-action accounting and actual
   opening-liquidity constraints. Study market/industry/size exposure using only
   time-appropriate available evidence. Do not mislabel low-vol-only regression as
   full style adjustment. Extra scenarios are diagnostic, not license to pick the
   most favorable fills or reset capital every year.
4. If it fails, explain whether the failure is signal strength, turnover, timing,
   exposure, or execution. Preregister a small new mechanism epoch with explicit
   inputs, economic rationale, signs, horizons, comparisons and finite budget.
   Prefer genuinely distinct timing/mechanisms and cached reproducible evidence;
   do not endlessly tweak weights on the same revealed outcome.
5. Restore/verify the statistical contract using synthetic planted-edge/null
   controls and the full historical search debt. Sensitivity-only DSR is not a
   calibrated certificate. Keep DSR>=0.95, PBO<=0.05, each placebo<=0.05 and the
   existing path/market-state/capacity gates. Use holding-horizon-aware purge,
   embargo, CPCV and walk-forward. Never lower gates to obtain a pass.
6. A historical lead is not usable Alpha. Freeze before independent validation or
   genuinely new forward shadow evidence. Prior research exposure cannot become
   a pristine holdout simply because the formula/version changed. Respect existing
   sealed2025/2026 protocols; never optimize on final-test results.
7. Continue bounded development/research while authorized work is possible. If
   independent data, a legitimate access boundary or a missing user choice truly
   prevents progress, report that constraint rather than claiming success or
   running the same tests forever. No paid data purchases or trading orders.

## Delivery

Store aggregate bilingual reports, immutable operation receipts and failure
tombstones. Test engineering changes with pytest/Ruff, create reviewable codex/
PRs, and do not merge main without applicable authorization. Keep data, credentials,
machine paths and detailed per-stock accounts out of Git. Normal failed epochs
are research records, not discoveries. Only evidence meeting the complete frozen
contract may be described as usable Alpha.

## 中文摘要

从最新结果和正在运行的进程恢复，不重启重复任务。两条旧线索保持冻结，新增假设、
成本和执行变体都记账。全批次测试后，优先对有经济性的候选验证连续账户与真实成交；
失败则解释机制并开启下一有限批次。完整统计门槛、封存窗口和独立验证要求不变。
工程完工、历史盈利、经济线索、可用Alpha是不同状态。需要新权限或真正新证据时如实报告。
