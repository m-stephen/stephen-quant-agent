# V11.21 phase B2: frozen input reader and mature-label predictor

## Decision and scope

A testable two-source reader and finite supervised predictor are implemented. **They are not yet an integrated empirical runner and do not authorize a market epoch or establish Alpha.** New market numeric reads0, empirical Trials0, debt3660 unchanged. No2025/2026 reads, frozen-target changes or main merge; PR199 remains Draft.

Input tests use synthetic Parquet in pytest temporary directories. Learning tests use fixed synthetic samples/seeds. No V11.19/V11.20 operation was repeated. Phase-B1 head7efb838c2652544f0efe78934fd0e436e71b5de2/CI34071068619 was verified successful.

## Components

`qmt/flow_response_inputs.py` validates the frozen manifest and only the daily/flow files: path, SHA-256, row count, date coverage and duplicate keys. Only2022–2024 numeric columns are projected. The other three sources remain manifest metadata; their files are neither checked nor opened. The passing fixture deliberately omits auction, chip and minute files.2021 warmup values are not projected. The explicit calendar must equal daily date coverage; inputs containing2025+ partitions fail before numeric projection.

This reader is not an authorization entry point. The future runner must freeze its parameters/budget, reserve native Trials and verify preregistration before calling it. It has not been called on real frozen inputs.

`discovery/flow_response_predictor.py` separates past contemporaneous response features from future-return training. All seven forms consume the same current names with all eight finite fields. Names are grouped into5 volatility by4 liquidity bins, with centered within-cell ranks; grouping/pairing do not inspect outcomes.

| Form | Inputs beyond three risk fields | Parameters |
|---|---|---:|
| response | standardized flow, price-response residual | 5 |
| response_interaction | response inputs and their rank product | 6 |
| risk | none | 3 |
| raw_flow_return | raw net-flow ratio, own daily return | 5 |
| standardized_flow_return | standardized flow and own return | 5 |
| old_absorption | negative flow-rank times20-day-return-rank | 4 |
| shuffle | interaction inputs with fixed within-training-cell label rotation | 6 |

Risk fields arevolatility_20,ret_20,liquidity. The old-absorption control recomputes the old formula on matched support/cells; it is not an exact replay of the original portfolio. One fixed shuffle is not a placebo p-value. These finite forms are fixed in code, but do not constitute the full empirical account/cost/source budget.

Training uses2022 for2023 and2022–2023 for2024, excluding the last five global prefix sessions. Next-open to20-session-exit-open labels must mature by that cutoff. Sampling stride is5; each actual training date has equal total weight; at least30 actual dates are required. Within each cell, a fixed hash picks at most64 names for adjacent disjoint pairs. Missing entry excludes the pair; a missing endpoint uses the parent's historical close-mark convention, not future-survival filtering. Overlapping labels remain dependent; pair counts are not independent sample sizes.

Fixed ridge0.01 weighted least squares estimates relative gross returns, with an independent normal-equation residual check. Scores are not executable net-return forecasts or causal effects. No portfolio turnover, costs or capacity results exist yet.

`fit_and_bind_predictor` checks shared-source bindings and predeclared year/policy before reading samples. It rejects existing fits, completed Trials and existing outputs, writes the model exclusively, then registers native fit evidence. `guarded_predict` checks source digests, actual model bytes and the prediction period before current-row access. Pure numerical helpers do not replace these runtime guards.

## Synthetic verification and remaining work

The combined targeted suite passed138 tests, including existing B1/fit/packet coverage;33 tests are new. See VERIFICATION for the final full regression and machine artifacts.

Coverage includes two-source-only access, manifest/hash/key/date failures, common support and seven vector widths, maturity filtering before numeric access, label horizon/stride/cell/duplicate-leg errors, prefix-only label creation, missing endpoint marking, independent row-wise normal equations, native pre-fit gates, policy mismatch, duplicate fitting and file mutation.

For the fixed planted interaction, independent synthetic test MSE is below one quarter of both the standardized-flow/own-return and risk control MSEs. Zero labels yield zero coefficients. A fixed independent random-null test has absolute prediction correlation below0.1. These passing assertions test implementation capability, not market performance, statistical significance, Alpha discovery or a false-positive-rate estimate.

Still required: integrated source bytes→historical response bundles→as-of feature verification/cache; daily risk/liquidity/eligibility and account-bar bridge; full fixed targets and original anchors; actual canonical packet wiring; all Trial/control/cost budgets; independent source/model/label/target/NAV audit; full preregistration. The native predictor fixture verifies a declared synthetic provider relationship, not that arbitrary supplied matrices derive from actual response bundles. The integrated runner must establish that missing link.

The analysis-validation workflow keeps engineering correctness, empirical increment and usable-Alpha certification distinct. With no new market findings, this phase produces no return charts or Alpha report.
