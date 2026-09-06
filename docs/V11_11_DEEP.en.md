# V11.11 Frozen Allocation: Stress Report

## 结论 / Technical summary

The frozen stable low-risk allocation survives all five stress scenarios and ten matched accounts. It remains a historical allocation observation,not usable Alpha;the three new signals still add zero. At132bps,2023profit is only0.43%,a thin cushion.

## 范围与定义 / Scope and definitions

Reused2023–2024 history,484sessions,one CNY3m model account. Increment is the total-return difference versus the same-scenario strict low-vol control,not CSI300 excess. Targets are immutable with no refitting:low-risk200pool,40names per cohort,four fixed phases.

## 全部压力结果 / Complete stress findings

82/102/132bps,quarter ADV capacity and one extra session delay all satisfy positive returns in both years,Sharpe≥0.7,drawdown≥−25%,total increment≥3pp and annual increment≥−5pp. Quarter-capacity returns equal baseline:the proxy constraint did not change realized fills here;this does not prove real opening liquidity.

|Scenario|Policy|bps|2023|2024|Total|Profit CNY|Δ low-vol pp|MDD|Sharpe|Fees CNY|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|baseline_82|lowvol|82|-0.33%|19.86%|19.46%|583,816.76|+0.00|-15.41%|0.711|449,182.39|
|baseline_82|stable_lowrisk|82|3.50%|27.59%|32.06%|961,809.35|+12.60|-12.69%|1.079|291,282.73|
|cost_102|lowvol|102|-2.07%|17.78%|15.35%|460,363.84|+0.00|-17.08%|0.584|549,236.89|
|cost_102|stable_lowrisk|102|2.26%|26.39%|29.24%|877,228.83|+13.90|-13.20%|0.999|358,575.42|
|cost_132|lowvol|132|-4.62%|14.74%|9.44%|283,153.16|+0.00|-20.01%|0.395|692,648.71|
|cost_132|stable_lowrisk|132|0.43%|24.59%|25.13%|753,795.76|+15.69|-13.98%|0.881|456,659.61|
|quarter_capacity|lowvol|82|-0.33%|19.86%|19.46%|583,816.76|+0.00|-15.41%|0.711|449,182.39|
|quarter_capacity|stable_lowrisk|82|3.50%|27.59%|32.06%|961,809.35|+12.60|-12.69%|1.079|291,282.73|
|delay_one|lowvol|82|0.02%|17.38%|17.39%|521,820.32|+0.00|-16.26%|0.652|447,087.25|
|delay_one|stable_lowrisk|82|3.60%|25.72%|30.25%|907,365.22|+12.85|-12.72%|1.033|290,211.08|

## 增量来源与风险暴露 / Increment and risk exposure

At82bps,net P&L exceeds strict low-vol by CNY377,992.59,with CNY157,899.66 lower actual fees. Subtracting these is accounting,not a zero-fee counterfactual or pure factor return. Low-vol beta=0.9835,R²=0.9819;nominal annualized intercept=5.38%,lag20 HAC interval=[3.03%,7.72%]. Neither selection correction nor industry/size/market controls are applied. Replacing the five best active days with control returns leaves9.04pp increment;a nontradable descriptive diagnostic.

## 方法与独立验证 / Methods and independent checks

Ten explicit unfitted native contracts precede source reads;raw Trial debt3310→3320,retaining failures and unused reservations.82/102accounts replay parent bytes exactly. Audit verifies frozen target+declared delay,chronology,weights,NAV/cash/positions,returns,order fees,recorded capacity,annual compounding,SQL drawdown and all ten SQLite results. Full suite811passed/1skipped;Ruff passes.

## 不能越过的结论边界 / Limits on inference

This is not fresh OOS or full-history DSR/PBO,signal/return/universe placebo or independent forward Court. One post-selected allocation cannot support identifiable strategy-selection PBO. Accounting PASS does not certify raw shares/lots/minimum fees/corporate events,real open liquidity or deployability.2025/2026,old leads and main remain untouched.

## 下一步与待解问题 / Next steps and open questions

Keep the policy frozen;do not beautify history by tuning200pool/40positions/calendar. Next bounded work inventories raw-price/adjustment/corporate-action and executable-share evidence,identifies a defensible lot/fee replay,then specifies fixed style/benchmark falsification and available independent windows. Report genuinely missing evidence instead of asserting usability. New mechanism work requires new reservations;never replay this claim or call cost scenarios independent Alpha.

Sources: docs/V11_11_DEEP.summary.json; scripts/audit_stability_challenge.py; immutable RESULT/INDEPENDENT_AUDIT/accounts/targets/native ledger.
