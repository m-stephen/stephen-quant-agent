# V2 M0：兼容契约、分层 ID、双账本与重放

## 目标

M0 不建立第二套研究基础设施。它把现有 V1 FactorSchema、safe DSL、fingerprint、Experiment Registry 和 Trial Ledger 扩展为 V2 可重放契约。

## 设计

- V2 合同内嵌完整 V1 schema JSON 和旧 fingerprint，可逆迁移并验证语义未丢失；
- hypothesis、expression structure、parameter variant 和 test stage 分别生成确定性 ID；
- 新增 append-only Search Ledger；现有 Trial 表继续作为 Inferential Trial Ledger；
- 纯文本且未使用实证反馈的提案可以只进入 Search Ledger；任何使用收益、标签、IC、回测或验证反馈的行为必须绑定 Trial；
- Replay Manifest 冻结代码、数据快照、V2 合同、reference library、配置、seed、双账本 ID 和完整 LLM/工具交互；
- V1.8.21 reference library 明确标记为 `research_only=true`、`validated_alpha=false`。

## 安全边界

Search Ledger 禁止 UPDATE/DELETE；Trial Ledger 禁止 DELETE，结果仍只允许写入一次。Replay audit 必须核对 Experiment→Snapshot、snapshot SHA-256、Search entry 和 Inferential Trial 的外键关系。M0 不读取封存窗口，也不生成新的 Alpha。
