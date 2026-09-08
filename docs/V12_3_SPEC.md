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
with one decoded history and complete compact-ledger checks. External artifact
acceptance and the deterministic bilingual renderer are implemented; complete
launch acceptance and the production once-only supervisor are pending.
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
固定核验入口、外部文件验收及双语生成器已完成；生产环境一次性监督和完整运行验收仍待补齐。
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

## External artifact acceptance / 外部文件验收

The external acceptance component binds the caller's frozen input, calendar and
producer/reference code roots to all51 expected outputs and six control files.
It checks12 complete account receipts, both costs, both97-decision schedules,
event/tail identities across chain and detail files, actual exposure dates, and
source-status aggregation. UNKNOWN and IMPLEMENTATION_MISMATCH remain explicit;
they never become source truth or Alpha certification. Duplicate JSON fields,
nonfinite numbers and bool/float substitutions for integer counts are refused.

Forty lightweight metadata-contract and tampering tests passed in both developer
and independent-review runs. These fixtures test artifact integrity, not account
arithmetic or new market performance. No history decode or account execution is
part of this external layer. Its outcome remains NOT_LAUNCH_ACCEPTED.

The earlier17-test synthetic integration completed, and its durable JUnit,
supervisor and runtime bindings remain available. However, its detailed report
and synthetic source files were in pytest temporary storage and were subsequently
removed by default retention. Those missing files cannot now receive external
acceptance; they must not be recreated and presented as original evidence. A
substantively new renderer/launcher integration requires separate review and a
unique persistent test directory retaining actual inputs and outputs.

外部验收层已完成双人审查及40项轻量测试，核对51份输出、6份控制文件、12份账户
凭证和两套97次维护日程。日期、相位、事件/尾链身份及来源状态必须一致；unknown
不会提升为来源真实或Alpha通过。本层只检查冻结产物的完整性，不重新解码历史或运行账户。

之前17项合成集成的运行回执仍保留，但详细文件被pytest默认临时保留策略清理，
因此当前不能完成该旧产物的外部验收，也不会重跑补造旧证据。后续包含报告和启动器的
实质新集成必须单独审查，使用唯一持久化目录。真实法证运行及最终报告仍未完成。

## Deterministic report projection / 确定性报告投影

The report component projects all36 saved account windows and six primary
comparisons into machine JSON and separate Chinese/English Markdown. It preserves
the full saved daily20-cell/unknown exposure rows and both97-event membership and
support histories. It does not calculate new metrics or reconstruct missing scores.
Annual opening capital is actual carried NAV. Costs are the frozen round-trip
contract and actual saved fees; writeoffs/recovery are valuations, not addbacks
or assumed cash receipts. Missing statistical evidence, unsaved scores, initial
membership and undefined Sharpe are labeled separately rather than replaced by zero.

Rendering verifies all57 accepted source/control artifacts before and after,
creates its reader-report directory exclusively, and verifies exact JSON projection
and deterministic text against actual files. Both languages, the machine report
and a matching rendered receipt are required. Changed text or values cannot be
accepted by only recomputing a local output hash.

Eighteen lightweight renderer tests passed in developer and independent review
runs, with persistent fixtures. These are formatting/integrity tests, not market
results or the completed real forensic report. Production launcher engineering
is approved separately; no real prepare/run or main merge is authorized here.

双语生成器直接展示36个账户窗口及6个主比较，保留完整逐日暴露和成员维护证据，
不新增统计量。年度承接本金、往返成本、估值与现金、不同缺失原因均明确区分。
渲染前后核验57份文件，必须同时具备机器JSON、中英文Markdown和一致的渲染回执。
双方各18项轻量测试通过，测试文件持久保存；这不是新的市场回测或真实法证最终报告。

## Bounded native diagnostic / 有限运行时排查

### Reviewed launch control / 已审查启动控制

The plan binds the unchanged completed parent, saved inputs, full frozen calendar,
clean code snapshot, launcher script and actual Python/native dependency bytes.
A fixed issue comment must explicitly acknowledge the unresolved native-runtime
risk and the exact plan. A shared, code-independent scope claim is consumed by
exclusive creation before any numerical child starts; failures cannot replay it.

One Windows Python3.10.9 child performs saved-account forensics, external artifact
acceptance and bilingual rendering. The parent checks the actual supervisor
receipt, child identity, source/code/runtime bindings, all57 accepted files and
three report files before issuing final success. The four-hour limit combines
checkpoints and child supervision, not an OS-hard deadline over blocking parent
reads; expiry cannot produce final success. Per-process private-memory and free
physical-memory limits remain explicit, not an aggregate machine memory cap.

Developer and independent reviewer each passed51 isolated control tests. These
tests mock process/network boundaries: they are not the new complete synthetic
orchestration, real prepare, real data run or permission to merge main. Those
stages require separate review, persistent evidence and exact launch approval.

计划绑定既有冻结证据、完整日历、干净代码、启动脚本及实际运行库字节；审批必须
明确对应计划并承认尚未根治的原生运行时风险。共享一次性标记先于数值子进程创建，
失败同样不能重放。单个受监督子进程完成核验和双语报告，父进程核对实际回执与文件。
双方各51项控制测试通过，但边界采用模拟；尚不代表完整合成集成或真实运行通过。
四小时是检查点与子进程监督期限，不冒充覆盖父进程阻塞读取的操作系统硬期限。

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
