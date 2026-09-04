# V10.2 Cross-source alpha result / 跨源 Alpha 结果

## Decision / 结论

`NO_RELIABLE_ALPHA`

V10.2 joined verified fund-flow and chip data on the prior signal date and
opening-auction data on the next execution date. The join uses canonical adapter
fields and binds the immutable multisource snapshot together with the minute
feature snapshot. No 2025-2026 data were read.

V10.2 将资金流和筹码数据按信号日连接，将集合竞价按下一执行日连接。联接使用
适配器的规范字段，并把不可变多源快照与分钟特征快照共同绑定。未读取 2025–2026。

## Real run / 真实运行

- Capital / 资金：CNY 3,000,000
- New candidates / 新候选：24
- Cumulative trials / 累计 Trial：671
- Selected expression / 入选表达式：`rank(concentration)`
- Meaning / 含义：筹码 15%–85% 成本区间相对加权成本的宽度
- Rejected field / 拒绝字段：`multiscale_divergence`

| Metric / 指标 | Discovery 2022 | Validation 2023–2024 |
|---|---:|---:|
| Net excess return / 净超额收益 | 27.33% | 10.41% |
| Annualized net excess Sharpe / 年化净超额夏普 | 2.023 | 0.373 |
| Double-cost return / 双倍成本收益 | — | 7.17% |
| Maximum drawdown / 最大回撤 | — | -16.75% |

| Gate / 门禁 | Required / 要求 | Actual / 实际 | Result |
|---|---:|---:|---|
| DSR | >= 0.95 | 0.00361 | FAIL |
| PBO | <= 0.05 | 0.35 | FAIL |
| Signal placebo p | <= 0.05 | 0.04 | PASS |
| Return placebo p | <= 0.05 | 0.10 | FAIL |
| Universe placebo p | <= 0.05 | 0.47 | FAIL |
| Double cost | positive | 7.17% | PASS |
| Sealed forward | required | not run | NOT ELIGIBLE |

The chip-concentration candidate is worth retaining as a mechanism clue, but it
is not reliable alpha. Its return is sensitive to return permutation and the
exact tradable universe, while multiplicity-adjusted evidence remains weak.

筹码集中度候选可以作为后续机制线索保留，但不是可靠 Alpha。它对收益置乱和精确
可交易股票池敏感，多重检验调整后的证据仍然不足。
