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

Implemented pure saved-ledger event extraction, unknown-preserving exposure,
completed-input byte bindings and saved sleeve membership reconstruction. The
wrapper verifies the untouched original V12.2 producer rather than rebinding its
consumed plan to this new code. It retains all12 prespecified accounts and exposes
an after-report input hash check; it never launches an account, fits or predicts.

Membership is recovered from successive saved aggregate desired-weight seat
counts and the prior same-phase membership, then checked against the stored
selected-name hash and entered-name count. This recovers names, not missing raw
scores or top60 ranks. Support identities still require frozen-history evidence.

The pure source/bar comparison helper distinguishes verified source absence,
format/time refusal, saved adjusted-price mismatch and incomplete evidence. It
does not interpret no-volume/no-name rows as absent execution bars: those affect
tradability, not bar inclusion in the frozen producer.

Saved-account chain reconciliation now follows every explicit session from empty
initial positions, checking stale counters, zero-mark retained shares, recovery
open valuation, executed share deltas, fees, cash and NAV identities. It never
regenerates expected orders or rechecks a modified capacity policy. Source event
explanations and still-open stale tails remain separate from ledger correctness.
The bounded Parquet reader projects only requested daily keys after byte checks;
logical row exclusion does not claim physical Parquet row-group isolation.

Descriptive metrics use actual carried NAV for each year, sample-SD Sharpe252,
window drawdown including opening NAV, and explicitly named one-way turnover
`0.5 * abs(executed notional) / previous close NAV`. Primary comparisons remain
response minus risk, with yearly CNY differences based on their separate carried
capital. DSR/PBO/placebo remain null; these summaries are not certification.

Fixed saved-report orchestration now runs the independent components directly,
with one decoded history and complete compact-ledger checks. The external final
acceptance, production once-only supervisor and bilingual renderer are pending.
All new numerical integration evidence is synthetic, not a market-data run.
No real forensic operation has been launched by these components. Exact internal
trading-date alignment still requires the frozen calendar, beyond helper shape
and endpoint checks.

Independent reference components now derive event/tail identities from original
account marks and saved bars, invert aggregate membership by subtracting the
other three sleeves, and attribute support changes using raw prior-session rank
identities. The independently derived event/tail set determines the required
source query keys; actual returned rows must carry all nine projected fields.
Source value/time/recovery explanations are checked without calling the producer
source helper. Unexpected volume/display-name types remain unknown, not proof
that the original panel could construct a matching execution bar. Legal zero or
missing volume/name may affect tradability without removing that bar.

A streaming canonical fingerprint component can detect accidental in-memory
changes to shared decoded original evidence without a second serialized history.
The fixed integrated runtime calls these reference paths itself, binds
all original input/output/code bytes, preserves partial failures and completes all
12 account receipts. These components alone cannot accept caller-made reference
objects as proof, and cannot substitute for external final runtime acceptance.

独立参考路径已补齐事件、成员、股票池及来源解释组件；同人数股票池的身份变化也会核验。
来源查询必须覆盖独立重建的全部事件和尾链，不得由生产端遗漏事件后同步缩小查询。
成交量或名称类型异常保留unknown；零成交或缺名称不等于缺少执行bar。
原始内存对象流式指纹组件用于发现意外原地修改，不新增多用户权限体系。
固定核验入口已完成集成；生产环境一次性监督、外部最终验收和双语报告仍待补齐。
合成通过不等于真实Alpha通过。

已实现证据封装、成员反演、逐日账本链、来源按键查询及解释、期末未恢复尾段和指标组件。
没有重算预测；未保存的分数与top60排名明确不可用。恢复估值不重复加入现金；核账通过
不等于来源真值或Alpha通过。真实数据的完整法证运行与最终双语报告尚未完成。

## Independent integration checkpoint / 独立集成检查点

The new bounded synthetic suite completed17 tests successfully. Its unchanged
726-session/200-name source fixture contains145176 nine-field rows, with the
same standard/double-cost native saved accounts. The previously placeholder
compact bindings were replaced by real484-period JSONL ledgers. All12 accounts,
two membership policies, two primary cost comparisons and all51 output hashes
were verified. Omitted events/queries, altered member output, in-place history or
report changes and a mid-verifier exception all fail without a success summary.

Ordinary JSON fingerprints remain strict for decoded JSON history/reports.
Actual Parquet lookup scalars use separate typed, row-streamed fingerprints so
timezone-aware datetime and diagnostic NaN/inf are not silently converted to
strings or repaired; source-type/availability judgments remain independent.

The component outcome is
`SAVED_REPORT_INDEPENDENTLY_VERIFIED_NOT_LAUNCH_ACCEPTED`.
This does not resolve the prior intermittent native CI crashes, approve a real
forensic launch, certify Alpha, or authorize a merge to main.

新增17项有界合成集成测试全部通过。原726日、200只合成股票、145176行九字段来源、
标准及双倍成本保持不变；12个账户的484日完整账本、成员/来源/指标与51份输出哈希
均纳入核验。事件或查询漏项、成员篡改、原始内存改写及中途核验失败不会生成成功摘要。
这不是市场回测，也不表示此前CI原生崩溃根因已修复；真实运行和main合并未获批准。

## Bounded native diagnostic / 有限运行时排查

CI34176935282 crashed in both Python3.10.21/3.12.14 trace120 groups; the
trace0 control completed1904 tests. The causal defect is NOT established.
New slot `v123-native-runtime-001` is separate from the consumed V12.2 probe.
Exactly four cells: those two patch versions x trace0/120, all PYTHONMALLOC=debug,
one unchanged `test_construction_complete_four_accounts_source_target_account_audit`
node per cell, observed dependency versions pinned. No market files or accounts.
Freeze tracked fixture/source bytes, installed dependency bytes, interpreter and
libpython; retain debugger output, elapsed time, maximum RSS, child exit status,
exact single-node JUnit and actual timeout-dump count. External process-group
deadline900s plus bounded termination grace. No autoretries or fixture reduction.

All four outcomes are retained independently. No actual dump in the120 arm means
NO_TIMER_EXPOSURE, not successful reproduction coverage. SIGKILL does not prove
OOM without separate evidence. Passing means NOT_REPRODUCED, never root-cause
fixed. The debug allocator changes runtime behavior and is investigation only.
Keep all three standard CI groups unchanged. Real numerical forensics remains
paused until independent review adjudicates runtime risk after this finite batch.
Implementation review and exact dispatch approval are required before launch.

四格合成诊断仅定位原生崩溃，不能充当Alpha研究。完整单项JUnit、真实转储次数、
退出码和超时分别记录；不通过反复重跑碰运气。调试分配器不是修复，旧失败保留。
此排查结束后必须复审处置，不自动开启更多排查或真实市场实验。
