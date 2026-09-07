# V11.21 B17：冻结账户根因复验

## 决策与边界

B16 提交 b041460 的 CI 34114709041 已成功。本次只验证已失败 plan003 的 risk-82 账户，不重训、不换目标、不用部分账户选赢家。合成测试证明审计的非零微小成交处理有缺陷，但尚未确认真实失败的唯一原因。

独立一次性操作：版本 11.21-risk-account-diagnostic-1。同一 Git common-dir 固定 claim；换工作树或输出路径不能自动重试。新增 1 个原生、无新拟合的冻结目标回放 Trial。账本继承 3660 + 失败002的23 + 失败003的23 = 3706；新 claim 实际消费后才为3707。失败也保留预算、原生状态和终态证据。

## 输入及执行

- 只读取 plan003 的 history/history.json、targets/risk.json 和原生血缘；旧文件、数据库、23个失败尝试均不修改。
- 预先 hash 验证旧失败清单的37个文件、两批失败 claim/terminal、父实验、旧审计源码和实际执行代码。其他账户报告仅验证字节，不解码收益。
- 使用原3e9fd0d审计的真实 Git bytes。AST 核验只允许 abs(notional)>1e-12 改为 notional!=0。执行器、会话转换和账户配置文件须与旧运行字节相同。
- 完整计划绑定当前 clean commit、全部 src、两个驱动、Python和包版本、资源限制、确切输入SHA、用途和新原生账户契约。Issue184 真实评论必须包含独立一行的计划SHA；固定 GitHub API 核验后才占用 claim 和预留 Trial，再读取金融数值。
- 历史缓存2022–2024；执行2023–2024；300万元、82bps、target_changes，原容量、时间、停牌、限价、核销规则不变。2025/2026、新来源、重新选股、重新生成目标、重新拟合均禁止。
- 一个自有隐藏子进程，private10GiB、可用RAM至少4GiB、4小时、0.2秒采样；无自动重试。轮询保护不是OS硬资源隔离。

## 诊断验收

1. 重建账户一次，先独占保存完整 UNVERIFIED_ACCOUNT，再运行两个审计。
2. 原审计必须复现 held-name set differs from fill reconstruction。保存原异常栈帧的首个分歧日期、身份、股数、成交值与当日开盘价。
3. 首次出现的名称集合差异必须能由当日被旧审计忽略的微小非零成交完全解释；修复后必须通过全账户订单、现金、股数、NAV等审计。所有小额成交逐项保存在本机结果。
4. 若原异常未复现、首次差异不能解释，或新审计还有异常，则 UNRESOLVED。不修改epsilon、不反复回放、不启动完整研究轮次。
5. engineering_pass 仅是账户根因证据，不是因子有效性、源数据重建/选股独立审计或 Alpha Court。原审计在首个异常处停止，不能声称比较了其后所有旧审计状态。

## 使用与证据

入口 scripts/diagnose_flow_response_account.py 有 prepare、run、child 三个子命令。prepare 只绑定元数据和原始字节SHA，不消费 Trial；run 需要实际预登记评论ID。child 是受监管阶段，不是跳过 run 的授权入口。所有输出位于 gitignored artifacts/flow-response/account-diagnostics。

当前文档是执行契约，不是实际诊断结论。新代码测试、实际commit/CI、完整计划评论和最终诊断结果另行留档；未消费 claim 前，不宣称真实诊断已经执行。
