# V11.4–V11.6: reliable research and the first bounded discovery comparison

Issue #180; package version11.6.0. The release repairs shared semantics, executes one mechanism comparison and introduces prefix-trained baseline models plus a structured proposal interface. It does not deliver unbounded autonomous discovery or deployable Alpha.

## Frozen experiment

-24 predefined predictors, two cost settings:48 new trials. Preserve2770 historical raw trials as a lower bound.
-2022 trains the ridge/stump baselines only;2023 selects;2024 is contaminated diagnostic evaluation.2022–2026 was historically exposed; this run excludes2025–2026 return labels.
-Each annual account starts independently with CNY3m. Do not add independent-window returns as one continuous account.
-Decision-time universe:at least20 observations, trailing up-to60-session ADV>=CNY10m, excluding contemporaneous ST flags. No Top800 truncation, future exit-price filter or unrelated-field completeness filter.
-Signals at close execute next-session open. Auction inputs lag a session.5/10/20-session rebalance, Top40, ten-rank buffer based on previous targets; rejected orders remain unfilled. Coverage and liquidity strata are recorded.
-41bps round trip:3bps commission and15bps slippage each way plus5bps sell tax;82bps stress case. Capacity:5% of prior-observable ADV.
-Shared daily stateful execution retains missing positions and applies a conservative20-session writeoff with recovery. Adjusted prices and fractional shares approximate execution, not precise board-lot or corporate-action accounting.
-Benchmark:equal-weight same-day matched field-availability universe with identical execution/costs, not CSI300. Benchmarks differ across dependencies; this is not proof of market-neutral Alpha.

## Statistics

Report daily account and benchmark returns separately, absolute profit, percentage-point excess and relative-wealth ratio. Never compound active returns and label them account returns.

2023 selection uses20 actual purged CPCV splits (six groups,three test groups), a20-session conservative overlap envelope andfive-calendar-day embargo. The same mean-active-return/lower-volatility/canonical-ID selector applies inside and outside each fold. Predictors remain frozen from the earlier2022 prefix. This is selector CV, not per-CPCV-fold model retraining or20 independent backtest paths.

PBO uses each training winner's relative test rank; unidentifiable repeated rankings return null. Daily DSR uses empirical skewness/kurtosis and conservative autocorrelation-adjusted sample size. However, the aligned historical Sharpe matrix is unavailable:extrapolating current-family dispersion to the raw historical trial count is a sensitivity analysis, not calibrated full-history confidence. Clustering never erases raw trials. The0.95 threshold is unchanged. See [the original DSR paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

Family placebo reselects the winner under199 common20-session block-sign draws. Its validity depends on approximate block-sign symmetry; it is not independent confirmation.

## Calibration, stopping and reproducibility

Before real labels:24 planted and100 null cases through actual scores, Top40, costs, execution, first-place selection and placebo. Actual1/8-worker execution must be deterministic. Recovery and economic detection>=75%; null95% Wilson upper bound<=5%. DSR/PBO are additionally computed on every path. Economic detection power must not be advertised as full Alpha Court power. This audit covers a fixed four-formula family, not the real24-candidate family or unbounded adaptive search.

Failed calibration stops before real labels. Preserve failures and seeds; do not retune and recycle an audit. After a successful audit, exactly one frozen historical epoch runs without new candidates, winner changes or threshold changes.

Copy `configs/reliable-research.example.json` to a gitignored `*.local.json` and configure local directories. Run:

```text
python -m stephen_quant.workflows.v114_reliable_epoch --calibrate artifacts/reliable-research/calibration-001
stephen-quant reliable-research --config configs/reliable-research.local.json
python -m stephen_quant.workflows.v114_reliable_epoch --replay artifacts/reliable-research/epoch-001
```

Evidence includes frozen specifications/models, pre-read reservations, bounded read-only Parquet extracts and hashes, SQLite trials, daily account JSONL, coverage, correlations/actual holdings overlap, split manifests and bilingual reports. Raw data stays out of Git. Exact replay requires identical code/identities/inputs and appends a replay operation with zero new inferential trials.

Source-query ranges and returned dates are measured; this does not assert that DuckDB never touched other row groups. Hash comparison protects only configured frozen artifacts. Access sealing never erases historical exposure.

Structured LLM proposals require a mechanism, falsifier, field/operator whitelist, horizon and parent. Screening records duplicate/budget/validation rejections. External LLM calls in this epoch:zero. Free-form adaptive generation and deployment are explicitly not implemented by this first comparison.
