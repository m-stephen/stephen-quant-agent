# V11.17 — Statistical peer information / 统计关联信息

## Question and bounded budget / 问题与预算

Can a train-only stock association graph add net information beyond own-stock
reversal, common risk-cell information, and a relabelled graph? This is a proxy
experiment, not a customer–supplier graph or a causal replication of Cohen and
Frazzini (2008). Existing frozen daily and flow fields are sufficient to test
this narrow question. No new industry labels or source purchases are required.

Issue #184 continuation: debt 3506 -> 3556. Exactly 50 native accounts: two
signals x three volatility strata x four policies x two costs, plus the two
original lowvol anchors. All plans and both training stages are registered before
first numerical access. No adaptive threshold/sign/horizon sweep or retry.

## Frozen contract / 冻结契约

- Same V11.4 epoch-002 snapshot; 2022 training/warmup, reused 2023–2024 development.
  No 2025/2026 access. Preserve the V11.11 card, targets and all earlier ledgers.
- Receiver eligibility: existing as-of non-ST, ADV60 >= CNY10m, history >=20,
  finite risk fields and five consecutive global sessions of return and flow.
  Price returns use adjacent-session adjusted closes; absent sessions reset history.
- Unsupervised graph: 2023 fitted on 2022; 2024 on 2022–2023; remove the final
  five global training sessions. Cross-sectionally demean one-day returns on each
  training day; pairwise Pearson correlations with >=120 overlapping sessions.
  Each node needs >=120 observations. Select ten highest positive correlations
  >=0.15, tie by instrument, exclude self. Receivers with <10 edges are absent.
  No return labels, prediction-year observations or supervised fit are used.
- Shuffle control: fixed SHA-256 ordering induces a node permutation inside the
  12 training-end risk cells (3 volatility strata x2 volatility x2 ADV bins).
  Conjugate graph endpoints with that permutation, preserving graph topology,
  weights and risk-cell structure, not actual economic identities. One fixed
  permutation, not a statistical placebo p-value.
- Price signal: positive-correlation weighted peer five-day simple return minus
  own five-day return. Flow signal: weighted peer mean five-day net-flow/turnover
  ratio minus own mean ratio. Require >=8 of each graph's ten peers currently
  eligible; renormalize only available weights. Both graph supports are required
  for every policy, so missingness cannot privilege the candidate.
- Four policies: peer gap, negative own value, shuffled peer gap, stable hash.
  A contemporaneous common risk-cell value minus own value gives exactly the same
  within-cell ordering as negative own value; explicitly test this identity and
  share that control account, rather than present it as independent evidence.
- Recompute 12 risk cells from common current support. Each stratum has four
  cells; each sleeve selects ten per cell, retains incumbents in top13, at2.5%
  per name. Four predeclared phases0/5/10/15, 20-session rebalance, net sleeves
  into one continuous target_changes account. No missing-cell redistribution.
- CNY3m, 82/164bps full round-trip, existing lagged capacity, limit/suspension,
  stale writeoff/recovery. Original anchors replay with their full_target mode.
  Adjusted fractional units remain an engineering assumption, not broker proof.
- Screening: at BOTH costs, positive return in BOTH years, Sharpe >=0.7,
  max drawdown >=-25%, total net increment >=3pp against every same-stratum
  control and original lowvol, annual increment >=-5pp versus every control.
  Common receiver coverage averaged daily >=70% in each year and >=40 names
  in each stratum on >=95% of signal dates. All provenance/account audits pass.
  All six primary identities are reported. Screens are not Alpha Court PASS.

## Engineering acceptance / 工程验收

Native unsupervised fit contracts must distinguish observation dates from label
dates without inventing labels or relaxing legacy supervised chronology.
Record exact graph/model bytes, observed sessions, snapshot and runtime hashes.
Before predictions validate graph stage, immutable artifact and cutoff.
Synthetic tests cover future poisoning, missing/gap handling, deterministic
pairwise correlation, self exclusion, shuffle topology, matched support,
training/validation boundary and unchanged prior supervised fit behavior.

Independent checks reconstruct source returns/flow, sampled and selected graph
correlations, model cutoffs, source/target clocks, all account cash/NAV/cost paths,
controls, annual results and trial lineage. Store all raw evidence locally in
ignored artifacts. Publish bilingual reports and aggregate results only.

Any survivor is frozen before deeper delay, capacity, regime and identifiable
DSR/PBO/placebo challenges; no claim of usable Alpha from reused history alone.
Failed mechanisms are archived; they do not license editing this frozen batch.

中文：本轮验证跨股统计关联是否真正增加信息，不把相关性称为产业链。先登记50项，
再读取旧快照；图仅在过去训练期拟合，控制自身信号、公共信号和打乱网络。六组候选
必须同时通过两种成本、两年及对照增量门槛，之后才值得进入更深入验证。保留全部
失败结果和旧候选，不修改main，不解封2025/2026。

Motivation: https://pages.stern.nyu.edu/~afrazzin/pdf/Economic%20Links%20and%20Predictable%20Returns%20-%20Cohen%20and%20Frazzini.pdf
