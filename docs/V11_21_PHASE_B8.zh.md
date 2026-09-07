# V11.21 B8：一次性实证入口

## 作用与当前证据

新增 `scripts/run_flow_response.py` 和 `flow_response_launch.py`，把既有数值后端接入固定来源、固定预算和可续接的运行流程。没有新增因子参数、成本档位、年份或晋级捷径。

当前证据是工程门禁和合成测试，不是新的市场收益或 Alpha 认证。完整测试计数、哈希及真实预登记/运行状态以 `V11_21_VERIFICATION.md` 和 `V11_21_CONTINUATION.md` 的最新记录为准。

## 三步流程

1. **Prepare。** 要求干净、已提交的当前工作树；绑定实际代码字节（包括独立审计器和入口脚本）、commit、Python 可执行文件和 NumPy/DuckDB 版本。验证固定 V11.20 RESULT/AUDIT、审计绑定的原生 registry、继承血缘和十二项父实验结果。验证原 V11.4 manifest、日 K/资金流两文件和原 V11.11 锚点目标字节。只投影日 K 的日期列形成 2022–2024 日历，不解码目标权重或读取行情数值列。
2. **预登记和一次性占用。** GitHub API 固定查询 Issue #184 的实际评论，校验评论身份、所属 issue、带时区的时间和完整计划 SHA-256 标记。原始评论与实际读取时间入档；不接受调用方注入的授权 callback。全局 claim 位置从真实 `git-common-dir` 得到，以父结果/版本为键，换工作树或计划输出目录不能重复本轮。占用后一次性登记完整 23 项 native Trial，全部检查成功才允许数值计算。
3. **生产与审计。** 两个独立的受监督 Python 子进程顺序运行。必须收到生产进程正常退出和资源采样证据，冻结其 RESULT/registry 哈希后才启动审计。审计数据库使用 SQLite `mode=ro` 和 `query_only`，不创建 schema、不写旧结果。追加 `AUDIT.json` 与 `ASSESSMENT.json`；原 RESULT 继续保留 pending-audit 状态，不改写历史。

这是一套单用户可重现性流程，不是新的多用户权限体系。全局 claim 限于同一共享 Git 仓库；不声称可以阻止用户故意复制整个仓库、删除记录或修改代码。

## 冻结资源与失败语义

每个子进程固定私有提交内存上限 10 GiB、可用物理内存下限 4 GiB、最长四小时、每 0.2 秒采样。在首次实证读取前固定这些值。四小时是工程停止边界，不是性能保证；两个阶段不能同时运行，也不是各四小时的实际耗时预测。

资源不足的启动前检查失败不产生 claim 或 Trial。全局占用后，完整尝试预算 23 不再消失；即使原生预留只完成部分，终态也分别记录承诺预算和实际 native 数量，无法查询时为 null 并注明错误类型，不伪称完整预留。完整预留前不读取行情数值。

内存/时间保护、进程失败、审计失败和中断均保留 claim、账本与终态；不隐性重试。出现失败必须解释原因并另行进行有限预登记，而不是删掉 claim。轮询不是 OS 硬限制，只控制自己持有句柄的单个子进程，不宣称后代进程树控制或全流程内存已认证。

## 测试覆盖与边界

新门禁测试用合成父账本和只有日期列可用的 Parquet：其他三个源文件故意不存在，目标文件故意不是可解码 JSON，证明 prepare 只使用获准文件/日期/原字节哈希。覆盖原证据变更、缺控制、代码变更、非法预算、资源拒绝、预登记归属/时间/摘要、全部 23 预留、部分预留失败、跨工作树重复占用、只读数据库拒写、被篡改的子进程启动证据，以及真实临时 Git worktree 的共同 claim 路径。

编排测试中的数值后端与审计用 stub 检查先后顺序，**不是新的全流程数值或统计功效测试**。既有完整合成 epoch 的独立数值审计改用真正只读连接，验证 RESULT/registry 字节不变。B7 的真实 Windows 子进程采样测试继续运行。最终完整测试证据见 VERIFICATION。

## CI 更正

B7 仅把 YAML 作业时限从 20 改为 40 分钟，没有解决取消：run 34086974315 于 05:29:05Z 开始、05:44:17Z 取消，测试到约 73%。官方文档确认 `ubuntu-slim` 有 **15 分钟 runner 硬限制**，因此之前把原因归为可配置的 20 分钟 job 时限不准确。

本轮通过 GitHub 连接器和主机网络 CLI 均确认仓库仍为 public，改用标准 `ubuntu-24.04` 并保留全部测试和 40 分钟作业上限。它不是付费 larger runner；标准 runner 在公开仓库免费。未来改为 private 后应重新检查免费分钟和计费，不把当前免费条件永久化。[GitHub 官方文档](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

## 使用与下一步

在已提交且干净的专用工作树中运行：

```powershell
python scripts/run_flow_response.py prepare --output artifacts/flow-response/launch-plan-001.json
```

将完整研究契约和生成的计划摘要实际评论至 Issue #184，独立确认 CI 与预检通过后才执行：

```powershell
python scripts/run_flow_response.py run --plan artifacts/flow-response/launch-plan-001.json --preregistration-comment ACTUAL_COMMENT_ID
```

第二条示例中的占位符必须替换为真实评论数字。不手动执行内部 `backend`/`audit` 命令，不删除 claim 续跑。

计划仍仅含 2022–2024 原日 K/资金流，2 个主候选、每成本 9 个控制、82/164 bps、300 万资金、14 个实际年度模型和 28 条成本消费绑定。真实全局占用承诺 23 次尝试后，下界从 3660 更新为 3683；部分原生预留失败也保留承诺预算，实际 native 数量单列。测试临时库中的 3683 不计入实证债务。完整探索幸存者也只能进入进一步证伪，不能自动通过 Alpha Court、获得新 OOS 身份或实盘部署。
