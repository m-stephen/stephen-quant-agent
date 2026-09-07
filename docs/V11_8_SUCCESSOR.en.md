# V11.8 Lower-Turnover Mechanism Test

## 结论 / Technical summary

Historical economic leads: 0; validated Alpha: zero. NO_LEAD_CONTINUE_RESEARCH.

Eight signals times two directions, ranked inside the bottom30% volatility cohort;60-session holding, Top40/buffer10. All16 candidates are retained;2023/2024 remain exposed historical development.

## 双倍成本结果 / Doubled-cost results

| Candidate | 2023 net | 2024 net | Pooled Sharpe | Linked increment vs low-vol pp | Economic lead |
|---|---:|---:|---:|---:|---|
|conditional_ret_20_-1_h60|7.42%|1.24%|0.298|-30.54|False|
|conditional_ret_20_+1_h60|-4.90%|-0.49%|-0.051|-44.66|False|
|conditional_liquidity_-1_h60|21.05%|-1.06%|0.469|-19.51|False|
|conditional_liquidity_+1_h60|-6.89%|28.35%|0.654|-19.78|False|
|conditional_net_inflow_ratio_-1_h60|0.81%|10.39%|0.377|-28.01|False|
|conditional_net_inflow_ratio_+1_h60|5.50%|6.71%|0.440|-26.72|False|
|conditional_concentration_-1_h60|9.19%|-8.88%|0.105|-39.79|False|
|conditional_concentration_+1_h60|-1.74%|12.20%|0.380|-29.04|False|
|conditional_late_30_return_-1_h60|9.76%|5.32%|0.456|-23.69|False|
|conditional_late_30_return_+1_h60|5.90%|0.12%|0.249|-33.26|False|
|conditional_realized_volatility_-1_h60|7.37%|16.33%|0.752|-14.39|False|
|conditional_realized_volatility_+1_h60|2.55%|-0.13%|0.166|-36.88|False|
|conditional_amihud_intraday_-1_h60|-8.96%|27.49%|0.564|-23.23|False|
|conditional_amihud_intraday_+1_h60|8.52%|7.84%|0.449|-22.26|False|
|conditional_auction_return_-1_h60|20.75%|3.13%|0.642|-14.76|False|
|conditional_auction_return_+1_h60|5.74%|-2.62%|0.182|-36.33|False|

## 口径、统计与限制 / Definitions and statistical limits

Each year independently starts CNY3m;82bps modeled round trip. Linked annual-reset increment is not a continuous account. Any lead needs continuous-capital, brokerage-realism and independent validation.

```json
{
  "statistics": {
    "daily_observations": 484,
    "dsr": 0.016301195168819893,
    "dsr_assumption": "current-family Sharpe dispersion extrapolated to all raw trials; not a calibrated full-history DSR",
    "dsr_benchmark_daily_sharpe": 0.07605209869226993,
    "dsr_raw_trial_count": 3184,
    "dsr_status": "RAW_COUNT_SENSITIVITY_HISTORICAL_SHARPE_MATRIX_UNAVAILABLE",
    "dsr_trial_sharpe_estimates": 16,
    "effective_observations": 484,
    "empirical_excess_kurtosis": 5.5777669587832595,
    "empirical_skewness": -0.5292744700217844,
    "pbo": 0.55,
    "pbo_status": "DIAGNOSTIC",
    "selector": "mean daily net active return, lower daily volatility, canonical ID",
    "winner": "cab1c4328999c2f68a1a12e3fe6d33a328485d0f2fd2d28ccfe4c70440187078"
  },
  "placebo": {
    "block_sessions": 60,
    "exchangeability": "assumption_not_independent_confirmation",
    "null": "common_block_sign_symmetry_of_active_returns",
    "p_value": 0.995,
    "repetitions": 199,
    "winner": "cab1c4328999c2f68a1a12e3fe6d33a328485d0f2fd2d28ccfe4c70440187078"
  }
}
```

CPCV purges the60-session holding horizon and retains embargo. DSR remains a raw-count sensitivity extrapolating current-family dispersion, not calibrated full-history confidence. No thresholds were relaxed; no Alpha Court PASS.

## 账本与核验 / Ledger and verification

- 96 new trials; cumulative raw lower bound 3184.
- 192 independently reconciled accounts; maximum NAV residual CNY4.66e-10.
- All account hashes and SQL/Python return, cost and drawdown comparisons match.
- Existing candidate/parent evidence unchanged; no2025/2026 access.

## 后续 / Next step

Inspect the complete family and its failure mechanism, then preregister the next bounded step. Keep frozen leads and count every amendment. Prioritize continuous-capital and horizon/execution mechanisms; more formulas are not independent evidence.
