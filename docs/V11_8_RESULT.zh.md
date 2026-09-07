# V11.8 候选深挖测试报告

## 结论

完成66个账户窗口。可用Alpha仍为0；全部压力情景幸存数：0。
下一动作 / Next action: `PREREGISTER_NEXT_BOUNDED_MECHANISM_EPOCH`。

## 口径 / Scope

2023、2024分别以300万元初始化；连续账户只初始化一次。所有收益均扣模型成本。基准为同字段覆盖、同持有期、同40只股票预算的低波动对照，不是沪深300。历史已被用于选因子，不能作为独立验证。

## 年度压力检验 / Annual execution stresses

筹码宽度 / Chip width = (cost85-cost15)/weighted_cost; higher does not mean more concentrated chips.

| Candidate | Scenario | Year | Net | Profit CNY | Low-vol | Increment pp | Cost CNY |
|---|---|---|---:|---:|---:|---:|---:|
|blend_concentration_+1_h20|baseline_82|2023|0.90%|27,149.63|1.02%|-0.12|204,751.94|
|blend_concentration_+1_h20|baseline_82|2024|33.67%|1,010,097.45|25.10%|+8.57|208,185.61|
|blend_late_30_return_-1_h20|baseline_82|2023|3.53%|105,770.94|1.02%|+2.50|300,948.49|
|blend_late_30_return_-1_h20|baseline_82|2024|28.33%|849,890.51|25.10%|+3.23|306,392.10|
|blend_concentration_+1_h20|cost_102|2023|-0.65%|-19,542.15|-0.78%|+0.13|252,978.86|
|blend_concentration_+1_h20|cost_102|2024|31.69%|950,814.90|22.93%|+8.76|257,217.37|
|blend_late_30_return_-1_h20|cost_102|2023|1.15%|34,525.04|-0.78%|+1.93|370,341.44|
|blend_late_30_return_-1_h20|cost_102|2024|25.45%|763,467.40|22.93%|+2.51|376,987.92|
|blend_concentration_+1_h20|cost_132|2023|-2.94%|-88,166.32|-3.42%|+0.48|323,850.50|
|blend_concentration_+1_h20|cost_132|2024|28.79%|863,590.85|19.76%|+9.02|329,274.63|
|blend_late_30_return_-1_h20|cost_132|2023|-2.31%|-69,267.53|-3.42%|+1.11|471,378.65|
|blend_late_30_return_-1_h20|cost_132|2024|21.25%|637,447.45|19.76%|+1.48|479,740.97|
|blend_concentration_+1_h20|delay_one|2023|1.07%|31,998.85|2.24%|-1.17|188,902.41|
|blend_concentration_+1_h20|delay_one|2024|31.88%|956,451.45|25.17%|+6.71|186,770.08|
|blend_late_30_return_-1_h20|delay_one|2023|4.95%|148,613.01|2.24%|+2.72|275,566.70|
|blend_late_30_return_-1_h20|delay_one|2024|26.70%|801,087.15|25.17%|+1.53|276,759.48|
|blend_concentration_+1_h20|quarter_capacity|2023|0.90%|27,149.63|1.02%|-0.12|204,751.94|
|blend_concentration_+1_h20|quarter_capacity|2024|33.67%|1,010,097.45|25.10%|+8.57|208,185.61|
|blend_late_30_return_-1_h20|quarter_capacity|2023|3.53%|105,770.94|1.02%|+2.50|300,948.49|
|blend_late_30_return_-1_h20|quarter_capacity|2024|28.33%|849,890.51|25.10%|+3.23|306,392.10|

## 连续账户 / Continuous capital

- blend_concentration_+1_h20: net 31.54%; profit CNY946,102.24; low-vol 26.21%; increment +5.32pp; MDD -16.72%.
- blend_late_30_return_-1_h20: net 13.73%; profit CNY411,873.56; low-vol 29.54%; increment -15.81pp; MDD -25.95%.

## 风格与极端日诊断 / Style and tail diagnostics

- blend_concentration_+1_h20 2023: low-vol beta 0.994, R² 0.833, annualized intercept -0.03%, descriptive HAC95 [-9.25%, 9.20%]. Top5 positive-active days set equal to control: increment -3.21pp.
- blend_concentration_+1_h20 2024: low-vol beta 1.021, R² 0.878, annualized intercept 6.69%, descriptive HAC95 [-8.38%, 21.77%]. Top5 positive-active days set equal to control: increment -1.02pp.
- blend_late_30_return_-1_h20 2023: low-vol beta 1.075, R² 0.781, annualized intercept 2.66%, descriptive HAC95 [-9.32%, 14.63%]. Top5 positive-active days set equal to control: increment -2.34pp.
- blend_late_30_return_-1_h20 2024: low-vol beta 1.049, R² 0.809, annualized intercept 2.02%, descriptive HAC95 [-12.23%, 16.27%]. Top5 positive-active days set equal to control: increment -9.96pp.

这些回归未做事后选择校正，区间不能当作正式Alpha推断。极端日替换是假设诊断，不能据此设计可交易删日策略。

## 验证 / Verification

- 66 accounts independently reconcile; max cash/position/NAV residual CNY4.66e-10.
- Independent DuckDB net/NAV/cost/drawdown aggregation matches every saved account.
- New trials 30; cumulative raw lower bound 3088;12 exact baseline replays have zero trial delta.
- Parent/frozen evidence unchanged; no2025/2026 reads.

## 局限与后续 / Limitations and next work

本轮属于复权分数股研究账户，未实现原始股数、交易手数、最低佣金、完整公司行为与开盘流动性核验。因此不能声称可实盘。压力失败不等于证明因子永远无效：冻结保留其证据，后续检验更匹配机制的期限、降低换手的方法，但任何修改均另计Trial。当前仍缺完整统计校准和独立验证，不能宣布Alpha Court PASS。

## 待回答 / Open question

信号能否在低换手、真实可成交且非样本反复筛选的条件下保留增量收益？
