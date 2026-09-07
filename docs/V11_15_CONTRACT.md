# V11.15 信号时点诊断 / Signal timing diagnostic

Issue184 preregistration: https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5561063399

Three V11.14 mechanisms and two matched controls plus cell-equal-weight, three
risk strata, five fixed return intervals: **90 no-fit diagnostics**, debt3366→3456.
No actual trading account in this epoch. Existing V11.11 card and all older
results remain frozen. Development2023–2024 is reused,not independent OOS.
The same five-source frozen snapshot is used;2022warmup,no2025/2026.

复用全量当时合格股票和原风险格；每日每格取前10名，每股固定2.5%，无buffer。
等权对照每格25%，稀疏格保留现金。当前成员先确定，然后才查询未来端点。
Use unchanged formulas/directions,not posthoc sign flips. Missing future prices
never change membership,weights or maturity dates. All intervals share t+21
calendar maturity. Cross-year events are grouped by signal year,not NAV year.

|Label|Endpoints|Interpretation / 含义|
|---|---|---|
|before_entry|close(t)→open(t+1)|Before entry,not capturable / 入场前|
|same_day|open(t+1)→close(t+1)|Diagnostic only,T+1 restriction / 不能新买当日卖|
|open_1|open(t+1)→open(t+2)|Earliest T+1-compatible interval / 最早T+1|
|open_5|open(t+1)→open(t+6)|Five global sessions / 五日|
|open_20|open(t+1)→open(t+21)|Twenty global sessions / 二十日|

Primary gross contribution uses fixed unit-notional denominator;missing price
contribution0,missing weight disclosed. Complete-price conditional mean is
separate and can be selection-biased. Stress scenario for open horizons:
unbuyable/missing entry cash0;entered but missing/unsellable endpoint loss100%.
This is not a realistic forced liquidation,net strategy or account return.
No compounded wealth,Sharpe,independent stock-event count,DSR/PBO/Court claims.
复权端点仍不是真实现金分红或整手成交证明，压力情景不等于实际清算。

Strong-response reason for a separately preregistered execution study requires
both signal years:mean gross>1.64%,increment>=0.30pp over EACH hash/reversal/EW,
price coverage>=99%,entry>=98%,positive stress mean. It is not a universal
necessary alpha condition,especially for low-turnover buffered strategies.
正式Alpha门槛不变；毛收益或重叠标签不可能直接提供可用Alpha结论。

Primary trading-rule context: [SSE trading rules,3.1.4](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml).
Rule reference supports no sale before settlement except designated turnaround
products;the diagnostic does not assume newly purchased A-shares can roundtrip
the same day. No trading authorization is created.

## Validation and reporting / 验证和报告

Synthetic planted timing,missing endpoints,asof membership,global maturity,
fixed denominators,native contract,budget;independent DuckDB from raw endpoint
and weight evidence versus Python date/annual aggregates. Bilingual Markdown,
JSON and native report. No raw identities or local source paths in Git.
Chart contract: grouped bars,5 discrete intervals ×3mechanisms,per risk stratum,
2023/2024 annual summaries retained;fractional gross diagnostic,not NAV.
Zero baseline,visible mechanism legend,neutral context;native report schema QA.
Visible/pixel QA deferred under user quiet-until-usable instruction.
