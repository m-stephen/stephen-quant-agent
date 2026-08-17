# V1.8.18：20 日资金背离稳定性与容量压力测试

关联 Issue：[#29](https://github.com/m-stephen/stephen-quant-agent/issues/29)

## 冻结假设

V1.8.17 的 20 日 walk-forward 选择持续偏向 `flow_price_divergence_60`。V1.8.18 只检验该家族的增量信息、状态稳定性和容量敏感性，不降低任何 Alpha Court 门槛。

## 搜索空间

- 期限：仅 20 日。
- 候选：8 个，包括 parent、5/60 与 20/60 资金 surprise、大单和特大单 surprise、资金持续性×价格反转，以及两个控制因子。
- CPCV 上限：6；成本执行上限：3；参与率压力 Trial：1%、5%、10% 三个。
- 研究截止：2024-12-31；2025 验证期和 2026 最终测试期封存。

## 状态与容量诊断

- 市场状态由执行日前 20 个交易日的等权市场收益和波动率构造。
- 高低波动阈值只使用当时及此前已知的历史滚动波动率。
- 容量分层使用决策时点前可知的 ADV，将每日横截面分为低、中、高三个组。
- 参与率压力保持佣金、印花税、滑点和冲击模型不变。
- 所有压力配置先登记 Trial，再计算 DSR，避免事后压力测试逃避 multiplicity ledger。

## 行业中性约束

现有申万文件是行业指数，不包含历史个股成员关系；同花顺概念压缩包主要从 2025 年开始。系统只接受带 `effective_at` 和 `available_at` 的 PIT 股票—行业映射，并要求每只股票在决策时点恰好属于一个可见行业，否则 fail closed。本轮不运行伪造的行业中性回测。

## 一键运行

```powershell
stephen-quant --db artifacts/qd-v1.8.18.sqlite3 qd-auto-discover `
  --paths-config configs/qd-paths.local.json `
  --manifest configs/v1.8.18-flow-stress.json `
  --ingested-at 2026-08-17T00:00:00+08:00 `
  --output reports/qd-v1.8.18-flow-stress
```

工程通过不等于 Alpha 通过；最终仍由 CPCV、成本、placebo、PBO、全局 Trial DSR 和 walk-forward 联合决定。
