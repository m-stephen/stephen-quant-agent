# V11.8 低换手机制测试

## 结论 / Technical summary

Historical economic leads: 0; validated Alpha: zero. NO_LEAD_CONTINUE_RESEARCH.

8类信号×双方向，在低波动30%股票内排序，持有60交易日，Top40/10档缓冲；下表完整保留16个候选，不只展示最好的结果。2023/2024仍为已暴露历史开发样本。

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

各年独立300万元，双倍成本82bps往返；复合增量是年度重置账户的链接，不是连续资金。若有经济线索，必须再检验连续账户、真实成交及独立证据。

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

CPCV按60日持有期purge并保留embargo；DSR仍仅为当前家族离散度外推全历史Trial数的敏感性，不是已校准正式置信度。未降低任何统计门槛，不报告Alpha Court通过。

## 账本与核验 / Ledger and verification

- 96 new trials; cumulative raw lower bound 3184.
- 192 independently reconciled accounts; maximum NAV residual CNY4.66e-10.
- All account hashes and SQL/Python return, cost and drawdown comparisons match.
- Existing candidate/parent evidence unchanged; no2025/2026 access.

## 后续 / Next step

先判断有没有经济线索及失败主要来源，再预声明下一有限批次。既有线索不覆盖，所有修改保留谱系并计Trial。下一步优先连续账户和期限/成交机制，不把更多公式当作独立证据。
