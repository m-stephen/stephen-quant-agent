# V11.20 verification / 验证证据

## Completed engineering, not Alpha certification

Runtime `7fc9ff06762cca5c107229c45a9362c4732c540e`; Issue184 preregistration [5562959810](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5562959810). Exactly12 native no-new-fit replays completed;24 immutable paid accounts independently checked. Inherited16models/32nativefits; no optimizer or prediction run. Trial lower bound **3660 = 3648 + 12**. Prior failed operations and targets preserved.

- New37 targeted synthetic tests PASS, including altered targets/clocks, invalid output/claims, inherited-lineage tampering, source-open/share reconciliation, no-promotion/scope/debt contracts and planted non-additive cash compounding.
- Full suite before version update: **1057 passed,1 skipped,186.66s**.
- Final suite after11.20.0 version update: **1057 passed,1 skipped,189.73s**; RuffPASS. Subsequent report-only text/default-sort changes passed Ruff and executed builders; market/audit runtime unchanged.
- Independent audit: all36accounts,24cost drags,42control increments; **131,099 new zero-fee +306,194 inherited paid opening-fill records** reconciled in source-adjusted fractional units. Zero source capacity or current-close mismatches. Maximum cash/NAV residual **4.656612873077393e-10 CNY**.
- RESULT SHA-256: `04dbbf1224bd50016d33d30cec145ffbbdefa0649a118c215bd1110d846f83fe`.
- INDEPENDENT_AUDIT SHA-256: `43808b722f9c0c30ccd09b24b4ef8b2b5fe0e733bafa005aeab444d958cedba5`.
- Snapshot unchanged: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`. No2025/26 reads.
- Two language reports,36 aggregate rows,24drag rows,42increment rows. Native report schemaPASS:4datasets/1source. Visible/pixel QA **DEFERRED_USER_QUIET_INSTRUCTION**; no rendered-image claim.
- Notebook contains4 executed ordinary-Python cells, independently recomputing all36 saved-account SQL aggregates. Checked nbformat/nbclient/ipykernel absent; Jupyter frontend/kernel QA **NOT_RUN**, not a passed Jupyter execution.
- Runtime CI status recorded in PR198; final report commit must receive its own successful CI before Ready. No automatic main merge.

## Diagnostic result

Zero-fee full models: linear+4.5677%,quadratic−1.2020%; same-basis risk controls+21.6998%/+13.6557%. Both models trail their risk controls in both years even without fees. Gross relative deficits:−17.1321pp/−14.8577pp. Costs substantially worsen returns but are not the only weakness. Original standard/double-cost failures remain failures; zero-cost old stable44.2256% is an old counterfactual control,not a new discovery.

All rates cover repeatedly reused2023–2024 development,not independentOOS or market benchmark excess. Validated Alpha remains0; DSR/PBO/placeboNOT_RUN/null. Retain82/164bps and all Court gates. This evidence supports redesigning information representation/mechanism,not claiming market Alpha is impossible or solely blaming missing data.
