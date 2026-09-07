# V11.20 next bounded stage — Frozen-policy gross-to-net attribution

## 中文：为什么先做这一步

V11.19.1的两个完整排序身份在两年、两成本均亏损，且不如同基风险排序/收益差回归。独立源、配对、拟合、目标及账户核对通过。因此本轮没有需要被包装为成功的候选；不能直接归咎于数据不足，也不能声称优化器修正带来Alpha。

82bps下，线性完整排序累计成交约1.236亿元、成本50.55万元；固定hash约4312万元、成本17.55万元。成本、成员路径和风险暴露同时变化，单凭这些总数无法因果归因。不能把手续费加回期末NAV就当成零成本策略，也不能继续扩大相同六输入的多项式阶数来赌结果。

下一步先对**全部12份冻结目标**作一次有界的真实零成本路径反事实，与已完成82/164bps账户逐项对账，区分毛收益缺陷与执行摩擦。这不是降低正式成本门槛，不生成可用Alpha结论。该阶段完成后再登记新的机制或训练目标，不在未得到诊断前编造成功方向。

## Proposed implementation contract / 待实现契约

1. New independent `codex/` branch from the completed V11.19 report commit; no automatic main merge. Preserve both V11.19 operations, native registries, original V11.11 card/target bytes and all previous evidence. Use the same five-file frozen snapshot and2023–2024 reused development period.2025/2026 remain unread.
2. Exactly12 additional diagnostic accounts:2 bases×4 learned policies plus4 fixed controls, all at0 commission/tax/slippage. The24 existing82/164bps accounts are read-only comparison evidence,not rerun. Register12 new native replay/no-fit Trials before any new numerical access,raising3648→3660 even on failure. Explicitly bind original16 models/32 fits as inherited lineage; do not claim these frozen-target replays are newly fitted models or fabricate new fit receipts.
3. Preserve every target byte, decision timestamp, member/weight, prior ADV constraint, rebalance mode, stale-mark/writeoff rule, initialCNY3m and continuous capital clock. Only all three cost components become0 together. Fees affect cash and later fills, so regenerate complete accounts using the existing stateful engine; no synthetic subtraction from old totals. Zero-cost accounts remain economically counterfactual.
4. Bind original target hashes and current runtime/source hashes. Use an exclusive operation and parent claim, record all failures, and refuse overlapping output/source or existing operations. Existing original lowvol/stable zero-cost results in V11.13 may be used only as read-only exact replay checks with matching target bytes/mode,never as unregistered new alternatives.
5. Independently reconcile source-open shares,cash,NAV,all-zero fees,capacity,annual compounding and24 inherited versus12 new record identities. Add planted synthetic tests showing why adding costs back to final NAV is not a valid zero-fee replay, plus target/lineage/claim tampering and no2025/2026 access tests. Complete pytest/Ruff, independent audit, bilingual reports and all36 aggregate records before publishing conclusions.
6. Report every policy's0/82/164bps return,annual returns,drawdown,turnover,cash and source limits; full-minus-risk/regression/hash increments at each cost and their gross-to-net differences. These descriptive differences include cash scaling,compounding and changed fills; they are not a clean causal treatment estimate of fees or a calibrated Alpha statistic. Do not select a new policy by the largest zero-cost curve.
7. The original two primary identities remain **failed** under their unchanged registered82/164bps screen. No new exploratory survivor or CourtPASS can be created by this diagnostic. DSR/PBO/placebo remain NOT_RUN unless separately registered complete identifiable evidence is implemented. Preserve all historical selection debt.

## Follow-on decision, not outcome-based threshold tuning

- If the complete ranking models lack gross incremental strength against risk/regression controls across years, stop repackaging those six primitives as increasingly complex models. Propose a genuinely different information mechanism after static catalog de-duplication and register it as a new finite family.
- If gross incremental strength exists but net performance loses it, prioritize train-prefix-only turnover-aware decision learning with an explicit fixed execution budget and matched controls. Do not lower82/164bps,change old targets or call raw fees an achievable savings estimate.
- If incremental direction is unstable across years, preserve that failure. Any regime-conditioned model needs past-only state fitting and a newly preregistered family; no retrospective relabeling of2023/2024 or selective year exclusion.
- Any eventual full survivor is frozen first and receives finite delay/capacity/state/placebo challenges,then identifiable full-historyDSR/PBO and independent evidence. Historical developer reuse cannot become a fresh test by renaming it. No guarantee that a usable Alpha exists; no purchases or trading.

## Status / 当前状态

Planning only: no V11.20 runtime,market run or new12 reservations yet. Economic diagnostic scope is fixed here; a complete runtime-specific preregistration is still required before execution. Ordinary negative results remain archived quietly under Issue184; the existing heartbeat continues development rather than waiting for unrelated data purchases.
