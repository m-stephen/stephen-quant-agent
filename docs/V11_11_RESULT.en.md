# V11.11 Temporal Mechanisms and Allocation Stability

## Technical summary

All three new mechanisms fail: their full daily account bytes equal the stable low-risk control at all costs,with zero discretionary swaps and zero incremental signal return. The stable baseline returns32.06% (CNY961,809.35) at82bps,with2023+3.50%,2024+27.59%,Sharpe1.079 and−12.69% drawdown; at102bps it returns29.24%,both years positive. Its12.60pp advantage over strict low-vol belongs to allocation,not the new signals. Freeze it as a post-selection allocation observation,not validated Alpha.

## Scope and definitions

Reused development from2023-01-03 to2024-12-31,484sessions,one continuous CNY3m account. Return=final NAV/CNY3m−1;increment is a net total-return difference in percentage points, not CSI300 excess or annualized regression alpha.41/82/102bps denote nominal linear round-trip costs.

## All accounts

|Policy|bps|2023|2024|Total|Profit CNY|Δ low-vol pp|Δ stable pp|MDD|Sharpe|Fees CNY|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|竞价尾部 / Auction tail|102|2.26%|26.39%|29.24%|877,228.83|+13.90|+0.00|-13.20%|0.999|358,575.42|
|竞价尾部 / Auction tail|41|6.07%|30.11%|38.01%|1,140,186.63|+9.67|+0.00|-11.64%|1.241|149,052.82|
|竞价尾部 / Auction tail|82|3.50%|27.59%|32.06%|961,809.35|+12.60|+0.00|-12.69%|1.079|291,282.73|
|筹码路径 / Chip path|102|2.26%|26.39%|29.24%|877,228.83|+13.90|+0.00|-13.20%|0.999|358,575.42|
|筹码路径 / Chip path|41|6.07%|30.11%|38.01%|1,140,186.63|+9.67|+0.00|-11.64%|1.241|149,052.82|
|筹码路径 / Chip path|82|3.50%|27.59%|32.06%|961,809.35|+12.60|+0.00|-12.69%|1.079|291,282.73|
|资金流持续性 / Flow consistency|102|2.26%|26.39%|29.24%|877,228.83|+13.90|+0.00|-13.20%|0.999|358,575.42|
|资金流持续性 / Flow consistency|41|6.07%|30.11%|38.01%|1,140,186.63|+9.67|+0.00|-11.64%|1.241|149,052.82|
|资金流持续性 / Flow consistency|82|3.50%|27.59%|32.06%|961,809.35|+12.60|+0.00|-12.69%|1.079|291,282.73|
|严格低波动 / Strict low-vol|102|-2.07%|17.78%|15.35%|460,363.84|+0.00|-13.90|-17.08%|0.584|549,236.89|
|严格低波动 / Strict low-vol|41|3.31%|24.23%|28.34%|850,073.57|+0.00|-9.67|-11.86%|0.972|232,925.47|
|严格低波动 / Strict low-vol|82|-0.33%|19.86%|19.46%|583,816.76|+0.00|-12.60|-15.41%|0.711|449,182.39|
|稳定低风险 / Stable low-risk|102|2.26%|26.39%|29.24%|877,228.83|+13.90|+0.00|-13.20%|0.999|358,575.42|
|稳定低风险 / Stable low-risk|41|6.07%|30.11%|38.01%|1,140,186.63|+9.67|+0.00|-11.64%|1.241|149,052.82|
|稳定低风险 / Stable low-risk|82|3.50%|27.59%|32.06%|961,809.35|+12.60|+0.00|-12.69%|1.079|291,282.73|

## Predicted edges versus costs

Pair bound = 2 × abs(slope) × (1 + sum(abs(nuisance rank coefficients))). Ranks lie in[-1,1]; the intercept cancels.

|Fit year|Mechanism|Upper pair edge bps|Hurdle bps|Swaps|
|---|---|---:|---:|---:|
|2023|auction_tail_balance|41.59|122|0|
|2023|chip_path_efficiency|60.25|122|0|
|2023|flow_consistency|26.98|122|0|
|2024|auction_tail_balance|3.38|122|0|
|2024|chip_path_efficiency|23.23|122|0|
|2024|flow_consistency|71.30|122|0|

## Methods

Twenty consecutive common-coverage sessions define signed flow consistency,auction cubic tail balance and chip-width path efficiency. Missing observations reset windows;only true zero denominators map to zero. Chip width is the85th–15th cost quantile spread,not concentration height. Research occurs within the200 lowest current20-session-volatility names. Each stable cohort retains40 incumbents while eligible, filling vacancies by low-vol rank;strict low-vol usesTop40/buffer10. Four fixed phases0/5/10/15 feed one netted account. Prefix-only expanding annual fits use mature20-session labels,5-session embargo, risk-rank residualization,ridge0.01 and122bps discretionary hurdle. Exit prices remain available; the existing5%ADV proxy capacity and open restrictions are unchanged.

## Verification and limitations

809 passed,1 skipped; Ruff PASS. Independent SQL/NAV/cash/positions/order fees,21 SQLite Trials,24 model bindings and all target hashes PASS.

Zero nonzero active paths make PBO/DSR NOT_IDENTIFIABLE;placebo p=1. No statistical PASS is manufactured. Native lineage binds21 fit/account contracts and24 model-evidence records;raw historical Trial lower bound3310 includes failed/unused reservations. The7997/17596 stock samples represent only40/88 signal dates with overlapping training prefixes.2025/2026 were not read. Selection of the stable allocation also incurs multiple-search bias;turnover and risk exposures may explain its return. Full market/industry/size attribution, independent forward evidence and raw shares/lots/minimum fees/corporate actions/open liquidity certification are absent. Adjusted fractional shares and ADV proxies limit live-trading interpretation. The loader verified and read frozen minute inputs,but this mechanism did not use minute features.

## Next steps and open questions

Do not lower the hurdle or Court gates,or sweep these parameters. Freeze the stable and strict-lowvol target sequences,then preregister matched higher-cost,execution-delay and quarter-capacity challenges. Separate fee savings from holdings performance and diagnose low-vol exposure and dependence on exceptional days,without trading or tuning on those diagnostics. Archive a failed lead before a new bounded mechanism; a survivor still needs independent evidence and full Court. Discovery is not guaranteed.

Sources: V11_11_RESULT.summary.json; scripts/audit_temporal_epoch.py; immutable local RESULT, INDEPENDENT_AUDIT, NATIVE_FIT_LINEAGE and PREDICTION_DIAGNOSTIC.

Machine field increment_hash_pp is a legacy label for the stable_lowrisk comparison here; it is NOT a hash-stock benchmark.
