# V11.16 recovery / 恢复点

Issue184,PR194,branch codex/v11.16-sparse-events,stacked on unmergedPR193.
Runtime commit98dc03ef83300d90f3e2fa90f3d5dae5bd6d1c6e.
Runtimecaa47f4fa916baa2b2e0fdefe45cdeae69c824f483bcb4bb6fc658dec839fd46.
Driver4629d7d29241e4807c3503567f7d7c3341872252204dbc665c207d1be2e1299a.
Preregistration5561319318. Operation artifacts/sparse-events/epoch-001 is COMPLETE.
Do not rerun the operation or bypass its parent claim with a new output path.

## Completed evidence

50/50 nativeNOFIT accounts;Trial lower bound3456→3506,no failed/unused reservations.
Frozen snapshotb813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51.
Original V11.4 epoch-002 inputs remain unchanged,2022warmup,2023/24reuseddevelopment.
No2025/26 reading or source refresh.13protected source/prior/card/ledger files intact.

RESULTc547a65d23578c30ff91ed7c84365ff057153c9c7ea163b657f02bc1bd30ef18.
Auditfd9b50aa1754b5db394575424b6030114f02296f112a9dd78ada89415c12bb4f.
NativeReport4dd66296732e35cee40d03bfe65ae0dbba67aeb43f05eb7ca5644143adc2e290.
Independent SQL reconstructs3,381,292 raw-source history rows,previous20sampleSDs,
asof eligibility and12risk cells. Independent reference reconstructs all8event
identities,qualifying triggers including rejected ones,cooldown,matched controls,
admissions and target clocks. All50accounts cash/NAV/marks/fees/capacity/year/SR/DD,
nativeSQLite contracts/results and economic screens reconcile.150evidence files
bound;maximumbalance residual4.656612873077393e-10CNY. Bothlowvolanchors replay
byte-identically against V11.14. No runtime or driver edits after numerical read.

39new synthetic tests pass2.01s;full924passed1skipped180.10s. Three premarket
synthetic runs were interrupted to diagnose slow nested DuckDB parameter import
lookups. ScalarJSON fixture transport fixes this;not market retries. Fixture
name stock triggered the intended ST filter and was corrected to firm before
market access. RuntimeCI34053905620success. Check final report HEAD CI before
Ready;do not merge main. AllnewPython scripts andsrc/tests RuffPASS.

Bothlanguage reports and full50account aggregate JSON are committed;source
rows,eventstock identities,account paths,local config andnativepayload remain
gitignored. Native schema validationPASS. Visible/pixelQA deliberately deferred
under user's quiet-until-usable instruction;noHTML/Sites or rendered claim.

## Research outcome

0/8identities survive;all16event/cost full-period net returns negative.
Every identity passes admission-count andcontrol-matching gates atbothcosts,
butfailsannualreturns,Sharpe,drawdown,andtotal/annualcontrolincrements.
NoDSR/PBO/placebo/CourtPASS. Not an access or inadequate event-count problem.
Primary annual admissions430–484. Hashmatches100%;worstconfirm-only476/478
=99.58%. Per-stockfirst-hit/cooldown doesnotmakeportfolioexposuresparse:
82bpsmeancash5.76–10.86%;targetsusually~36–39of40.

Descriptivelybesttotalnetandminimumcontrolgapat82bps:
negative_price_innovation--recovery_positive_flow--lag3:
total−0.6408274%,2023−13.3554205%,2024+14.6744241%,SR.0941175,
MDD−38.0123409%,CNY−19,224.82;164bps−17.7349102%.
Original lowvol82bpstotal+19.4605587%;gap−20.1013861percentagepoints.
No candidate is promoted from this batch;originalV11.11card remains frozen.

## Next distinct investigation (not yet a registered experiment)

Do not incrementally raise shock thresholds,reverse directions,pick the strong
year or repeat horizon sweeps on this failed batch. Investigate a genuinely new
information channel within existing frozen inputs: cross-stock lead/lag or
information diffusion,not another own-stock flow×price filter. Static search of
discovery code andV11docs found no existing implemented lead/lag/spillover
generator (this is bounded search evidence,not proof of worldwide novelty).

Before numerical work,inspect the complete existing catalog for duplicates,
justify a simple economic mechanism and compare at least own-stock information,
market/risk-cell common signal and structure-shuffled peer controls. Any peer
graph,normalizer or forecast parameters must fit strictly within a training
window/fold and bind native fit lineage;contemporaneous or future industry
memberships must not substitute for historical graph evidence. Keep the graph
and signal budget finite,control turnover,capacity and actual net execution.
Reject a design that merely relabels the same already-tested information.
Use existing frozen data first;do not demand a PIT rebuild or paiddata bydefault.

No new budget,graph or real numerical read has been authorized by this design
note alone:the continuing user delegation permits completing a concrete plan,
then preregistering it inIssue184 and nativeledger before its first read.
All new attempts startfrom3506;keepfullfailedfamily,notonlywinners.
Any truly incremental survivor is frozen before deepercapacity/delay/regime/
placebo/identifiableDSR/PBO challenges. No lowering formal thresholds,no
automaticbrokeractions. If safe meaningful paths are genuinely exhausted,ask
once for a concrete necessary input rather than claiming success or certainty.

## Recovery and boundaries

First check latestIssue184/PR194comments,HEAD/CI,processes,RESULT/ABORTED/claims.
Never rerun V11.15orV11.16. PR193270163b alreadyReady,CI34051764251success.
Rootcodex/v4-8-sealed-alpha-court retains23unrelateddirtyfiles;do not modify,
reset,checkout orstage them. OldstackedPRdependencies remain unless verified
merged;no mainmerge. OriginalV11.11card/targets stay in originaltree;do not
substitute checkoutCRLFbytes. Localconfig identifies all originalpaths.

Existingv10-alphaheartbeat30minutes,not a new automation. Ordinaryfailedor
noncertifiedobservations stayquiet. Notify only usableAlpha,actionableblocker
or majorfault. Stopnewsearchandpauseautomationonlywhenallrequiredvalidation
supports usableAlpha;reportbenchmark,cost/capacity/statisticalevidenceandlimits.
Testing removesAlphaPaivariables fromchildenvironmentonly;neverprintsecrets.

## 中文摘要

本轮全部完成且不得重跑。50账户和独立源/事件/账户/账本复核通过，0个Alpha晋级。
事件足够且匹配完整，问题是跨年收益、成本后增量和回撤，而不是单纯数据缺失。
全市场汇集后仍接近满目标，单只股票的稀疏事件不等于低仓位组合。
下一方向先检索排重跨股信息扩散/领先滞后机制，严格训练期拟合图及参数，配置
自有信号、市场公共信息和打乱图对照；明确有限预算后再登记。当前没有登记或
运行该后续实验。继续保护旧候选、所有Trial、2025/2026封存和main。
