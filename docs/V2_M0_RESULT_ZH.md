# V2 M0 测试结果（中文）

## 结论

- **工程验收：通过。** V1 因子可无损迁移至 V2 契约，分层 ID、双账本和重放审计已贯通。
- **兼容性验收：通过。** 全量 191 项测试通过；原有 V1.0–V1.8.21 能力未被替换。
- **完整性验收：通过。** Search Ledger 和 Inferential Trial Ledger 均不可删除；Search Ledger 同时不可修改。
- **边界验收：通过。** 仅接触文本的搜索行为不消耗 inferential trial；一旦使用收益、标签、IC、回测或验证反馈，必须绑定已登记 Trial。
- **研究结论：M0 不产生 Alpha。** V1.8.21 组合仅作为 research-only reference，不能被标记为 validated alpha。

## 已验证能力

1. V1 FactorSchema 的完整 JSON 和旧 fingerprint 被嵌入 V2 契约，可反向恢复并检查语义一致性。
2. hypothesis、expression structure、parameter variant、test stage 使用相互独立且确定性的 ID。
3. Search Ledger 保存提案、派生和反馈暴露；Inferential Trial Ledger 继续保存统计检验尝试。
4. Replay Manifest 冻结数据快照、配置、代码版本、seed、reference library、双账本 ID、LLM 原始输入输出和工具调用。
5. Replay audit 核对 Experiment、Snapshot、SHA-256、Search entry 与 Trial 的关系，并报告封存窗口访问次数。

## 验证记录

- 定向测试：23 项通过。
- 全量测试：191 项通过。
- 静态检查：通过。
- Python 编译检查：通过。
- 2025 validation / 2026 final test：未打开。
- 新增实证 Trial：0。

## 下一步

进入 M1–M2：建立可执行 hypothesis graph、证据来源分级和 deterministic experiment compiler；编译器必须在运行前完成预算、反证、时间边界和 required controls 检查。
