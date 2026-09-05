# V11.2 最终测试结果

实现依据：[Issue #175](https://github.com/m-stephen/stephen-quant-agent/issues/175)  
冻结实现提交：`1c16f476a925e45ab48e60a7be346ad9ff676c3b`  
规范版本：`11.2.0`  
规范 hash：`09d5e702580c534c425581a24e06592df908d5fb1cb6610d85e4cef40517dd68`

## 工程验收

- 完整测试：`671 passed, 1 skipped`；
- Ruff：通过；
- `git diff --check`：通过；
- V11.2 新增针对性测试：`21 passed`；
- 原冻结协议语义 hash：`71ba4f198f2f3dcbc4877d684f5a5fd8023d806a469e2d2a482ead4174a77106`；
- 原冻结协议字节 hash：`bd05436613e94f4333383f66f68c1c6fa22f0703041fabbe23d5b3282deb546c`；
- 真实运行 content hash：`405a2f688c5e63bd43b98b2cdceec74c4f1fd742c7333abc8c4220545409bc33`；
- 真实运行 envelope hash：`84160012ea26cfe837857f2cf542f9e04a17ee8a7a437ecc493e9c97ea773d7c`。

对抗测试覆盖状态回写、协议/证据篡改、pre-genesis、回填、延迟到达、修订链、重复、覆盖、不同 source watermark、双层日历、Day 25/126/252、标签接口拒绝、正交域硬门槛、原子写入中断、重复 operation 和确定性重放。

## 真实运行结果

| 项目 | 结果 |
|---|---|
| Candidate Nursery | `CANDIDATE_NURSERY_READY` |
| 可信观察时钟 | `ESTABLISHED` |
| Family actionable dates | `0` |
| Forward stage | `ACTIONABLE_DATES_INSUFFICIENT` |
| Orthogonal domain | `ORTHOGONAL_DATA_NOT_READY` |
| Raw global Trials | `770` |
| 新增 inferential Trials | `0` |
| 未授权封存标签读取 | `0` |

Nursery 迁移了两条且仅两条已有前向候选、一个规格依赖的 V11 线索，以及 V11.1 全部 15 条拒绝证据。没有翻转方向、生成近邻或建立第三份协议。

可信时钟从本次受控运行开始。此前本地文件只能用于覆盖和 QA，不能追认成当时可交易的 first-seen 证据。由于目前没有 freeze boundary 之后、且在 T+1 decision cutoff 前由该时钟首次观察到的完整 daily/minute/chip 共同日期，0 个 actionable dates 是正确结果。

## 正交数据审计

1. 公告与预期差：已有公告发布时间与修订元数据，但没有 point-in-time 一致预期和 actual value，缺少 `actual_value`、`expected_value`，未通过硬门槛。
2. 股份供给/公司行动：现有源页尚未形成稳定 ID、完整去重、PIT/revision 契约和确定性全量 replay，未通过硬门槛。
3. 行业内相对机制：申万二级历史数据可重放且覆盖较高，但当前资格仍为 `PIT_LITE`、`formal_research_eligible=false`，未被伪装成正式 PIT。

## 研究结论

V11.2 完成的是可信研究运行能力，而不是 Alpha 发现。当前没有新增 Alpha，也没有任何候选获得实盘授权。下一次有效进展来自可信时钟之后真实的新数据，或某个正交数据域补齐硬门槛后另建预注册研究；不能使用旧文件回填，也不能恢复无界历史搜索。
