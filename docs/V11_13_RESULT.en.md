# V11.13 Stability Attribution Test Report

## 结论 / Decision

No usable Alpha was found. Membership stability retains historical increment, but avoiding repeated weight maintenance adds only a small improvement. Both modes fail the complete economic screen because2023 is negative at doubled costs. Keep the frozen observation and optional new execution mode;no default promotion or certificate.

## 范围与定义 / Scope and definitions

484 sessions in reused2023–2024;continuous CNY3m adjusted fractional-share model accounts. Two frozen target schedules × two maintenance modes ×0/82/164bps produce12 accounts without fitting or new stock selection.82bps comprises6bps commission each side,10bps sell tax and30bps slippage each side;164 doubles every term. Zero cost is a path counterfactual only. Returns are relative to initial capital;the matched control is strict low-volatility under the same maintenance mode,not a market index.

|Policy|Maintenance|bps|2023|2024|Total|Sharpe|Max DD|Cost CNY|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|lowvol|full_target|0|7.0781%|28.7596%|37.8733%|1.2348|-10.4206%|0.00|
|lowvol|full_target|164|-7.2293%|11.5747%|3.5086%|0.1954|-23.1604%|836,499.11|
|lowvol|full_target|82|-0.3318%|19.8583%|19.4606%|0.7112|-15.4078%|449,182.39|
|lowvol|target_changes|0|6.9677%|29.0021%|37.9905%|1.2409|-10.3399%|0.00|
|lowvol|target_changes|164|-7.1871%|12.0044%|3.9545%|0.2107|-23.0736%|830,401.68|
|lowvol|target_changes|82|-0.3130%|20.5473%|20.1700%|0.7330|-15.3351%|442,402.02|
|stable_lowrisk|full_target|0|8.6974%|32.6854%|44.2256%|1.4034|-10.5645%|0.00|
|stable_lowrisk|full_target|164|-1.4452%|22.7071%|20.9337%|0.7560|-14.8276%|556,656.33|
|stable_lowrisk|full_target|82|3.5000%|27.5945%|32.0603%|1.0786|-12.6927%|291,282.73|
|stable_lowrisk|target_changes|0|8.6772%|32.8825%|44.4130%|1.4203|-10.4941%|0.00|
|stable_lowrisk|target_changes|164|-1.2170%|23.5281%|22.0248%|0.7910|-14.6943%|538,702.60|
|stable_lowrisk|target_changes|82|3.6284%|28.2936%|32.9486%|1.1098|-12.5879%|279,863.15|

## 小单减少不等于经济优势 / Fewer tickets are not sufficient

At82bps,stable executed tickets fall from8,001 to3,783 (52.72%),but cumulative absolute traded notional falls only3.91%. Return improves from32.0603% to32.9486%,a0.8883percentage-point gain. New-policy model profit is CNY988,458.00,final NAV CNY3,988,458.00;not brokerage-realizable performance. Tickets require absolute execution>1e-8CNY,unlike the priorV11.12 positive-ticket diagnostic.

## 成员稳定性与成本的拆分 / Membership and cost decomposition

Under legacy maintenance,the stable-minus-lowvol zero-cost increment is6.3523%,versus12.5998% at82bps. The6.2474percentage-point difference is attributable to the full cost-path contrast within this simulator,including compounding and funding scaling,not fee add-back. New maintenance retains approximately6.42pp zero-cost membership increment. The advantage is not entirely fee savings,but industry/size/risk exposure,membership-path luck and independent predictive information remain unresolved.

## 未通过的门槛 / Failed condition

At164bps,2023 returns are−1.4452% for original stable maintenance and−1.2170% for target_changes;2024 remains positive. The frozen both-years-positive condition fails. Do not discard2023 or relabel132bps as doubled82bps to pass. This is not failure of every previous stress or proof of permanent ineffectiveness;the current edge lacks robustness.

## 执行和统计边界 / Execution and inference limits

Maximum realized close weights are approximately3.05%–3.13%,above the declared2.5% target because of drift/constrained orders. Refresh-time trim requests are not an always-enforced cap. Raw lots,minimum commissions,physical share/dividend-payment/rights accounting and real opening liquidity remain unverified. Twelve related accounts are not twelve independent evidence sets;reused2023/2024 do not provide a new independent Court certificate. DSR/PBO/placebo are not certified in this run.

## 验证与复现 / Validation and reproducibility

15 new regressions pass;full suite843passed,1skipped in117.17s. Both legacy82bps accounts replay byte-identically. Independent SQL/Python checks reconcile12 accounts,NAV,cashflow,fees,marks,annual returns,Sharpe,drawdown,contrasts and SQLite unfitted contracts. Raw Trial lower bound3334. The auditor initially rejected a valid first-day08:00 inactive cash target;corrected to full timestamps before09:30 and reread saved evidence only,no market rerun or search.

## 后续方向 / Next direction

Do not tune cost or maintenance thresholds to repair the weak2023 year. Next test whether the search universe is too narrow:predeclare a finite mechanism-ranking experiment in as-of low/middle/high volatility groups using existing authorized frozen inputs,with same-group risk-matched controls and complete costs/budget. Keep old low-vol controls and evaluate the entire family,not the best observed risk group. Only surviving increments advance to CPCV,placebos and credible execution;independent windows retain their authorization protocol.

Method reference:[Bailey and López de Prado—Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551). Evidence:docs/V11_13_RESULT.summary.json;single-use operation;independent audit;Issue184 preregistration5560589655.

Native report schema QA recorded separately;visible/pixel QA deferred under quiet-until-usable instruction.

## V11.13.1 Post-run code review

An additional synthetic check exposed lost disposal intent when a missing exited stock was marked tozero and later recovered. Pending intent now survives the writeoff;recovery and capacity-constrained recovery have two added regressions. All12actual accounts have zero writeoff/recovery events,so this branch was not exercised. No market rerun or additional Trial occurred.

Reported returns remain bound to immutable pre-fix commit9bd9eaeaa8405272593227cb588ed6968d3d279d. Independent reconstruction of its Git source matches the original runtime hash;the patched code has a separate hash and tests. These figures are not relabeled as an empirical patched-code market run. SeeV11_13_1_CODE_REVISION.json.
