# V10.3 centered cross-source result / 中心化跨源结果

## Decision / 结论

`NO_RELIABLE_ALPHA`

V10.3 adds centered signed interactions and admits predeclared three-field
mechanisms to the bounded generator. A centered interaction multiplies ranks
after mapping each rank from `[0, 1]` to `[-1, 1]`; this distinguishes joint
extremes from the level-biased product used by the original interaction. The
candidate identity, direction, source timing and failed-candidate tombstone
remain deterministic. No 2025–2026 data were read.

V10.3 为有界生成器加入中心化有符号交互，并允许预声明的三字段机制。中心化交互
先把每个排名从 `[0, 1]` 映射到 `[-1, 1]` 再相乘，从而区分联合极端状态，避免
原始排名乘积偏向高水平组合。候选身份、方向、来源时点和失败墓碑仍可确定性重放。
未读取 2025–2026 数据。

## Real run / 真实运行

- Capital / 资金：CNY 3,000,000
- New candidates / 新候选：24
- Cumulative trials / 累计 Trial：719
- Selected expression / 入选表达式：`rank(closing_volume_share)*rank(concentration)`
- Mechanism / 机制：尾盘成交占比与筹码集中状态的联合排序
- Rejected field / 拒绝字段：`multiscale_divergence`（退化）

| Metric / 指标 | Discovery 2022 | Validation 2023–2024 |
|---|---:|---:|
| Net excess return / 净超额收益 | 18.07% | 16.46% |
| Annualized net excess Sharpe / 年化净超额夏普 | 1.843 | 0.657 |
| Double-cost return / 双倍成本收益 | — | 7.92% |
| Maximum drawdown / 最大回撤 | — | -10.31% |

Validation was not stable by year: 2023 net excess return was -1.13%, while
2024 was +17.78%. The candidate therefore remains a mechanism clue rather than
a frozen alpha.

验证期存在明显年份不稳定：2023 年净超额收益为 -1.13%，2024 年为 +17.78%。
因此该候选仅作为机制线索保留，不能冻结为 Alpha。

| Gate / 门禁 | Required / 要求 | Actual / 实际 | Result |
|---|---:|---:|---|
| DSR | >= 0.95 | 0.04731 | FAIL |
| PBO | <= 0.05 | 0.20 | FAIL |
| Signal placebo p | <= 0.05 | 0.03 | PASS |
| Return placebo p | <= 0.05 | 0.01 | PASS |
| Universe placebo p | <= 0.05 | 0.92 | FAIL |
| Double cost | positive | 7.92% | PASS |
| Sealed forward | required | not run | NOT ELIGIBLE |

The positive validation and double-cost returns are useful evidence, but the
large universe-placebo p-value, PBO and deflated Sharpe reject reliability.
V10.3 does not lower any gate and does not open the sealed forward window.

验证期和双倍成本收益为正，说明该线索值得保留；但股票池伪造 p 值、PBO 与
Deflated Sharpe 均不支持可靠性。V10.3 未降低任何门槛，也未打开封存前向窗口。
