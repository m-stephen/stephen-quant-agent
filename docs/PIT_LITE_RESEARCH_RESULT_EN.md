# V2.9 PIT-Lite Factor Research Result

## Decision

**`NO_ROBUST_ALPHA_POPULATION`**. The frozen `flow_confirmation_20_20d` candidate retains positive
RankIC in RAW and price-style specifications, but all cost-aware portfolios lose money. After
fold-local PCA and statistical-cluster controls, 2024 RankIC turns negative and the placebo evidence
disappears. The candidate is not reliable alpha, and the best-looking RAW specification cannot be
promoted in isolation.

## 2023–2024 walk-forward results

| Specification | Mean RankIC | 2023 / 2024 RankIC | CNY 3m net return | Annualized net Sharpe | Max drawdown | DSR |
|---|---:|---:|---:|---:|---:|---:|
| RAW | 0.0381 | 0.0559 / 0.0186 | -3.88% | -0.7903 | -15.74% | 3.29% |
| PRICE_STYLE | 0.0302 | 0.0478 / 0.0111 | -6.61% | -1.6308 | -15.41% | 2.20% |
| PCA_NEUTRAL | -0.0065 | 0.0169 / -0.0320 | -15.35% | -3.8786 | -20.42% | 0.08% |
| STATISTICAL_CLUSTER_NEUTRAL | 0.0016 | 0.0156 / -0.0137 | -20.38% | -5.1337 | -22.55% | approximately 0% |

RAW and PRICE_STYLE signal/return placebo p-values are both 0.005. PCA produces 0.845/0.840 and
statistical clustering 0.420/0.405. None of the four specifications is capacity-clipped at CNY 20m,
but all still lose money; capacity is not the primary blocker.

## Integrity

- The daily-bar industry field remains `B_CURRENT_LABEL_BACKFILL`, diagnostics only and unused by the signal.
- 2023 is fit on 2022; 2024 is fit on 2022–2023. Scaling, PCA and clustering are fold-local.
- The successful research operation accessed neither 2025 nor 2026.
- Issue #98 added four Trials: three retained engineering failures and one completed result.
- Cumulative inferential Trial count is 52.
- Result SHA-256: `f74674b75eb1991e6436b457a01a0e8dad1d5c1f0669ef3db72c11cb8fe857d5`.
- Source snapshot: `d612a91a0045a1f4543955e19bcea1b26e37c18a818df2f9001b312b8c364587`.

The next epoch should tombstone further tuning of this candidate and reserve remaining Trial budget
for new economic mechanisms and data families rather than weakening risk, placebo or DSR gates.
