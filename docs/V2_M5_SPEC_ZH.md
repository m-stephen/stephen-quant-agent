# V2 M5：预算化自主研究闭环（Shadow Mode）

## 单命令

```text
stephen-quant --db artifacts/v2-shadow.sqlite3 v2-shadow-validate --config configs/v2.0-m5-shadow.json --output reports/v2.0-shadow
```

该命令使用冻结 synthetic engineering fixture，默认不请求模型、不读取外部数据、不连接交易执行。`--dry-run` 仅生成并编译提案，不接触任何实证反馈；`--kill-switch` 在写入研究状态前立即停止；`--replay-manifest` 离线校验既有运行包。

## 编排

候选依次经过 constrained proposal、typed compiler/PIT audit、novelty gate、cheap diagnostics、marginal value 和 future-validation decision。失败写入 structured failure store，并通过关闭后的 epoch 产生 revise 或 STOP_FAMILY。所有 proposal/decision 进入 Search Ledger；任何数值反馈都先创建 Inferential Trial。

## 决策边界

M5 只允许 `REJECT`、`REVISE`、`STOP_FAMILY`、`PROMOTE_FOR_FUTURE_VALIDATION`。最后一种只表示值得未来独立验证，不是 Alpha Court 通过或实盘许可。2025 validation 与 2026 final test 的访问次数必须为 0。

## 输出

命令生成 JSON、中英文 Markdown、Replay Manifest 和完整 registry provenance。所有生成物位于 git ignored 的 reports/artifacts 路径。
