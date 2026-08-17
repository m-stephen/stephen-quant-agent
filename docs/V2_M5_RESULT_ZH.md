# V2 M5 测试结果（中文）

## 最终结论

- **V2.0 Shadow Mode 工程验收：通过。** 单命令已完成 proposal → audit → novelty → diagnostics → marginal value → failure learning → decision。
- **自主闭环目标：通过。** 系统自动提出 3 个初始假设，并从失败生成 1 个单维修订，共登记 4 个候选。
- **四类决策齐全：** `REJECT`、`REVISE`、`PROMOTE_FOR_FUTURE_VALIDATION`、`STOP_FAMILY` 各至少 1 个。
- **双账本完整：通过。** 本次运行写入 8 条 Search Ledger；4 次数值反馈全部各自绑定 Inferential Trial。
- **预算与停止：通过。** 使用 candidate 4/6、compute 4/4、statistical trial 4/4、token 0/1000；耗尽 family 下一 epoch 预算为 0。
- **封存与重放：通过。** 2025 validation / 2026 final test 访问 0；Replay audit 通过；离线重放模型请求 0。
- **不是 Alpha 结论。** promoted 候选只进入 future validation 队列，Alpha Court 在 synthetic fixture 上明确未运行。

## 冻结正式运行

- 实现 commit：`ae90efb825066b86ec47817657ed9be60635af81`
- Experiment：`exp_d1ad1036c3b74c25`
- Snapshot：`snap_7cef53a4ce05c38b`
- Snapshot SHA-256：`7cef53a4ce05c38b561251c8e1e3a0034d7f5b9a68a0ad037180c6e2a05e33ba`
- Replay Manifest SHA-256：`6e6e0b090d30b3ef5d25f176ffcbabdfb4823ef2feeb8aa7d152529b8790f497`
- Semantic Decision SHA-256：`c4234f283b946722e0617ecbca450a7c0c05534b04dbcbfaf8e29d02f90e9784`

## 决策

| Family | 决策 | 原因 |
|---|---|---|
| flow_price_divergence | REJECT | EXACT_AST_DUPLICATE |
| margin_financing | REVISE | LOW_COVERAGE |
| margin_financing（修订） | PROMOTE_FOR_FUTURE_VALIDATION | POSITIVE_ORTHOGONAL_ENGINEERING_FIXTURE |
| large_flow_surprise | STOP_FAMILY | FAMILY_EXHAUSTED |

## 自动验证

- M5 定向测试：6 项通过；
- 全量测试：218 项通过；
- ruff、compileall、git diff check：通过；
- registry audit：snapshot / experiment / trial counter 全部 PASS；
- 离线 replay：verified=true，sealed access=0，model requests=0。

## 如何测试

```text
stephen-quant --db artifacts/v2-shadow.sqlite3 v2-shadow-validate --config configs/v2.0-m5-shadow.json --output reports/v2.0-shadow
```

下一阶段应使用新的预注册 research experiment 接入真实 QD 数据，并在不打开 2025/2026 封存窗口的前提下运行正式 cheap diagnostics、CPCV、placebo、DSR/PBO 和成本门禁。
