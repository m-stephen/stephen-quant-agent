# V1.8.20：因子增量价值与收益归因

关联 Issue：[#33](https://github.com/m-stephen/stephen-quant-agent/issues/33)

## 目标

V1.8.20 不扩张候选空间，而是解释资金背离因子较高 RankIC 为何不能转化为可交易收益，并判断该 family 应继续、停止还是重新设计。

## 冻结诊断

- 沿用 8 个固定 20 日候选，只分析 2022—2024 研究区间。
- 对资金背离 parent 输出每日十分位收益、多头端、空头端、多空差和极端日期集中度。
- 在每个决策日横截面内，对已知的价格反转控制和 `log(ADV)` 做 OLS 残差化；不使用未来收益估计暴露。
- 新增归因 Trial 在执行和 DSR 之前登记。
- 缺失控制观测、未来可见数据或奇异控制矩阵一律 fail closed。

## 冻结失败标签

- 残差 RankIC < 0.02：`NO_INCREMENTAL_INFORMATION`
- 十分位单调性 < 0.50：`WEAK_MONOTONICITY`
- 多头端收益 <= 0：`WEAK_LONG_LEG`
- 极端 10% 日期绝对贡献 > 50%：`DATE_CONCENTRATION`
- 成本后 Sharpe < 0.50：`LOW_EXECUTION_SHARPE`
- 最大回撤低于 -25%：`EXCESSIVE_DRAWDOWN`

存在增量信息不足、低执行 Sharpe 或过大回撤时，建议必须为 `STOP_OR_REDESIGN`。2025/2026 窗口继续封存。

