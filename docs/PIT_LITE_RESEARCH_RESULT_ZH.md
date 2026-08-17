# V2.9 PIT-Lite 因子研究结果

## 结论

**`NO_ROBUST_ALPHA_POPULATION`**。冻结候选 `flow_confirmation_20_20d` 在 RAW 和价格风格
控制下仍有正 RankIC，但成本后组合收益为负；加入折内 PCA 和统计聚类控制后，2024 RankIC
转负且 placebo 不再显著。该候选不能视为可靠 Alpha，也不能只选择最好看的 RAW 规格晋级。

## 2023–2024 Walk-forward 结果

| 规格 | Mean RankIC | 2023 / 2024 RankIC | 300万净收益 | 年化净 Sharpe | 最大回撤 | DSR |
|---|---:|---:|---:|---:|---:|---:|
| RAW | 0.0381 | 0.0559 / 0.0186 | -3.88% | -0.7903 | -15.74% | 3.29% |
| PRICE_STYLE | 0.0302 | 0.0478 / 0.0111 | -6.61% | -1.6308 | -15.41% | 2.20% |
| PCA_NEUTRAL | -0.0065 | 0.0169 / -0.0320 | -15.35% | -3.8786 | -20.42% | 0.08% |
| STATISTICAL_CLUSTER_NEUTRAL | 0.0016 | 0.0156 / -0.0137 | -20.38% | -5.1337 | -22.55% | 约 0% |

RAW 与 PRICE_STYLE 的 signal/return placebo 均为 0.005；PCA 为 0.845/0.840，统计聚类为
0.420/0.405。2,000 万元规模下四个规格均无容量裁剪，但收益仍为负，因此容量不是主要
阻塞项。

## 完整性

- 日 K 行业字段保持 `B_CURRENT_LABEL_BACKFILL`，仅用于诊断，未进入信号；
- 2023 用 2022 训练，2024 用 2022–2023 训练；标准化、PCA 和聚类均为折内拟合；
- 成功 operation 的 2025/2026 访问为 0；
- Issue #98 新增 4 个 Trial：3 个工程失败和 1 个完成，全部保留；
- 累计推断性 Trial 为 52；
- 结果 SHA-256：`f74674b75eb1991e6436b457a01a0e8dad1d5c1f0669ef3db72c11cb8fe857d5`；
- Source snapshot：`d612a91a0045a1f4543955e19bcea1b26e37c18a818df2f9001b312b8c364587`。

下一步应 tombstone 继续微调该候选的路线，把剩余 Trial 预算留给新的经济机制和新数据
family，而不是降低风险控制、placebo 或 DSR 门槛。
