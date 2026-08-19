# V7.2 Source-balanced Automatic Factor-discovery Report

## Conclusion

System status: `OPERATIONAL`. Research status: `RESEARCH_CANDIDATE_PENDING_EXECUTION`. The frozen
set reaches the final PBO boundary, but it has not passed cost, placebo, DSR or Alpha Court gates and
is not deployable.

## Experiment

- Labels: 2022–2024 only; 2025/2026 unopened.
- Dynamic universe: at most 300 stocks per date.
- 32 direction-complete candidates; ten entered CPCV; 42 Trials recorded.
- Composite snapshot: `8e48128cc889baf07a92bd60920db7c3010938ff08d3b17bca2e7a9cd69e8088`.
- Alternative coverage: 1,245,394 chip rows, 1,245,790 fund-flow rows and 910,285 margin rows.

## CPCV result

Fold-selection PBO was `0.05`: one of 20 purged folds selected a training winner whose complementary
OOS rank fell in the lower half.

| Rank | Source | Formula and direction | Mean fold RankIC | Fold range | Positive |
|---:|---|---|---:|---:|---:|
| 1 | Daily | `-period_return(close, 20)` | 0.066944 | 0.049501–0.084394 | 20/20 |
| 2 | Chip | `-sma_ratio(chip_cost_5, 1, 5)` | 0.051327 | 0.035600–0.067066 | 20/20 |
| 3 | Chip | `-sma_ratio(chip_cost_15, 1, 5)` | 0.045719 | 0.020758–0.070696 | 20/20 |
| 4 | Flow × margin | `mean(net_inflow_amount,5)/mean(margin_financing_balance,5)` | 0.032104 | 0.010738–0.053450 | 20/20 |

No pure fund-flow candidate reached the shortlist. Four chip, three margin and one cross-source
candidate did, proving that the adapters now provide testable orthogonal evidence rather than mere
directory availability.

## Decision

Because PBO only equals the final 0.05 ceiling, the search space is frozen instead of expanded.
Twenty-session reversal, chip-cost change and cross-source flow pressure should next receive
standard/doubled-cost, CNY 3 million capacity, placebo, DSR, correlation and marginal-portfolio
tests. Alpha Court PASS requires every gate.
