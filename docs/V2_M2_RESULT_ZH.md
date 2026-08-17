# V2 M2 测试结果（中文）

## 结论

- **工程验收：通过。** Novelty Gate 和 Cheap Diagnostics 已完成，所有拒绝均有 typed reason code。
- **重复识别 benchmark：通过。** exact duplicate recall 100%；实证 duplicate precision 100%、recall 100%。
- **工作量目标：通过。** 冻结 fixture 中 6 个候选有 4 个在 CPCV 前被拒绝，昂贵工作量减少 66.7%。
- **工程有效样例保护：通过。** 两个 known-valid fixture 均保留，recall 100%。
- **重要限制：** fixture 指标只验证工程回归，不代表真实 Alpha 的统计召回率或盈利能力。

## 已覆盖诊断

coverage、missingness、staleness、daily IC/RankIC、residual IC、五分位收益形态、多空分解、rank turnover、holding decay、风格/行业暴露、日期/regime 集中度和简化成本后 spread 均已进入 typed report。

## 验证记录

- M2 定向测试：5 项通过。
- 全量测试：204 项通过。
- 静态检查：通过。
- Python 编译检查：通过。
- 2025 validation / 2026 final test：未打开。
- 本阶段未将 fixture 结果登记为 Alpha。

## 下一步

进入 M3：针对版本化 reference portfolio 计算 leakage-safe residual/conditional IC 和边际组合价值，证明“较低 standalone IC 但更正交”的候选可以优先于高 IC 重复候选。
