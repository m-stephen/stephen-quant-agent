# V7.4 Novel-Mechanism Automatic Alpha Discovery Report

## Decision

V7.4 completed two bounded and auditable search epochs, but found **no deployable alpha**. The final decision is `REJECT_ALPHA_COURT`. The sealed 2025/2026 windows remained unopened, and every failed attempt was retained in the cumulative trial count.

The search did find statistical signals: several candidates had strong RankIC, placebo p-values of 0.005, and Epoch 2 produced candidates with 35/35 positive CPCV paths. Those signals did not convert into stable net portfolio returns, and the PBO, DSR, Sharpe, and drawdown gates still failed.

## Frozen protocol

- Research data: 2022-01-01 through 2024-12-31.
- 2025/2026 remained sealed and were not used for tuning.
- Capital: CNY 3 million.
- Epoch 1: 5-day horizon, Top 10, 48 directional candidates, 24 CPCV slots, 12 execution slots.
- Epoch 2: 20-day horizon, Top 20, 32 directional candidates, 16 CPCV slots, 8 execution slots.
- Standard costs: 3 bps commission, 5 bps sell tax, 5 bps slippage, 10 bps impact coefficient, 5% maximum participation.
- Doubled-cost stress remained enabled.
- Gates: DSR >= 0.95, PBO <= 0.05, placebo p <= 0.05, annualized Sharpe >= 0.50, maximum drawdown <= 25%.

## Epoch 1: novel-mechanism grammar

The system generated 24 mechanism formulas in both directions, for 48 candidates covering price risk, path quality, Amihud liquidity, flow impulses, margin demand, chip structure, and cross-source interactions.

| Metric | Result |
|---|---:|
| Screening trials | 48 |
| CPCV candidates | 17 |
| Full-Court candidates | 12 |
| Cumulative Court trials | 234 |
| PBO | 0.1000 (fail) |
| Best DSR | 0.1383 (fail) |
| Placebo p-values | 0.005 / 0.005 (pass) |
| Walk-forward return | 28.77% |
| Walk-forward Sharpe | 0.5733 |
| Walk-forward maximum drawdown | -28.72% (fail) |

The best executed candidate was inverse net margin-financing pressure:

- Standard-cost return 21.68%, annualized Sharpe 0.3500, maximum drawdown -35.71%.
- Doubled-cost return 4.33%, annualized Sharpe 0.1915.
- Capacity passed; Sharpe, drawdown, PBO, and DSR failed.

## Epoch 2: cross-source confirmation and slower execution

The system generated 16 cross-source formulas in both directions, for 32 candidates covering flow x margin, flow x chip, margin x chip, and price-path x alternative-data mechanisms. The horizon moved to 20 days and the portfolio to Top 20.

Two engineering runs each recorded 32 screening trials before failing closed because a CPCV path correction was applied to the wrong configuration block. All 64 attempts remain in the cumulative count. The final corrected run started with 298 prior trials and froze 7 groups, 3 test groups, and at least 15 positive paths.

| Metric | Result |
|---|---:|
| Final-run screening trials | 32 |
| CPCV candidates | 14 |
| Full-Court candidates | 8 |
| Cumulative Court trials | 360 |
| PBO | 0.0571 (fail) |
| Best DSR | 0.1804 (fail) |
| Placebo p-values | 0.005 / 0.005 (pass) |
| Walk-forward return | -7.81% |
| Walk-forward Sharpe | 0.0151 |
| Walk-forward maximum drawdown | -32.16% (fail) |

Epoch 2's best standard-cost candidate still lost 8.38%, with annualized Sharpe 0.0039 and maximum drawdown -34.18%; doubled-cost return was -13.02%. The slower horizon and broader portfolio did not solve tradability.

## Reliable findings

1. The broader mechanism space materially improved statistical-signal coverage; the system can now automatically generate and screen candidates that look strong.
2. RankIC, placebo, and positive CPCV paths are not sufficient evidence of tradable alpha. Several Epoch 2 candidates achieved 35/35 positive paths while losing money in portfolio execution.
3. The bottleneck has moved from search breadth to candidate-expression and portfolio-objective mismatch. Multiplying raw-unit signals amplifies tails and scale differences.
4. A longer horizon and more holdings did not automatically reduce drawdown, indicating regime and mapping risk beyond transaction costs.
5. Continuing an unbounded search on the same 2022–2024 window would only increase multiplicity. Stopping after two preregistered orthogonal epochs is required by the integrity policy.

## Engineering outcomes and next step

- Added a direction-complete, source-aware mechanism-combination grammar.
- Added cross-source confirmation mechanisms and a dedicated CLI.
- Reused raw observation panels across opposite directions while retaining independent identities and trials; observed memory fell from roughly 11.6 GB to 7.6–8.5 GB.
- Extracted the CPCV design into a directly validated frozen configuration so path feasibility is checked before expensive computation.
- A pre-release audit found that hashed schema IDs did not match the mechanism-family budget labels. Both realized shortlists already satisfied every declared cap, so results are unchanged. The code now prefers `schema.event` when it names a configured family, with regression coverage.

The next stage should not add more raw arithmetic formulas. Recommended order:

1. combine signals after fold-local cross-sectional rank/z-score normalization;
2. train with a portfolio-aware objective covering net return, drawdown, turnover, and path stability;
3. add fold-local industry, size, and volatility neutralization plus regime diagnostics;
4. persist shared feature matrices and CPCV path caches;
5. run append-only forward validation when genuinely new dates become available.

No current candidate is authorized for deployment.
