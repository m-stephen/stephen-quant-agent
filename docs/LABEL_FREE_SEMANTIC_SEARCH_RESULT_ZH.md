# 无标签语义搜索控制器——结果

## 结论

`EFFICIENCY_GAIN`

冻结的合成基准包含 9 个提案，分布于 train、validation 和 sealed-test，固定使用
seed 7、19、41。

## 证据

| 指标 | Bounded baseline | Semantic controller |
|---|---:|---:|
| 最差 seed 重复召回率 | 0.20 | 1.00 |
| 语义决策正确率 | — | 每个 seed 9 / 9 |
| 避免昂贵评估 | 取决于 baseline | 每个 seed 6 / 9 |
| 正确机制覆盖 | — | 3 / 9 个提案 |

三个 seed 的汇总指标完全一致。控制器正确拒绝了语义变体、精确后代、tombstone family
和 PIT 阻塞的行业方案，同时保留三个不同机制。

## 完整性审计

- 新增 Inferential Trial：0；
- 真实市场矩阵读取：0；
- 受限窗口访问：0；
- 远程模型请求：0；
- replay：确定且与内容哈希绑定；
- 输出：JSON、中英文 Markdown。

该结果只验证搜索控制工程，不证明存在盈利因子，也不授权在 PIT 数据缺口与 Gate 5
解决前进行真实收益型研究。
