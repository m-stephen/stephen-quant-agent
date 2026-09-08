# V12.3 — Frozen account forensics / 冻结账户法证

Issue #206. Both Agents approved this finite scope before implementation.

## Question / 研究问题

V12.2 response-risk full-period net differences were negative at both costs.
Do the frozen source, missing-bar valuation, recovery and turnover records explain
that result, or demonstrate a specific implementation mismatch? This is a forensic
question, not authorization to change prices, fees, losses, models or account policy.

V12.2未发现可晋级Alpha。本版只解释已有证据，不继续调整topN/buffer/方向/期限，
不把成本或核销加回净值，不将回测诊断变成认证通过。

## Fixed contract / 固定契约

- Parent plan ace020b075d872f3a6a78d91934b788adc6192109574b32e031bdcdd4e710b98.
- Original producer75602e12e2cc1b81b814146af1e8b9e67072afdd remains untouched.
- Parent RESULT67e4558edada509d15b2e957fbd8229e01a77699c9fb35cd6390d448f193cc08;
  AUDITe4d141c35e1f444ff9e45380204a8ffe583dca2eea8229ed700f50ababf194c5.
- Four completed global_response/global_risk accounts,82/164bps, plus all eight
  saved predeclared parent comparison accounts. No posthoc comparator selection.
- Only frozen2022–2024 daily/fund_flow, history and saved ledger/target/diagnostic
  files bound by that plan. No2025/2026 and no new provider or downloaded data.
- New accounts0, fits0, prediction recomputations0. Preserve real Trial debt3737.
- Exclusive new report output; bind input hashes before/after. Never rewrite old
  raw bytes, evidence, claims, terminals or final outcomes.

## Required evidence / 必须完成的证据

1. All writeoff/recovery identities keyed by(account,date,instrument,event_type),
   retaining per-account daily and full totals. A name shared across accounts is
   not a duplicate event. First writeoff and subsequent zero-mark days differ.
2. Source-row existence/price/time, saved history inclusion, stale chain and
   recovery valuation/order/cash evidence. Classifications: source absent,
   filtered out, format/time refused, implementation mismatch or unknown.
   Missing vendor bars are not proof of actual suspension or delisting.
3. Later recovery is retrospective evidence, never prediction-time information.
   Recovery valuation is not necessarily cash received. If the producer lacks
   per-name recovery open price, leave the amount unknown until frozen-source
   reconciliation; never allocate a daily total arbitrarily across names.
4. Exactly97 stored maintenance decisions per policy. Same-phase membership and
   support persistence; raw-score/rank analysis only if already saved. Missing
   raw scores mean unavailable, not permission to predict again.
5. All12 fixed account comparisons by year and continuous window, both costs:
   returns,Sharpe,drawdown,CNY P&L,primary paired differences,fees,traded value,
   turnover,cash/positions and20-cell exposure. Declare existing map timestamp;
   unknown names/weights remain in the denominator. Name churn is not turnover.
6. Synthetic tampering/incomplete evidence tests and independent Agent review.
   Completed cash accounting and event extraction do not prove source truth.

每个账户完整逐事件对齐，不跨账户去重漏证据。来源缺失、真实停牌/退市及实现错误
必须区分；不能确认则unknown。实际暴露保留未知权重，不删除分母。

## Acceptance / 验收

Deterministic bilingual forensic report, complete fixed coverage or explicit
unavailability, synthetic tests and independent review. DSR/PBO/placebo remain
unidentifiable when historical evidence is insufficient. No usable-Alpha claim.
If a concrete defect is demonstrated, propose a separate finite repair/retest;
otherwise stop grinding this response family and discuss a genuinely different
target/mechanism. No automatic market rerun, statistical relaxation or main merge.

## Current engineering stage / 当前工程阶段

Pure saved-ledger event extraction and unknown-preserving exposure helpers only.
Source tracing, frozen evidence wrapper, complete report and final validation are
not implemented yet. No real forensic operation has been launched by these helpers.
