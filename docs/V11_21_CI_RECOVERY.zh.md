# V11.21：CI 超时诊断恢复

## 结论与边界

2026 年 9 月 7 日，run 34089011614 / job 101638545074 已取消。主机网络 REST 的检查注释明确记录：作业超过配置的 40 分钟上限。作业从 06:01:09Z 至 06:46:10Z，包括终止阶段。这不是 B7 的 ubuntu-slim 15 分钟硬上限；本次 runner 标签确实是 ubuntu-24.04。

连接器下载日志返回 BlobNotFound，CLI 也返回 log not found，因此目前不能确定哪个测试或依赖导致运行缓慢。没有把本机 1399 passed、2 skipped 当作远端通过。没有启动实证实验、占用 claim 或新增 Trial；累计下界仍为 3660。

## 本次修改

- 保留全部测试与断言，不添加筛选、跳过、自动重试或 continue-on-error。
- 输出逐项测试名称、前 25 项耗时、120 秒挂起堆栈和 JUnit；标准输出同时保存到日志文件。
- 测试步骤最多 45 分钟，作业最多 60 分钟，为失败后的日志上传留出时间。上传失败或 runner 丢失仍可能导致日志不可用，不能保证任何故障都可归档。
- 仅在 CI 中将 BLAS/OpenMP 线程数限定为 1，避免潜在的嵌套并行竞争。它是控制变量，不是已经证明的超时根因；不改变本机实证子进程的资源契约。
- 仅上传 CI 自身生成的合成测试日志、运行库信息和 JUnit，保留 7 天；不上传任何本机行情、配置、实验数据库或秘密。

NumPy 官方说明 BLAS 后端可能使用多个线程，并可通过后端相关的环境变量控制。[NumPy 文档](https://numpy.org/doc/stable/reference/global_state.html)
GitHub 支持步骤级超时和测试产物归档。[工作流语法](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[产物上传](https://github.com/actions/upload-artifact)

## 计划与后续

本次仅修改 CI 和说明文档，不修改数值代码、测试、研究契约或现有证据。旧 launch-plan-001.json 绑定提交 ff7421b，必须原样保留，不能用于新提交。先核验新提交 CI；通过后另存 launch-plan-002.json，并在 Issue #184 发布完整的新计划哈希预登记，明确替代旧评论的待执行计划，而不是重试已经消费的实验。本轮至今没有实证消费。

若新 CI 仍失败，读取新日志和堆栈定位具体问题，不继续盲目增加超时，也不以本机通过绕过远端门禁。这个检查点没有新的市场收益、统计功效或 Alpha 结论。
