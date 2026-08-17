# V2 M3 测试结果（中文）

## 结论

- **工程验收：通过。** 边际价值 scorecard 已覆盖 residual/conditional IC、long-only/long-short 增量、成本、Sharpe、回撤、换手、尾部、容量、复杂度与数据成本。
- **排序目标：通过。** 冻结 fixture 中，较低 standalone IC 但正交的候选排在较高 IC 重复候选之前。
- **fold-local 验收：通过。** 每个残差模型只拟合该 fold 的 train 行；改变 test 行不会改变训练系数。
- **确定性验收：通过。** 相同冻结输入产生完全相同 scorecard 和排序。
- **命名边界：通过。** V1.8.21 始终显示为 `reference_only`；引擎不能把 research-only 记录提升为 validated alpha。

## 解释

该结果纠正了“只追求更高 IC”的搜索偏差。若候选的大部分信号已被 reference portfolio 包含，即使 standalone IC 很高，也可能没有新增组合价值。正交候选则通过 residual IC 和增量组合指标获得优先级。

## 验证记录

- M3 定向测试：4 项通过。
- 全量测试：208 项通过。
- 静态检查：通过。
- Python 编译检查：通过。
- 2025 validation / 2026 final test：未打开。
- 本阶段 fixture 仅验证排序性质，不构成 Alpha 证据。

## 下一步

进入 M4：用 append-only structured failure graph 保存失败、谱系和决策，在 epoch 开始时冻结预算与 policy，epoch 关闭后才允许更新下一轮 prior。
