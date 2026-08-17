# V2 M2：有界 Novelty Gate 与廉价诊断

## 目标

在进入 CPCV 前，用预注册、有边界、可解释的规则拒绝重复或明显不可用候选。该门禁只减少昂贵验证工作量，不替代统计验证，也不承诺真实 Alpha 召回率。

## Novelty Gate

依次支持 canonical AST equality、加法/乘法交换归一化、固定 fixture 数值与秩等价、控制变量残差相关、暴露余弦和语义标签 Jaccard。语义相似度仅作审计指标，不单独触发拒绝。所有拒绝返回 typed reason code。

## Cheap Diagnostics

报告 coverage、missingness、staleness、daily IC/RankIC、residual IC、五分位形态、多空分解、rank turnover、holding decay、风格和行业暴露、日期/regime 集中度及简化成本后 spread。阈值来自冻结配置。

## 工程 benchmark

冻结样例包含 exact、algebraic、numerical、residual duplicate 及两个 known-valid unique fixture。验收要求 exact recall 100%、实证 duplicate precision/recall 至少 95%、CPCV 工作量减少至少 50%、known-valid fixture recall 100%。这些是工程回归指标，不是投资有效性证据。
