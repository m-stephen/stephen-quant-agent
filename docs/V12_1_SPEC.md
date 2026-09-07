# V12.1 — bounded power design / 有界功效设计

## Agreement / 审查共识

The owner authorizes continued upgrades with an independent review Agent agreeing
before each version. Core developer and reviewer `v12_review` agreed to this
scope on 2026-09-08 (APPROVE). This is synthetic capability work, not market Alpha.
V12.0's consumed audit and FAIL remain unchanged; historical raw attempts remain
at least 3,733. No real labels, 2025/2026 tuning, live trades, purchases, automatic
main merge or new data domains are part of this version.

用户授权每版先经核心开发与独立审查 Agent 达成一致。此次只做合成功效诊断，
不把工程通过、公式恢复、合成晋级、真实 Alpha 混为一谈。保留全部失败记录。

## Fixed experiment / 冻结实验

- Four scenarios: linear, interaction, correlated_null, regime_null.
- 24 fictional names, six fixed groups; train sessions 1..95, evaluation starts
  at 100 (zero-based); lengths 120/360/720. Horizons 5/10; 48 structures.
- Primary policy is the unchanged gross search; 3m CNY; native accounts with
  0/82/164 bps roundtrip cost; mean >=1bp/day, HAC(10) t>=2.5 and both halves
  positive at both positive costs. No weakening of these predicates.
- New generator uses independent RNG streams and fixed regime break at session
  110. Same seed/scenario/strength gives exactly identical complete short/long
  prefixes. Linear strength .004; interaction .012. New streams mean this is
  a new generator, not an identical rerun of the old V12.0 sample.
- Development: (four full-strength scenarios + two half-strength planted
  scenarios) x three lengths x eight fixed seeds = **144 paths**. Cross-length
  and cross-strength cases are paired, not independent evidence. Every cell
  denominator is 8. Half-strength is reported stress, never silently dropped.
- A length qualifies for a single new reserved audit only if both planted
  full-strength scenarios have >=7/8 primary AND reference promotions and both
  nulls have 0/8 promotions. Choose the shortest qualifying length; if none,
  no audit is opened. This is coarse development screening, NOT an 80% power CI.
- Reserved audit: fresh hidden master seed, one suite identity, full-strength
  only; 100/200/500 looks for each scenario; exact binomial bounds with total
  error .05 / (4 scenarios x 3 looks x 2 tails); power lower >=.80 and null
  path-FWER upper <=.05. All paths count, including reference failures.
  At most 2,000 paths / four hours; terminal failure is not an automatic retry.

## Measurement and training objective / 测量与训练目标

Independent Bartlett matrix calculation uses denominator n without small-sample
correction. Fixed zero-mean stationary AR(1) rho=0/.3/.8, lengths120/360/720,
2,000 independent replications per cell: report empirical SD, mean estimated SE,
95% interval coverage and t>=2.5 frequency. Compare with exact finite-n mean
variance. Numerical agreement is NOT a declaration of valid confidence coverage;
undercoverage is explicitly flagged, not repaired by tuning lag on audit results.
Cost-negative account nulls cannot alone establish the test's statistical size.

Development-only net reranking: gross top3; same native risk/signal and baseline
accounts on sessions1..95 only, at82/164 costs. Rank by minimum paired mean over
the two costs; deterministic identity tie-break. Each account is recorded before
label access. Evaluate its two-cost incremental outcome only as a diagnostic.
It cannot choose the audit policy. Future-tail poisoning must not change ranking.

## Evidence / 证据

New sources and full pipeline hashes, native ExperimentRegistry trials before
each label/account read, per-path complete daily account evidence, immutable
plan/result/terminal, failed reservations and bilingual reports. Numerical
reconciliation and reviewer re-review precede any claims. No real Alpha may be
declared from this experiment; historical Court remains NOT_IDENTIFIABLE/null.

## Next-version gate / 后续版本边界

No unbounded recalibration. If only power is inadequate, measurement and false
positive diagnostics must first be reviewed. A separately frozen tiny empirical
mechanism diagnostic may then be proposed using existing admitted data, with
explicit formulas, trial budget, train/diagnostic windows, revealed-history flag,
cost/capacity and stopping rules. It needs renewed developer/reviewer agreement;
it is NOT_CERTIFIED and cannot bypass independent Alpha Court/forward evidence.

中文摘要：不补数据、不放宽门槛、不以过关率挑政策；先分清计算是否正确、统计是否
有足够把握、信号是否可兑现。未检出也必须给出完整结果，不能换题直到通过。
