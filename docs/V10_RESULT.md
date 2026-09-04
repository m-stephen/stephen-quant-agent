# V10.0 Real-data Validation Result / 真实数据验证结果

## Decision / 结论

`NO_RELIABLE_ALPHA`

V10.0 completed the first bounded daily-plus-minute automatic discovery run. The
winning discovery candidate did not survive the frozen statistical and cost
gates, so it is retained as negative evidence and is not promoted to a sealed
forward test.

V10.0 已完成首轮日 K 与分钟结构特征的有界自动发现。发现期优胜候选未通过冻结的
统计与成本门禁，因此仅作为失败证据留档，不提升至封存前向测试。

## Data and lineage / 数据与血缘

- Source minute snapshot: `fde4ef3ef60aafe6a7fca932381b96b49429e30d77ace6cbe3b4e8e2d9817dfb`
- Composite feature snapshot: `6c3d8d8d768868066fba6fc535542b90bf8256b118644040452fc5e2feb42a6b`
- Monthly feature snapshots: 36/36 verified
- Feature rows: 3,723,346
- Feature period: 2022-01-01 through 2024-12-31
- 2025-2026 reads: none
- Capital: CNY 3,000,000
- Candidate trials in this run: 24
- Cumulative recorded trials used by DSR: 557

## Selected candidate / 入选候选

`rank(vwap_deviation) - rank(volatility_20)`

The candidate prefers lower intraday VWAP displacement relative to trailing
daily volatility. It was selected only from the 2022 discovery window.

该候选比较日内 VWAP 偏离与过去 20 日波动率的横截面秩，方向偏向较低的相对日内
偏离；候选选择仅使用 2022 年发现窗口。

| Metric / 指标 | 2022 discovery / 发现期 | 2023-2024 validation / 验证期 |
|---|---:|---:|
| Net excess return / 净超额收益 | 16.85% | 1.06% |
| Annualized net excess Sharpe / 年化净超额夏普 | 1.404 | 0.144 |
| Double-cost return / 双倍成本收益 | 11.92% | -6.70% |
| Maximum drawdown / 最大回撤 | -5.96% | -21.20% |

Validation year attribution was +8.12% in 2023 and -6.53% in 2024. Capacity
passed at approximately CNY 389.8 million, so capacity was not the limiting
gate for a CNY 3 million portfolio.

验证年度归因为 2023 年 +8.12%、2024 年 -6.53%。容量估计约 3.90 亿元并通过，
因此对 300 万元组合而言，容量不是限制因素。

## Frozen court gates / 冻结门禁

| Gate / 门禁 | Required / 要求 | Actual / 实际 | Result / 结果 |
|---|---:|---:|---|
| DSR | >= 0.95 | 0.0232 | FAIL |
| PBO | <= 0.05 | 0.35 | FAIL |
| Signal placebo p | <= 0.05 | 0.11 | FAIL |
| Return placebo p | <= 0.05 | 0.16 | FAIL |
| Universe placebo p | <= 0.05 | 0.16 | FAIL |
| Standard-cost validation return | > 0 | 1.06% | PASS |
| Double-cost validation return | > 0 | -6.70% | FAIL |
| CNY 3m capacity | pass | pass | PASS |
| Sealed forward test | required for final PASS | not run | NOT ELIGIBLE |

The result demonstrates that the V10 pipeline can generate, record, select and
falsify real candidates without reading the sealed window. It does not
demonstrate a deployable alpha.

该结果证明 V10 流水线可以在不读取封存窗口的情况下生成、记录、选择并证伪真实
候选，但不能证明已经获得可部署 Alpha。

