# V1.8.16 — 可审计的自动因子发现

## 目标

V1.8.16 将因子研究升级为有预算、可复现的自动流水线：自动生成、筛选、证伪和
回测结构化候选，同时保持 2025 验证期与 2026 最终测试期封存。

## 冻结工作流

1. 编译 `FactorSchema`，校验数据源与字段，并生成确定性的结构指纹。
2. 所有提案（包括重复项）写入 Campaign Ledger；Schema、CPCV、执行和全套件
   Trial 预算在测量前冻结。
3. 在训练期检查覆盖、稳定性和冗余度，并计算 RankIC；每个实证测量均先登记 Trial。
4. 对齐所有候选共同可用的样本面板，执行 purge/embargo CPCV 和 PBO。
5. 只有信号门禁通过后，才运行包含成本、容量和可交易性约束的 Top-K 执行回测。
6. 执行信号打乱、收益打乱、按全局 Trial 数修正的 DSR、PBO 和扩展窗 walk-forward。
7. 输出不可变 JSON、详细中英文报告、研究记忆、Alpha Card 和 fail-closed 组合授权结果。

## 数据与时间边界

- 日线、资金流、集合竞价、融资融券、行业指数、动态股票池及标准化行业/概念成员
  都使用明确的 `effective/available/ingested` 时间语义。
- 缺失或过期的另类数据不得新开仓，但已有持仓必须保留退出通道。持仓行情缺失时，
  仅在显式策略下按零收益陈旧估值并禁止交易；普通基线默认仍直接报错。
- Alpha派仅用于假设生成。历史研究只能读取带 prompt/model/tool 血缘的精确冻结缓存；
  缓存缺失、未来引用、不完整流、重试耗尽或抓取时间晚于决策时间时全部关闭失败。
- 本机路径、原始第三方数据、报告、数据库、凭据和缓存均由 Git 忽略。

## 研究记忆与组合门禁

系统持久化成功、失败、重复、无效和筛除原因，并确定性输出 Explore、Exploit 与
单维度 Mutate 建议。变异候选保存父指纹，必须进入下一次预注册 Campaign；禁止使用
封存期反馈指导搜索。

每个执行胜出候选都会生成 Alpha Card，包含覆盖率、CPCV 稳定性、换手、收益、Sharpe、
回撤、成本、容量假设、完整血缘和暴露测量状态。只有 Alpha Court 与 walk-forward
同时通过时，信号才可进入 Portfolio/PPO。V1.8.16 不增加 PPO、GNN 或实盘下单。

## 复现方式

先在 Git 忽略的 `configs/qd-paths.local.json` 中配置本机路径，再运行：

```powershell
python -m stephen_quant.cli --db artifacts/qd-v1.8.16.sqlite3 qd-auto-discover-suite `
  --paths-config configs/qd-paths.local.json `
  --suite-manifest configs/v1.8.16-suite.json `
  --ingested-at 2026-08-17T12:00:00+08:00 `
  --output reports/qd-v1.8.16
```

命令成功代表审计流程完整结束，不代表因子必须通过。严格否决弱因子是有效结果，也不会
触发验证期或最终测试期开放。
