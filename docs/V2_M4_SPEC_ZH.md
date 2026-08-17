# V2 M4：结构化失败与冻结 Research Epoch

## 目标

失败不再只存在于报告文本中，而是成为 SQLite 中 typed node、edge 和 event。它们与 epoch、family、candidate、stage 和 reason code 绑定，全部 append-only。

## Epoch 纪律

- epoch 开始时冻结 policy hash，以及 family/candidate/compute/token/statistical budgets；
- epoch 内中间结果只能追加失败和事件，不能修改 policy；
- 只有当前 epoch 已关闭，才能创建下一 epoch；
- 下一 epoch 的动作限定为 Explore、Exploit、Mutate、Recombine 或 STOP_FAMILY；
- 达到 exhaustion threshold 的 family 下一 epoch 预算必须为 0。

## 决策映射

重复、成本过高或无边际价值触发单维 Mutate；多种失败并存可触发 Recombine；CPCV/placebo 失败要求 Explore 新机制；数据未准备好或 family 耗尽触发 STOP_FAMILY；没有失败时才 Exploit。每个决策保存来源 failure node IDs 和 reason code。

## 验收

相同冻结失败图必须产生相同下一 epoch 预算和动作；开放 epoch 禁止更新 policy；failure/history/decision 的 UPDATE 或 DELETE 必须失败。
