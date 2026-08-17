# V2.5 Regime-aware Portfolio Result
worthy of independent validation, but not a proven Alpha or live rule. 2025/2026 stayed sealed.
Engineering status: **RESEARCH_PREVIEW_READY**. Alpha status: **PROMOTE_RESEARCH_ONLY**.

## Policy results

| Policy | Net return | Annualized net Sharpe | Max drawdown | Turnover | Cost |
|---|---:|---:|---:|---:|---:|
| Frozen V2.3 baseline | 63.71% | 0.6028 | -21.12% | 32.8054 | CNY 226,029.47 |
| Cash in risk-off | 104.80% | 0.8537 | -8.87% | 15.5880 | CNY 129,340.34 |
| Momentum fallback in risk-off | -39.43% | -0.2313 | -54.87% | 30.4013 | CNY 127,130.58 |

Deterministic selection chooses `risk_off_cash`. It earns 106.70% across 16 risk-on periods and
loses about 0.92% across 19 risk-off periods through liquidation and re-entry costs. All three
execution years are positive; worst-year return is 2.54%, worst-year Sharpe is 0.3139, and the
minimum rolling-12 Sharpe is 0.0601.

## Failed gates

- the top 10% of absolute period returns contribute 69.98%, above the 50% limit;
- strategy-family PBO is 46.83%, above the 20% limit;
- DSR after 47 cumulative trials is 66.72%, below 95%.

Signal and return placebo p-values are 0.015 and 0.020. All engineering, exact replay, PIT,
capacity, ledger, and sealed-window gates pass. The evidence makes “do not trade in risk-off”
worthy of independent validation, but not a proven Alpha or live rule. 2025/2026 stayed sealed.
