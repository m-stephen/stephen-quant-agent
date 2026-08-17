# V2 M3：边际 Alpha 引擎

## 目标

候选不再只按 standalone IC 排序，而是相对版本化 reference portfolio 评估新增信息和可交易价值。V1.8.21 仍是 `research_only` reference，不是 validated alpha library。

## 方法

- 每个 fold 仅用 train 行拟合 `candidate ~ reference` 残差模型，再应用于该 fold 的 test 行；
- 输出 standalone IC/RankIC、residual IC/RankIC 和 redundancy correlation；
- 用 reference score 与 reference + residual blend 构建 long-only / long-short 比较；
- 显式计算成本后的收益、Sharpe、最大回撤、turnover、尾部收益和容量；
- 边际 utility 同时惩罚新增换手、复杂度和数据成本。

## 验收

冻结 fixture 必须让较低 standalone IC 但与 reference 正交的候选，稳定排在较高 IC 的重复候选之前。修改 test 行不得改变 fold-local 训练系数；相同冻结输入必须得到完全相同 scorecard。
