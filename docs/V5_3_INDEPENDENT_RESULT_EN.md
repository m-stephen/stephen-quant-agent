# V5.3 Independent-Mechanism Factor Search Report

## Final decision

The search found no independent-mechanism candidate eligible for Alpha Court. The formal decision is `NO_INDEPENDENT_ALPHA`.

The system pre-registered seven formulas across margin financing, opening auction and limit-event domains, tested both directions, and recorded **14 candidate Trials**. Chip and fund-flow inputs were excluded. Screening used a size-balanced panel of roughly 300 names per day. No candidate passed the joint cross-year IC, return-path and decay rules, so there were zero stable candidates and zero validation Trials. The cumulative Trial count increased from 1,218 to **1,232**.

## Most useful finding

Several candidates had same-sign positive RankIC in all three years but lost money in the costed Top50 portfolio. Cross-sectional correlation therefore did not translate into tradable excess return.

| Candidate | Domain | 2022/2023/2024 RankIC | Annual portfolio excess | Positive paths |
|---|---|---|---|---|
| Limit-up seal strength, negative direction | Limit event | 0.0520 / 0.0590 / 0.0497 | -13.24% / -7.82% / -2.52% | 0 / 3 / 7 of 20 |
| Limit-up main-net amount, negative direction | Limit event | 0.0450 / 0.0509 / 0.0438 | -13.99% / -8.18% / -2.61% | 0 / 2 / 7 of 20 |
| Auction price absorption, positive direction | Auction | 0.0362 / 0.0341 / 0.0438 | -6.03% / -2.85% / -0.96% | 6 / 7 / 8 of 20 |
| Margin crowding reversal, negative direction | Margin | 0.0152 / 0.0450 / 0.0234 | -4.44% / -5.30% / -6.71% | 3 / 0 / 4 of 20 |

All evidence is reused 2022–2024 development evidence, not a fresh final test. The snapshot SHA-256 is `82631cf88431a6dd62e631aca08c526cc7776fdbc4d0638e109445d14547360a`.

## Why validation stopped

The protocol requires stable candidates from at least two independent domains before entering the roughly 1,200-name validation panel and spending at most six raw/style-residual by cost-scenario Trials. With zero stable candidates, the process stopped as designed and did not run DSR, PBO, placebo or cost-stress gates. Combining unstable candidates would only enlarge the search space and manufacture lucky results.

## Assessment of the discovery system

1. **Search breadth is no longer the primary bottleneck.** The universe is now market-wide and size-balanced, and this run covered three distinct data mechanisms. Failure occurred at cross-year economic tradability, not candidate count.
2. **Limit-event and auction signals look like ranking information rather than net-return signals.** Turnover, execution cost, Top50 concentration or benchmark effects consume their positive RankIC. Diagnose this before changing any window.
3. **Margin signals lack a stable direction.** The current low-frequency fields do not adequately represent deleveraging, forced selling or crowding-release regime changes.
4. **The negative result saved validation budget.** All 14 attempts are in the ledger, and early stopping avoids worsening multiplicity with unsupported combinations.

## Recommended next steps

1. Perform fixed-formula attribution on the leading positive-IC/negative-return candidates: gross return, turnover, cost, size/industry exposure and holding-period return curves. This is diagnostic only and must not change formulas.
2. Limit the next search to genuinely new mechanisms: corporate-action events, accounting revisions/expectation gaps, announcement-text shocks, or margin balances relative to lendable supply. Pre-register a direction-complete Trial budget per domain.
3. While authoritative corporate-action and industry PIT sources remain unavailable, continue candidate generation with existing price/event data but keep conclusions at development grade. Do not wait idly and do not promote proxies to formal PIT evidence.
4. Keep Track A waiting for genuinely new observations. Failed Track B candidates must not feed back into the frozen Track A specification.

This report does not authorize live trading or deployment of CNY 3m into any candidate tested here.

## Appendix: complete candidate-ledger summary

| Candidate ID | 2022/2023/2024 RankIC | 2022/2023/2024 portfolio excess |
|---|---|---|
| `margin_buy_intensity_20_20d_positive` | -0.0082 / -0.0237 / 0.0257 | -2.14% / -4.42% / 5.79% |
| `margin_buy_intensity_20_20d_negative` | 0.0082 / 0.0237 / -0.0257 | -1.04% / -2.56% / -9.34% |
| `margin_demand_acceleration_5_20_20_20d_positive` | -0.0251 / 0.0025 / 0.0086 | -6.58% / -3.00% / -1.11% |
| `margin_demand_acceleration_5_20_20_20d_negative` | 0.0251 / -0.0025 / -0.0086 | 1.44% / -0.96% / -4.43% |
| `margin_crowding_reversal_20_20_20d_positive` | -0.0152 / -0.0450 / -0.0234 | -5.65% / -10.98% / -1.98% |
| `margin_crowding_reversal_20_20_20d_negative` | 0.0152 / 0.0450 / 0.0234 | -4.44% / -5.30% / -6.71% |
| `auction_price_absorption_5_20_20d_positive` | 0.0362 / 0.0341 / 0.0438 | -6.03% / -2.85% / -0.96% |
| `auction_price_absorption_5_20_20d_negative` | -0.0362 / -0.0341 / -0.0438 | -18.55% / -17.01% / -13.62% |
| `limit_up_persistence_20_20_20d_positive` | -0.0476 / -0.0613 / -0.0399 | -7.38% / -9.21% / -7.24% |
| `limit_up_persistence_20_20_20d_negative` | 0.0476 / 0.0613 / 0.0399 | -11.87% / -6.91% / -1.38% |
| `limit_up_main_net_intensity_5_20_20d_positive` | -0.0450 / -0.0509 / -0.0438 | -16.78% / -12.72% / -4.92% |
| `limit_up_main_net_intensity_5_20_20d_negative` | 0.0450 / 0.0509 / 0.0438 | -13.99% / -8.18% / -2.61% |
| `limit_up_seal_strength_5_20_20d_positive` | -0.0520 / -0.0590 / -0.0497 | -17.43% / -12.90% / -7.49% |
| `limit_up_seal_strength_5_20_20d_negative` | 0.0520 / 0.0590 / 0.0497 | -13.24% / -7.82% / -2.52% |
