# Next bounded direction / 下一有限研究方向

Design investigation only;**not a new preregistration, candidate, fit or market
run**. Current debt3600. Preserve V11.18 and all previous negative evidence.

V11.18 found no incremental lead. Its2023conditional allocation saturates at25%,
and its gross200-stock basket labels are not the actual net40-stock policy.
Simply changing floors or training horizons now would chase revealed outcomes.

## Proposed question / 拟研究问题

Investigate date-balanced, risk-cell-matched **pairwise ranking** of stocks using
existing frozen fields. This would learn a relative selection objective rather
than another hand-written factor or a market-level absolute-return regression.
The project already has ridge/stump baselines, residual single-slope fits and
many fixed rank interactions;those are mandatory baselines,not new inventions.
An initial code search found no dedicated date-balanced pairwise loss. Complete
static deduplication before claiming novelty or reserving a numerical batch.

[Burges et al.,Learning to Rank using Gradient Descent](https://www.microsoft.com/en-us/research/publication/learning-to-rank-using-gradient-descent/)
motivates a probabilistic pairwise ranking objective. The source studies toy and
web-search data,not A-share trading;it offers an optimization method,not evidence
of financial Alpha. Only its official research-page abstract was reviewed here.
Read the relevant original objective before committing an implementation.

## Required contract before execution / 执行前要求

1. Fixed very small model family,dimensions,parameter counts,seed and training
   schedule. Begin with linear pairwise logistic and one bounded interaction
   representation;no deep-network or hyperparameter sweep without a new rationale.
2. Pairs formed inside an as-of date/risk/liquidity cell;equal total weight per
   decision date. Thousands of stock pairs are not thousands of independent
   market observations. Pair sampling must not depend on future winners.
3. Labels have explicit executable entry and maturity dates;no final-window
   labels. Baseline-relative returns,missing entry/exit handling,corporate-action
   approximations and any cost proxy must be stated. Do not call a raw rank score
   a probability-calibrated expected return or use it as a bps swap hurdle.
4. All learned transforms and interaction selection train-prefix/fold local,
   native fit receipts and immutable models before prediction. Synthetic planted
   nonlinear rank signals,style-only/noise nulls,maturity/gap invariance and
   trained-vs-shuffled controls must pass before any numerical epoch.
5. Same-field,as-of risk-cell portfolio controls with fixed target construction,
   turnover/cash/risk diagnostics,original frozen anchors and standard/double
   cost. Predeclare economic gates and full trial accounting first. Correlated
   pairs/models/costs do not erase historical searches.
6. Independent source/pair/gradient/prediction/target/account audit;reserve the
   whole finite budget before real values. Keep2025/26sealed,no mainmerge/trading.
   A survivor must still face the unchanged Court and credible execution gates.

## Rejected duplicate direction / 去重记录

An overnight/intraday decomposition was considered from Lou,Polk and Skouras,
[A Tug of War](https://personal.lse.ac.uk/polk/research/TugOfWar.pdf). Its component
persistence and offsetting cross-period effects do not imply tradable A-share
open-to-open alpha. Existing `price_discovery_lab.py` already implements
overnight_intraday_divergence and gap_fill_pressure;seeds include overnight-gap
reversal and intraday strength. Do not relaunch those under a new paper label.
This was a static/literature deduplication,not another numerical trial. Only
the abstract and relevant return-definition passages were examined,not the
entire paper or a claimed replication.

中文摘要：下一步优先审查按日期等权、同风险格内的成对排序学习，解决“训练目标与选股目标是否匹配”的问题。
先固定小模型、标签时钟、对照、预算及原生拟合证据，再做合成验证和有限真实实验。
这不是更多股票对就有更多独立样本，不是把预测分数当收益率，也不能保证找到Alpha。
旧日内/隔夜分歧已实现，不能换名称重复探索；2023/24的重复开发属性和统计门槛不变。
