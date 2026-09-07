# V11.21: Frozen Response Empirical Results

## Reproducibility passed; both new candidates failed

One preregistered 22-account continuation and its separate audit completed on7 September2026.
**No new usable Alpha was found.** Both response and response_interaction failed the frozen screen.
Engineering tests and numerical auditing are not economic, statistical or brokerage certification.

The study uses existing frozen daily/fund-flow sources, training from2022 and repeatedly reused2023–2024 development history.
Each account starts with CNY3m, runs continuously for484 sessions and does not reset capital at year-end.
Returns below are cumulative net returns, not CAGR. Sharpe uses daily sample standard deviation,252-session annualization and zero risk-free rate.

| Policy | Roundtrip bps | Net total return | Sharpe | Maximum drawdown | 2023 | 2024 |
|---|---:|---:|---:|---:|---:|---:|
| response |82|−22.55%|−0.293|−48.01%|−10.33%|−13.63%|
| response |164|−37.07%|−0.647|−56.22%|−18.67%|−22.62%|
| response_interaction |82|−24.04%|−0.327|−48.52%|−9.85%|−15.75%|
| response_interaction |164|−37.69%|−0.666|−56.25%|−18.19%|−23.84%|
| original_stable, existing uncertified control |82|+32.04%|1.078|−12.69%|+3.50%|+27.58%|
| original_stable, existing uncertified control |164|+20.92%|0.756|−14.83%|−1.45%|+22.69%|

The complete bilingual report retains all22 accounts under ignored
`artifacts/flow-response/report-b24/report.zh.html`, `report.en.html`, `RESULT.zh.md` and `RESULT.en.md`.
Exact machine-readable values are in the same directory's `summary.json`; no raw market data or individual holdings are committed.
HTML data, packaging, embedded payload and semantic fallback structure passed verification. No compatible headless-shell was available;
enhanced-reader interaction and chart visual QA were not run.

## A construction concern, not a newly discovered Alpha

Excluding each of four sleeves' first entry leaves93 continuing sleeve refreshes.
Response replaces39.27of40 names on average(98.17%); interaction98.23%, stratified lowvol95.75%, and fixed hash28.95%.
This is membership replacement, not traded-notional turnover. Four40-name sleeves combine into one account whose positions may exceed40.

Stratified lowvol selects within every volatility cell and is not a global low-volatility portfolio.
Original anchors and generated policies also differ in target construction/execution mode.
The return gap therefore cannot be attributed exclusively to flow features, fees or the model.
Response's cumulative increment over matched risk is only+0.39percentage points at standard costs and−0.50points at double costs.
Do not manufacture a recovery by adding back costs, reversing the failed signal post hoc, or changing thresholds.

## Evidence and limits

- Actual cumulative Trial lower bound: **3729 =3707+22**. This archive adds no empirical Trial;14 inherited models were not refitted.
- Terminal `COMPLETE_EXPLORATORY_AUDITED`: backend696.55s and separate audit1736.06s, both normal exits.
- Peak private memory:8,983,871,488 /8,987,328,512bytes, each below10GiB.
- Sources, features, mature labels, models, targets and all accounts independently audited; cumulative/annual returns,P&L,Sharpe and drawdown independently aggregated again for all22 accounts.
- SQL and Python independently reconcile replacement summaries for all9 generated policies, without new models/accounts.
- Runtime commit `89ecd36e1f3fff2c9493a3a599eb139397c064aa` [CI34129101817](https://github.com/m-stephen/stephen-quant-agent/actions/runs/34129101817): all three required groups1569passed/2skipped;JUnit/Ruff passed.
- Earlier native SIGSEGV evidence remains; its root cause has not been proven permanently fixed.
- DSR/PBO/placebo **NOT_RUN**; both primary screens FAIL;`validated_alpha=false`.
- Reused development is not fresh OOS. Board lots, minimum commissions,raw prices and corporate-action cash lack full brokerage certification. No2025–2026 tuning reads.

Actual preregistration: [Issue184 comment5572026627](https://github.com/m-stephen/stephen-quant-agent/issues/184#issuecomment-5572026627).

| Evidence | SHA-256 |
|---|---|
| Canonical plan |85005460b6e3d6128cf7e3a1ea9ebfb09fc6f59b78ae8ac458d71a22f3e03c9f|
| RESULT |42967cab1f0463974244a3a3393678be558a33924377f3369825fb43e9b0432c|
| AUDIT |0846c919950f1aae395b692897349c21274d12d7cf63b8b270ff82b716c7467f|
| ASSESSMENT |f948d68cf807f2870f791e6db6917e527e762af95f9eacd00ff8eb6be957e27b|
| Native database |8be3d9bbcc5e4fb9536afe4034c7dab3a0fdd6ecadee27c9f867ab2524c13baa|
| Independent summary |500544a24af6f4886e12b473afc3044008bf9aad60f7b7d813a033d48c948e89|

## Next work started; no new empirical account launched

`portfolio_construction.py` adds a fixed four-account diagnostic contract and a pure selector,with22 passing synthetic tests.
Compare global lowvol/hash selection on the same audited support against completed stratified controls:
40names/top60 retention,four phases,20sessions and unchanged costs/capacity. No fit,buffer grid or relabeling diagnostic controls as Alpha candidates.

Next implement completed-evidence binding,full reservation,targets/accounts/independent audit and a one-shot runner.
Only after tests and exact code/evidence preregistration may four real accounts run.
**Actual debt remains3729;3733 is only the projected count after future reservation.**
The diagnostic changes risk allocation and trade maintenance jointly;do not claim single-variable causality.
PR remains Draft;no main merge,relaxed Court thresholds or live trades.
