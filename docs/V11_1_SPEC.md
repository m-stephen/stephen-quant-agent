# V11.1 Mechanism Discovery / 机制化 Alpha 研究

V11.1 implements [Issue #172](https://github.com/m-stephen/stephen-quant-agent/issues/172).
It is one bounded development epoch, not a restart of continuous historical
return search.

## Frozen scope / 冻结范围

- Three mechanism families and exactly fifteen candidates.
- Four promotable candidates and one non-promotable negative control per family.
- Primary horizons are fixed at 20 sessions for chip-state transitions, 10 for
  flow-price mismatch and 5 for auction-close absorption.
- CNY 3 million, long-only Top 40, ten-name buffer, 41 bps standard cost,
  82 bps stress cost and 5% participation.
- Raw global Trial accounting continues from 755; successful execution ends at
  770 and cannot create a successor epoch.

三条机制各包含四个正式候选和一个不可晋级负对照。主期限、方向、公式、组合和
成本在收益读取前冻结。本轮最多增加 15 个 inferential Trial，结束后强制停止。

## Label-free screen / 无标签预筛

The runner first loads features without querying execution or exit prices. It
checks date coverage, cross-sectional variation, exact numeric fingerprints,
estimated buffered turnover and capacity. Any failure returns
`LABEL_FREE_PREFILTER_NOT_READY`, adds no Trial and never loads a return label.

Real data showed 85.4%–92.3% eligible date coverage, 100% variable eligible
dates, distinct score fingerprints and estimated capacity above CNY 350m for
all fifteen frozen candidates. This feature-only evidence is allowed to freeze
the catalog; it is not evidence of return quality.

## Risk cleaning and court / 风险清理与门禁

At each prediction cross-section, scores are demeaned within point-in-time
Shenwan L2 industry groups and residualized against contemporaneous liquidity
rank and volatility rank. The transform uses no future or cross-time fit.

After Trial registration, 2022–2024 development returns are attached. Each
candidate then receives the V11 bridge, standard/double-cost portfolio,
year/regime attribution, universe robustness, three identifiable null tests,
DSR and family CPCV/PBO. Negative controls cannot be promoted. DSR must remain
at least 0.95 and identifiable PBO at most 0.05.

2025–2026 historical returns remain sealed. Passing only means eligibility for
independent forward evidence; it is not a reliable-alpha or trading claim.
