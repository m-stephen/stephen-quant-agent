# V11.7 Incremental Alpha Test Report

Decision: **FROZEN_HISTORICAL_LEAD**. Validated Alpha: **false**.

Historical leads: 2/16.

Both2023/2024 are contaminated historical development. No trading approval or independent OOS claim.

## Definitions and comparisons

Independent CNY3m each year; lagged ADV>=CNY10m,>=20-session history, non-ST. Top40/buffer10, previous-close signal/next-open execution.
Controls are coverage/horizon-matched low-vol Top40 and hashed Top40, not CSI300. Compounded annual-reset accounts are a normalized link, not continuous trading.

## All candidates (double costs)

| Candidate | 2023 net | 2024 net | Compound increment vs low-vol | Pooled Sharpe | Lead |
|---|---:|---:|---:|---:|---|
| blend_ret_20_-1_h20 | -13.36% | -1.49% | -41.03pp | -0.253 | False |
| blend_ret_20_+1_h20 | 2.26% | 23.22% | -0.37pp | 0.769 | False |
| blend_liquidity_-1_h20 | 9.03% | 0.88% | -16.39pp | 0.346 | False |
| blend_liquidity_+1_h20 | -1.04% | 26.60% | -1.09pp | 0.884 | False |
| blend_net_inflow_ratio_-1_h20 | -7.35% | 10.96% | -23.58pp | 0.169 | False |
| blend_net_inflow_ratio_+1_h20 | 7.87% | 19.26% | +2.27pp | 0.894 | False |
| blend_concentration_-1_h20 | -0.95% | 15.20% | -12.27pp | 0.491 | False |
| blend_concentration_+1_h20 | 0.90% | 33.67% | +8.51pp | 1.067 | True |
| blend_late_30_return_-1_h20 | 3.53% | 28.33% | +6.48pp | 0.954 | True |
| blend_late_30_return_+1_h20 | -7.75% | -7.91% | -41.42pp | -0.396 | False |
| blend_realized_volatility_-1_h20 | -5.23% | 15.55% | -16.86pp | 0.385 | False |
| blend_realized_volatility_+1_h20 | 0.37% | 14.65% | -11.30pp | 0.492 | False |
| blend_amihud_intraday_-1_h20 | -5.55% | 35.01% | +1.14pp | 0.962 | False |
| blend_amihud_intraday_+1_h20 | 2.19% | 9.44% | -14.54pp | 0.394 | False |
| blend_auction_return_-1_h20 | 0.92% | 9.28% | -16.09pp | 0.364 | False |
| blend_auction_return_+1_h20 | -2.98% | 13.63% | -16.13pp | 0.383 | False |

## blend_concentration_+1_h20

Identity: `6aef857e541e9787432cf5a9b888fbf9b67866e4e46fc86495f6781f3ddf1f60`.
Formula: `0.7*(-rank(vol20))+0.3*direction*rank(signal)`.

| Year | Cost bps | Net return | Profit CNY | Low-vol | Hash control | Drawdown | Cost CNY |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 0 | 7.51% | 225,175.86 | 8.71% | 5.05% | -9.92% | 0.00 |
| 2023 | 41 | 4.15% | 124,532.45 | 4.79% | 4.69% | -10.95% | 104,069.83 |
| 2023 | 82 | 0.90% | 27,149.63 | 1.02% | 4.32% | -12.09% | 204,751.94 |
| 2024 | 0 | 42.03% | 1,260,885.39 | 34.30% | 1.30% | -10.68% | 0.00 |
| 2024 | 41 | 37.78% | 1,133,539.22 | 29.61% | 0.89% | -11.52% | 105,810.39 |
| 2024 | 82 | 33.67% | 1,010,097.45 | 25.10% | 0.48% | -12.34% | 208,185.61 |

Quarterly double-cost returns (quarters compound; not summed):

- 2023: Q1 +7.15%, Q2 -0.05%, Q3 +0.29%, Q4 -6.05%; writeoffs=0, stale-position-days=0, traded=CNY50,280,380, holdings Jaccard vs low-vol=0.110.
- 2024: Q1 +7.82%, Q2 -2.18%, Q3 +19.04%, Q4 +6.47%; writeoffs=0, stale-position-days=13, traded=CNY51,117,444, holdings Jaccard vs low-vol=0.108.

## blend_late_30_return_-1_h20

Identity: `dbcf5838021af944830a7dc7269c1770306e1c1fdbe6df8fd0784aeaff43b60e`.
Formula: `0.7*(-rank(vol20))+0.3*direction*rank(signal)`.

| Year | Cost bps | Net return | Profit CNY | Low-vol | Hash control | Drawdown | Cost CNY |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2023 | 0 | 13.81% | 414,245.70 | 8.71% | 3.75% | -9.40% | 0.00 |
| 2023 | 41 | 8.55% | 256,366.04 | 4.79% | 3.37% | -10.42% | 154,090.83 |
| 2023 | 82 | 3.53% | 105,770.94 | 1.02% | 3.00% | -11.42% | 300,948.49 |
| 2024 | 0 | 40.78% | 1,223,306.71 | 34.30% | 6.05% | -11.96% | 0.00 |
| 2024 | 41 | 34.41% | 1,032,334.70 | 29.61% | 5.59% | -13.21% | 156,915.86 |
| 2024 | 82 | 28.33% | 849,890.51 | 25.10% | 5.13% | -14.45% | 306,392.10 |

Quarterly double-cost returns (quarters compound; not summed):

- 2023: Q1 +3.82%, Q2 +1.68%, Q3 +1.40%, Q4 -3.29%; writeoffs=0, stale-position-days=5, traded=CNY73,731,224, holdings Jaccard vs low-vol=0.105.
- 2024: Q1 +6.30%, Q2 -5.47%, Q3 +18.11%, Q4 +8.13%; writeoffs=0, stale-position-days=24, traded=CNY75,058,268, holdings Jaccard vs low-vol=0.141.

## Statistical and engineering checks

- Independently reconciled 192 accounts; max residual CNY0.0000000005.
- Trials: reserved 192, completed 96, raw lower bound 3058.
- All accounts retain costs/cash/orders/positions. Protected candidate files unchanged; no2025/2026 data reads.
- Family best-mean candidate: 6aef857e541e9787432cf5a9b888fbf9b67866e4e46fc86495f6781f3ddf1f60; DSR sensitivity=0.008278541201081513; PBO diagnostic=0.7; family placebo p=0.905.

The statistical selector maximizes mean daily active return and may differ from the historical-wealth winner; its DSR must not certify another candidate.

## Limits and next steps

Adjusted fractional shares, fixed fees, lagged ADV capacity and20-session stale write-downs are approximations. Board lots/minimum fees/actual opening volume are not established. Low-vol control excludes only part of style explanations; industry/size/beta exposures are not fully regressed.
Missing aligned historical Sharpe matrix makes DSR sensitivity-only; CPCV/placebo are historical diagnostics. Generation uses bounded mechanism grammar, not external LLM calls.
Freeze any lead and stop expanding; independently replay, then test brokerage/capacity realism and forward shadow performance. Without leads, preserve all failures and propose a new mechanism without relaxing criteria.

Snapshot: `b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51`.
Result: `e10b06647b6b00e40bc4b898f00916ab120b2932bf1d839ccfd2cc4e11c40731`.
