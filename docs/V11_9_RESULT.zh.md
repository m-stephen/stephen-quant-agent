# V11.9 调仓日历稳健性测试

## 结论

完成72个连续账户；固定四批策略稳健性幸存数1，已验证可用Alpha仍为0。

2023–2024 已暴露历史研究；单次300万元、覆盖匹配低波动/hash对照。增量为两个总收益率相减（百分点），不是信息比率或对沪深300的超额。

## 双倍成本：所有预定日历

|Candidate / 候选|Calendar / 日历|2023|2024|Total / 总收益|Profit / 盈利元|Low-vol / 对照|Increment / 增量pp|MDD|Sharpe|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|blend_concentration_+1_h20|annual_calendar|0.90%|34.60%|35.82%|1,074,487.25|27.22%|+8.60|-16.82%|1.090|
|blend_late_30_return_-1_h20|annual_calendar|3.53%|28.88%|33.42%|1,002,607.94|27.22%|+6.20|-14.45%|0.966|
|blend_concentration_+1_h20|phase_0|0.90%|30.36%|31.54%|946,102.24|26.21%|+5.32|-16.72%|0.964|
|blend_late_30_return_-1_h20|phase_0|3.53%|9.86%|13.73%|411,873.56|29.54%|-15.81|-25.95%|0.470|
|blend_concentration_+1_h20|phase_10|1.29%|17.53%|19.05%|571,501.25|15.91%|+3.14|-14.41%|0.635|
|blend_late_30_return_-1_h20|phase_10|1.03%|-6.14%|-5.17%|-155,012.60|15.80%|-20.97|-27.78%|-0.069|
|blend_concentration_+1_h20|phase_15|1.78%|19.90%|22.04%|661,161.07|24.76%|-2.72|-13.98%|0.720|
|blend_late_30_return_-1_h20|phase_15|-5.20%|8.91%|3.25%|97,430.95|24.51%|-21.26|-27.90%|0.182|
|blend_concentration_+1_h20|phase_5|1.53%|26.10%|28.03%|840,913.08|17.13%|+10.90|-16.40%|0.890|
|blend_late_30_return_-1_h20|phase_5|1.47%|5.82%|7.38%|221,294.41|16.87%|-9.50|-27.68%|0.294|
|blend_concentration_+1_h20|staggered_four|1.29%|23.92%|25.51%|765,386.29|20.09%|+5.42|-15.31%|0.825|
|blend_late_30_return_-1_h20|staggered_four|0.06%|3.98%|4.05%|121,432.55|20.68%|-16.63|-27.50%|0.206|

## 年度重置差异分解

|Candidate|Annual reset linked|Continuous annual calendar|Continuous phase0|Account reset pp|Calendar pp|
|---|---:|---:|---:|---:|---:|
|blend_concentration_+1_h20|34.88%|35.82%|31.54%|-0.94|+4.28|
|blend_late_30_return_-1_h20|32.85%|33.42%|13.73%|-0.57|+19.69|

差分按预定顺序可加总，但不是唯一因果归因。四批策略是目标权重合成的同一账户，不是事后收益平均。

## 门禁与局限

- blend_concentration_+1_h20: failed checks=none
- blend_late_30_return_-1_h20: failed checks=annual_increment, continuous_drawdown, hash_increment, lowvol_increment, sharpe, three_of_four_phases, worst_phase_floor

PBO diagnostic=0.65; DSR and all details in the adjacent machine-readable summary. Family placebo={'block_sessions': 20, 'exchangeability': 'assumption_not_independent_confirmation', 'null': 'common_block_sign_symmetry_of_active_returns', 'p_value': 0.655, 'repetitions': 199, 'winner': 'blend_concentration_+1_h20:phase_5'}. These are current-family diagnostics, NOT full-history calibrated confidence.

复权碎股、线性费用和ADV容量仍是近似；尚缺真实手数/最低佣金/公司行为/实际开盘容量和完整风格独立验证。没有门槛降低，也没有解封2025/2026。

## 核验与下一步

Independent SQL, daily cash/positions/NAV, annual compounding, gate decisions and72 SQLite trials passed. Maximum residual9.31e-10 CNY. Raw trial lower bound3256; restricted rows read=0.

若固定四批策略幸存，冻结后进入真实成交及风格审计；否则记录时点/换手/信号不足，预声明下一种机制，禁止挑选本轮最佳相位。待解问题是机制增量而非回测收益本身；已见历史不重新命名为独立验证。
