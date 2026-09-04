# V10.4 regime-robust result / 市场状态稳健性结果

## Decision / 结论

`NO_RELIABLE_ALPHA`

V11.0 preservation note: the historical `universe placebo` number below is now
classified as `DEPRECATED_REINTERPRETATION_ONLY`. It measured universe
perturbation robustness, not an independently calibrated no-alpha null. This
does not change the original V10.4 rejection.

V11.0 留档说明：下方历史 `universe placebo` 数值现标记为
`DEPRECATED_REINTERPRETATION_ONLY`。它衡量的是股票池扰动稳健性，并非经过
独立校准的无 Alpha 零假设；该重解释不改变 V10.4 原始拒绝结论。

V10.4 ranks discovery candidates by their worst temporal half and worst
benchmark-up/down state before double-cost return and Sharpe. The court now
reports and gates every validation year and both benchmark regimes. These are
additional failure conditions; no existing threshold was relaxed. No
2025–2026 data were read.

V10.4 在双倍成本收益和 Sharpe 之前，先按发现期最差时间半段及最差基准涨跌状态
选择候选。Alpha Court 现在报告并门禁验证期每个年份及基准上涨/下跌两种状态。
这些是新增的失败条件，原有阈值均未降低。未读取 2025–2026 数据。

## Real run / 真实运行

- Capital / 资金：CNY 3,000,000
- New candidates / 新候选：24
- Cumulative trials / 累计 Trial：743
- Selected expression / 入选表达式：`-(rank(profit_ratio)-rank(main_inflow_ratio))`
- Mechanism / 机制：主力资金流相对筹码获利比例的背离

| Metric / 指标 | Discovery 2022 | Validation 2023–2024 |
|---|---:|---:|
| Net excess return / 净超额收益 | 12.73% | -6.52% |
| Annualized net excess Sharpe / 年化净超额夏普 | 1.565 | -0.193 |
| Double-cost return / 双倍成本收益 | — | -14.27% |
| Maximum drawdown / 最大回撤 | — | -15.13% |

| Stability / 稳定性 | Net excess return / 净超额收益 |
|---|---:|
| 2023 | -10.99% |
| 2024 | +5.02% |
| Benchmark-down months / 基准下跌月份 | +1.73% |
| Benchmark-up months / 基准上涨月份 | -8.12% |

| Gate / 门禁 | Required / 要求 | Actual / 实际 | Result |
|---|---:|---:|---|
| DSR | >= 0.95 | 0.00468 | FAIL |
| PBO | <= 0.05 | 0.30 | FAIL |
| Signal placebo p | <= 0.05 | 0.32 | FAIL |
| Return placebo p | <= 0.05 | 0.35 | FAIL |
| Universe placebo p | <= 0.05 | 0.33 | FAIL |
| Year stability | every year positive | 2023 negative | FAIL |
| Regime stability | every regime positive | benchmark-up negative | FAIL |
| Double cost | positive | -14.27% | FAIL |
| Sealed forward | required | not run | NOT ELIGIBLE |

The candidate is rejected. Its 2022 result did not transfer to 2023, rising
benchmark states, doubled costs, or any placebo test. The new stability
attribution prevents aggregate validation return from hiding this failure.

该候选被拒绝。2022 年表现未能迁移到 2023 年、基准上涨状态、双倍成本或任一
伪造检验。新增稳定性归因可防止汇总验证收益掩盖这种失效。
