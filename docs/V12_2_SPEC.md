# V12.2 — Frozen signal / portfolio-construction bridge

Issue: #204. Implementation specification approved by the independent reviewer.
This document does not authorize an empirical launch or a main merge.

## Engineering checkpoint / 工程进度

Core allocation, four-native-account backend and independent source/score/target/
saved-account audit components are implemented. Component commit423edce passed
the full regression (1,765 passed,2 skipped) and GitHub CI34162422776.
The subsequent complete synthetic backend-to-audit suite passed5 tests in140.23s:
726 fictional weekday sessions,23 inherited native identities,14 actual model
files,28 cost bindings,and4 new accounts. No numerical guard was replaced by a
mock PASS. The first run's test-only uppercase DSR key failure is preserved;
the corrected test uses the existing lowercase statistical keys,not new thresholds.
The once-only launcher,final integrated regression/CI,frozen launch plan and
reviewer launch approval remain required. This is not an empirical Alpha result.

已完成纯分配、四账户原生预留/后端及独立来源/评分/目标/已存账户审计构件，
构件提交423edce完整回归1,765通过、2跳过，CI34162422776通过。新增完整四账户
端到端合成测试5项通过（140.23秒），实际经过726个虚构工作日、23个继承原生身份、
14份模型、28个成本绑定及独立来源/评分/目标/完整账户审计。首轮测试字段名大小写
错误已保留记录并修正，未改生产统计或门槛。一次性启动器、最终集成回归/CI、
冻结计划和审查Agent启动批准仍待完成。未运行市场账户，真实尝试下界仍3733。

## 中文

目标：检验冻结的流价响应信号在更稳定的持仓构造中是否仍有净增量；
不增加公式、模型拟合、超参数或数据供应商。

- 使用 V11.21 的 response/risk 年度模型及已核验历史缓存；原八字段
  共同支持集、原模型评分，不重新排序归一化字段，不再拟合。
- 2023–2024 已揭示开发窗，2022仅作原模型训练与历史缓存来源；不访问2025/2026。
- 前日评分、20交易日维护、相位0/5/10/15；global40/top60：原持仓仍在
  top60内优先保留，按评分补足40；并列按股票代码升序。相位锚点跨年不重置。
- 每相位单股2.5%，四相位平均；300万连续账户。原 target_changes、
  前日ADV5%容量、stale20恢复规则和82/164bps成本不变。
- 仅四个新账户：global_response/global_risk ×82/164；一次性预算4，
  原生占用先于数值读取；历史尝试下界3733→3737，失败仍计数，fits=0。
- 唯一主要比较 global_response − global_risk；旧分层response/risk及
  全局lowvol/hash八账户只读作解释，不重跑、不以事后最佳账户改换基准。
- 报告分年及全段双成本净收益、Sharpe、回撤、配对日均与累计差、人民币
  增量、实际费用和换手、20分组实际持仓暴露、成员变更；成员变更不等于换手。
- 相同支持集不等于风险中性。HAC仅描述性；历史DSR/PBO/placebo在不可识别
  时为null；最高 COMPLETE_DIAGNOSTIC_AUDITED，不能宣布可用Alpha或覆盖旧FAIL。

实现/CI/完整测试通过、精确来源/代码/预算计划冻结、独立审查批准以后，
才允许一次真实运行。原始来源→模型评分→目标→完整账户需独立核验。
不通过则保留证据，与审查Agent讨论下一版；不能反复重跑本诊断直到通过。

## English

Question: does the frozen flow/price response signal deliver net incremental value
under less disruptive holdings? No additional formulas, fits, hyperparameters or sources.
Reuse the original annual response/risk models, immutable eight-field common support,
and raw model scores. No extra cross-market normalization or support selection.

Use only revealed 2023–2024 development execution (2022 historical training input),
never 2025/2026. Prior-session decisions,20-session maintenance,phases0/5/10/15,
global40/top60 retention and ascending instrument tie-break; no year reset.
Each sleeve targets2.5% per name and sleeves are averaged. CNY3m, original
target_changes execution,prior-ADV5% capacity,stale20 recovery and82/164bps costs.

Exactly four new native accounts, reserved before numerical reads; prior empirical
attempt lower bound3733 becomes3737 even on failure. Zero new fits. Primary comparison
is global_response minus global_risk. Eight saved grouped/global controls are read-only
explanatory evidence, never rerun or selected post hoc as a new primary comparator.

Report both years and the full continuous account, both costs, net return/Sharpe/MDD,
paired mean/cumulative percentage-point/CNY increments,actual fees/notional/turnover,
20-cell actual exposures and membership churn. Common support does not imply risk
neutrality; membership churn does not measure actual traded turnover. HAC is descriptive;
unidentifiable historical DSR/PBO/placebo remain null. Highest possible status is
COMPLETE_DIAGNOSTIC_AUDITED, not usable Alpha or replacement of old failed verdicts.

Empirical launch requires frozen source/code/budget plan, full tests and CI, then
independent reviewer approval. Independently reconcile source,model scores,targets
and complete account. No automatic retry, main merge, trading or data purchases.
