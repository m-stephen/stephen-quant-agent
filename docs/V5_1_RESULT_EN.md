# V5.1 Frozen Candidate Reliability Audit Report

## Final decision

The V5.0 two-factor ensemble remains worth monitoring forward, but it is not a reliable or
deployable Alpha. The formal V5.1 decision is `FORWARD_CANDIDATE_WITH_BLOCKERS`.

The frozen candidate equally ranks `chip_cost_gap_reversal_5_20_20d` and
`flow_price_divergence_20_20d`, buys the top 50 names with CNY 3m, and uses a 20-session
horizon. 2021 supplies lookback only. All 2022–2024 results are reused development evidence,
not a fresh final test.

## Main results

| Signal representation | Cost scenario | Excess return | Increment | Positive paths | Q25 path Sharpe | Capacity clipped |
|---|---|---:|---:|---:|---:|---:|
| Raw ensemble | Standard | 31.27% | 32.72% | 19/20 | 0.447 | CNY 0 |
| Raw ensemble | Double | 16.63% | 19.22% | 16/20 | 0.121 | CNY 0 |
| Raw ensemble | Conservative | 13.64% | 16.45% | 15/20 | 0.046 | CNY 0 |
| Style residual | Standard | 5.86% | 7.03% | 16/20 | 0.093 | CNY 0 |
| Style residual | Double | -5.14% | -3.02% | 5/20 | -0.202 | CNY 0 |
| Style residual | Conservative | -7.23% | -5.10% | 5/20 | -0.267 | CNY 0 |
| Industry-proxy residual | Standard | 22.11% | 23.47% | 20/20 | 0.263 | CNY 0 |
| Style plus industry proxy | Standard | 0.32% | 1.44% | 11/20 | -0.338 | CNY 0 |

Excess return is compounded excess over an identically evaluated no-signal control, not account
absolute return. At CNY 3m, 31.27% corresponds to about CNY 938k of historical excess-capital
equivalent; the conservative 13.64% corresponds to about CNY 409k. Neither is a forecast.

## Attribution

Raw RankIC was 0.1214, 0.0850 and 0.1251 in 2022, 2023 and 2024. After removing prior-known
size tier, liquidity tier, 20-session momentum and volatility, RankIC fell to 0.0545, 0.0363 and
0.0272 but remained positive in every year. Standard-cost excess remained 5.86%. This shows
some information beyond those controls, but also shows that much of the raw result is related to
style exposure.

The style residual turns negative under doubled and conservative costs, so the independent edge
has a thin economic margin. The industry-proxy residual remains strong, but daily-file industry
labels lack authoritative historical membership intervals and are diagnostic only.

## Frozen gates

| Gate | Threshold | Result | Status |
|---|---|---:|---|
| Feature timing | zero violations | 0 / 829,663 | PASS |
| Raw standard paths | at least 15/20 | 19/20 | PASS |
| Raw conservative paths | at least 15/20 | 15/20 | PASS |
| CNY 3m capacity clipping | CNY 0 | CNY 0 | PASS |
| Inherited PBO | <= 0.05 | 0.000 | PASS |
| Signal placebo | <= 0.05 | 0.005 | PASS |
| Return placebo | <= 0.05 | 0.005 | PASS |
| DSR | >= 0.95 | 0.00000197 | **FAIL** |
| Historical chip-vintage proof | required | absent | **FAIL** |

The fixed audit added 12 Trials, taking the cumulative count from 1,206 to 1,218. DSR uses the
empirical incremental-return skewness of 1.1900 and excess kurtosis of 5.9708. The low DSR means
the observed historical Sharpe cannot yet overcome the full research program's multiplicity.

## Data reliability

- Daily, fund-flow and chip files are frozen into composite snapshot
  `823a06bbd078fb5c91640709260abfb1c3aa2c5018742b86adbcd234b472bd48`.
- All 829,663 candidate observations have feature availability before next-open execution.
- Chip data is used only after the source day's close, but the vendor does not provide historical
  vintage or immutability proof; later revision of historical files therefore remains unexcluded.
- Industry uses the prior session's daily-file label and is classified
  `B_CURRENT_LABEL_PROXY_DIAGNOSTIC_ONLY`.

## Recommendations

1. Freeze the candidate and do not tune neighboring windows, weights, horizons or costs.
2. Run append-only forward validation after at least 25 genuinely new common sessions arrive.
3. Obtain chip-file vintage evidence. If unavailable, test the fund-flow mechanism separately;
   do not promote the current ensemble to formal Alpha.
4. Give new discovery a separate Trial budget and distinct mechanisms—margin financing,
   auctions and corporate actions—rather than refinements of these two formulas.
5. Cache or chunk frozen factor panels by snapshot hash to reduce the roughly 14 GB peak without
   changing observations, timestamps or metrics.

This result does not authorize live trading. The appropriate action is to retain the candidate for
new-data validation while continuing independent-mechanism discovery.
