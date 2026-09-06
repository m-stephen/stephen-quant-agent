# V11.10 Residual Mechanism Test Report

## Technical summary

Six fits and15 continuous accounts reconcile independently;zero new historical leads andzero validated Alpha. The old staggered-chip observation remains frozen. No thresholds are reduced.

## Scope and definitions

Reused2023–2024 development,484sessions,one continuous CNY3m model account. Return=final NAV/CNY3m-1;increment is a total-return difference in percentage points,not CSI300 excess. Common field coverage,next-open execution,41/82/102bps linear round-trip costs.

## All account results

|Policy / 政策|bps|2023|2024|Total / 总收益|Profit CNY / 盈利元|Δ lowvol pp|Δ hash pp|MDD|Sharpe|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|auction_late_disagreement|102|-2.81%|-3.40%|-6.11%|-183,190.18|-22.10|+0.00|-38.76%|0.029|
|auction_late_disagreement|41|-0.50%|-1.02%|-1.52%|-45,564.54|-30.47|+0.00|-37.59%|0.115|
|auction_late_disagreement|82|-2.05%|-2.63%|-4.62%|-138,619.24|-24.72|+0.00|-38.38%|0.057|
|chip_reversal|102|0.15%|-2.89%|-2.74%|-82,217.23|-18.73|+3.37|-36.05%|0.086|
|chip_reversal|41|3.91%|-0.51%|3.38%|101,460.36|-25.57|+4.90|-33.86%|0.200|
|chip_reversal|82|1.37%|-2.11%|-0.77%|-23,055.70|-20.86|+3.85|-35.34%|0.124|
|flow_reversal|102|-2.81%|-3.40%|-6.11%|-183,190.18|-22.10|+0.00|-38.76%|0.029|
|flow_reversal|41|-0.50%|-1.02%|-1.52%|-45,564.54|-30.47|+0.00|-37.59%|0.115|
|flow_reversal|82|-2.05%|-2.63%|-4.62%|-138,619.24|-24.72|+0.00|-38.38%|0.057|
|lowvol|102|-2.10%|18.48%|15.99%|479,664.76|+0.00|+22.10|-17.06%|0.607|
|lowvol|41|3.28%|24.86%|28.95%|868,454.51|+0.00|+30.47|-11.91%|0.995|
|lowvol|82|-0.36%|20.53%|20.10%|602,863.00|+0.00|+24.72|-15.41%|0.734|
|risk_hash|102|-2.81%|-3.40%|-6.11%|-183,190.18|-22.10|+0.00|-38.76%|0.029|
|risk_hash|41|-0.50%|-1.02%|-1.52%|-45,564.54|-30.47|+0.00|-37.59%|0.115|
|risk_hash|82|-2.05%|-2.63%|-4.62%|-138,619.24|-24.72|+0.00|-38.38%|0.057|

## The hurdle exposes weak predicted edges

Flow and auction policies are byte-identical to the stratified hash across all costs,not three independent effective strategies. Chip return is-0.77% at82bps,with+3.85pp vs hash but-20.86pp vs low-vol and-35.34% drawdown. Beating one weak control does not establish Alpha.

|Fit year|Mechanism|Max pair edge bound bps|Hurdle bps|Replacements|
|---|---|---:|---:|---:|
|2023|auction_late_disagreement|45.69|122|0|
|2023|chip_reversal|265.78|122|543|
|2023|flow_reversal|14.29|122|0|
|2024|auction_late_disagreement|25.21|122|0|
|2024|chip_reversal|104.98|122|0|
|2024|flow_reversal|6.09|122|0|

The pairwise upper bound is2×|slope|×(1+sum absolute three nuisance-rank coefficients),because ranks/interactions lie in[-1,1] and intercept cancels. This is a diagnostic proof,not an ex-post trading rule. Only the2023 chip model can cross the hurdle;all543 discretionary replacements occur there.

## Methodology and verification

Training-only residualization,yearly expanding fits,mature20-session labels plus5-session embargo,common-coverage5×4 risk cells,fixed four-cohort netted accounts.2023fit187,052rows/44signal dates;2024fit410,745rows/92dates. Many stock rows are not independent time observations. Missing entries excluded49/83;missing exits conservatively-100% at220/360,with overlapping historical prefixes.

Twelve new tests pass;full suite783passed,1skipped;Ruff passes. All15 accounts independently reconcile SQL NAV/cost/drawdown,cash/positions,order fee rates,annual compounding,target dates/hashes,21SQLite reservations and screening decisions.

## Statistical and interpretation limits

Legacy static registry training columns still say2022 and cannot alone represent the2024 expanding fit. The original ledger is not rewritten: append-only `V11_10_FIT_LINEAGE.json` binds all21trials to actual yearly model cutoffs and artifact hashes. Fit-timing audits must use this supplement plus models,not the old scalar columns. No account returns change. A successor must natively record multi-stage fit lineage.

PBO diagnostic=0.65;DSR sensitivity=0.2303059565579566;family placebo=0.27. Raw trial lower bound3289.

Two candidate active paths are the same zero series,leaving one nonzero incremental direction. PBO/DSR are not usable Court certification. CPCV only diagnoses adaptive-return selection,without nested model refits;full historical Sharpe matrix is unavailable. No fresh OOS or brokerage execution certification.

## Next steps and open questions

Keep the old observation;do not repeat these weak interactions or lower the hurdle. Next bounded work should separate the stratified base allocation from factor information,testing incremental mechanisms within a fixed low-risk baseline after synthetic executable-signal calibration. Preregister new trials first. The question is whether incremental information clears costs,not whether a wider universe or more parameters guarantees Alpha. Independent evidence and credible execution remain necessary.
