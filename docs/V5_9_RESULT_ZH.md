# V5.9 测试结果：预算感知搜索控制器

状态：`READY_FOR_PORTFOLIO_AWARE_SEARCH`

在没有注入伪造历史表现的基线规划中，七个机制族均从未尝试状态开始。控制器选择：

- Action：`EXPLORE`
- Family：`price`
- Batch：16
- 最大增量 Trial：20
- 保留 Trial：32/256
- 控制器自身 Trial 增量：0

价格族首先被选中是因为其预期评估成本最低，不代表价格因子已经有效。对抗测试确认了
验证期/最终测试反馈被拒绝、重复失败触发 REPAIR、达到保留线或机制耗尽时 STOP。
