# V11.12 执行可行性审计

## 结论 / Finding

冻结配置仍值得保留，但尚不能声明为可用 Alpha。真实数量审计暴露了小额再平衡订单的可执行性缺口；本轮没有新回测，也没有将旧收益改成所谓‘整手收益’。

## 范围与定义 / Scope and definitions

两条冻结的82bps账户，2023–2024共484个交易日，初始300万元。只检查已执行票据和上日实际持仓，不选择新股票、不调参数、不读取2025/2026。累计未分配金额=每笔原买入金额减按当日原价向下取整后的金额再求和；分母为累计买入金额，不是本金、净值、独立订单机会或收益。

## 买入数量诊断 / Buy-ticket quantities

稳定配置4,827笔买单中2,111笔（43.73%）不足最低数量；严格低波动为1,980/5,484（36.11%）。所有买单均匹配到原价和已覆盖的沪深规则，没有缺价或未知市场。数量少的订单不代表同等比例的收益损失；下表列出的是票据数量及金额诊断。

|Policy|Buys|Below minimum|Unallocated / buy notional|Extra commission CNY|Held factor changes|
|---|---:|---:|---:|---:|---:|
|lowvol|5,484|1,980|4.22%|23,739.13|415|
|stable_lowrisk|4,827|2,111|4.76%|26,998.52|352|

## 金额和最低佣金 / Notional and minimum commissions

稳定配置累计买入37,041,808.08元，逐笔舍入累计未分配1,764,248.10元（4.76%）；对照为4.22%。假设6bps佣金且每票最低5元，原始买卖票据需额外26,998.52/23,739.13元。5元未获用户券商确认；票据在真实整手账户中会变化，因此这些金额既不是收益损失估计，也不能直接扣减旧NAV。

## 公司行为复核范围 / Scoped event evidence

稳定配置上日持仓有352个复权因子变化键及35个原价缺失键；对照为415/35。两者合并去重为512个键、253只股票：477个变化键和35个缺价键。已生成私有逐项清单，无需先补全市场。因子变化只是线索，不能反推出分红、送转、配股和支付时间；无变化不等于无事件。缺价可能与停牌等有关，本轮不自行填补。

## 方法与质量验证 / Methods and QA

原始快照、候选卡、父账户先验SHA-256检查；2个无拟合原生Trial预占后才解析账户/源数值，累计债务3320→3322。独立SQL重算订单和佣金，逐笔核对10,311笔买单的数量上限、下限、最大可买数量及原价对账，重建持仓待核实键并核对SQLite。17项新增针对性测试通过，全套828 passed/1 skipped。报告数据只含汇总；源数据、个股清单和本机路径不入Git。

## 推断边界 / Inference limits

没有真实原股数账本、零股卖出、T+1库存、分红税和到账/送转/配股现金流，也没有真实开盘成交容量证明。当前库元数据有申万行业表，但未发现corporate/action名称表；不据此断言所有旧staging无资料。历史配置事后选中，旧32.06%仍仅为复权碎股模型收益；本轮未执行Alpha Court，不产生DSR/PBO或独立样本认证。

## 下一步 / Next actions

保持冻结卡。先用现有数据做有限的‘低波风格×持仓稳定性’匹配对照，区分少换仓收益与预测增量；不要重复5个已完成压力情景，也不要因暂缺全市场PIT而停止一切研究。并行的执行改进仅围绕上述清单和原股数/现金守恒，不能用因子变化伪造公司行为。任何改动后的交易政策另计Trial、另命名候选；认证还须独立窗口及完整Court，不以本轮工程测试代替。

Sources: [SSE STAR](https://edu.sse.com.cn/tib/), [SZSE 2023](https://investor.szse.cn/knowledge/qa/t20230306_599093.html), [SSE quantity notice](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/tz/c/c_20230209_5716007.shtml). Local: docs/V11_12_RESULT.summary.json; scripts/verify_execution_evidence.py; immutable execution-evidence operation.

Notebook QA: code cells replayed sequentially in Python; native Jupyter kernel/nbformat unavailable in both installed runtimes. Widget schema validation recorded separately; visible/pixel QA deferred under the user's quiet-until-usable instruction.
