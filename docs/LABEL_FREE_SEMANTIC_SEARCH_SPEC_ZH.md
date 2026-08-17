# 无标签语义搜索控制器——规格

## 目标

在读取任何真实收益、IC、RankIC、Sharpe 或回测结果之前，提高因子提案质量。本控制器
属于工程与搜索效率原型，不构成真实 Alpha 研究 epoch。

## 身份模型

```text
SemanticPlan
→ MechanismFamily
→ ExpressionVariant
→ ParameterVariant
→ PolicyVariant
```

`ResearchContractVersion` 独立于候选身份，冻结 PIT readiness、预测周期、证伪规则、
snapshot/window authority 和零实证 Trial 预算。

Context 被严格区分为 `CONSTITUTIVE`、`ELIGIBILITY` 与 `POLICY_CONDITION`，只有
构成机制的 Context 进入 family identity。公式正负号或 reverse-rank 只能成为表达式
控制，不能制造新机制。

## 静态漏斗

1. Schema、枚举、周期与预算校验；
2. 受限窗口引用拒绝；
3. required-data 与 PIT readiness 门禁；
4. canonical typed DSL 编译；
5. 语义 family 重复门禁；
6. 表达式重复门禁；
7. 确定性 family tombstone 门禁；
8. 写入 Search Ledger。

缺少 PIT 数据时返回 `DATA_NOT_RESEARCH_READY`。精确语义重复和 tombstone 后代必须
在任何实证数据访问之前拒绝。

## Remote 与 Replay 合同

Remote record 根据渲染后的请求字节和原始响应字节寻址，保存 provider/model、prompt、
parser 版本、sampling config、tool calls、retry parent 与哈希。离线 cache miss 直接失败，
replay 不允许网络回退。

## 合成基准

提交的 fixture 隔离为 `train`、`validation` 和 `sealed_test`，使用三个固定 seed，比较
仅识别精确表达式的 bounded baseline 与语义/tombstone-aware 控制器。成功要求最差 seed
的重复召回率提高、PIT 拒绝正确、重放确定，并保持零实证和零受限窗口访问。

## 硬边界

- `inferential_trial_delta=0`；
- 真实市场矩阵读取为 0；
- 受限窗口访问为 0；
- 远程模型请求为 0；
- 不授权 Alpha Court 或实盘；
- #92、#93 与 Gate 5 边界不变。
