# V4.2 Economic Conversion Stability Test Report

## Decision

V4.2 is complete, but Alpha Court still returns `NO_DEPLOYABLE_ALPHA`.

The release fixes one engineering problem: the V4.1 winner selected by maximum 2023 full-year
Sharpe no longer wins. Four chronological subwindows, double-cost stress, adjacent breadths and a
regime-increment burden instead select:

`limit_proximity_60_20d_neg + TIMING / breadth=10 / risk_off`

All four 2023 subwindows were positive. Worst subwindow Sharpe was 4.7510, stressed worst Sharpe
was 3.7734, and breadth 5/10/20 all passed. The frozen 2024 shadow nevertheless reversed to
Sharpe -3.9514, cumulative excess -27.84% and drawdown -32.90%.

Within-year, cost and parameter stability therefore did not establish cross-year regime
stability. The mapping is not deployable and 2024 cannot be used to reselect it.

## Frozen design

- Freeze the first twelve V4.1 representative mechanisms; add no candidates.
- Shortlist SHA-256:
  `913de6d25c60289f9a0c04f053d2803bd5933b0a893ad8984203ec002dce9a46`.
- 2022: inherited V4.1 discovery evidence only.
- 2023: sole conversion-selection year, split into four chronological subwindows.
- 2024: evaluated once after selection; never used for thresholds or reselection.
- 2025/2026: `SEALED`.

The grid is `BUY / AVOID / TIMING × breadth 5/10/20 × all/risk_on/risk_off`, under normal and
double costs. That creates 648 mapping Trials. Twelve candidate Trials, one shadow Trial and five
capacity Trials produce 666 audited Trials in total.

## Real-data result

| Metric | Result |
|---|---:|
| Snapshot SHA-256 | `b3a638ceb564292a5a36a577257bfacfbc0db05e5147cb3879bdc68d5c27a68e` |
| Frozen candidates | 12 |
| Mapping / total Trials | 648 / 666 |
| Selected candidate | `limit_proximity_60_20d_neg` |
| Selected mapping | `TIMING / breadth=10 / risk_off` |
| Stability admission | passed |
| PBO | 0.000 |
| Signal-shuffle / return-permutation p | 0.005 / 0.005 |
| DSR probability | `2.85e-14` |

| Window | Excess Sharpe | Cumulative excess | Max drawdown |
|---|---:|---:|---:|
| 2023 normal costs | 5.2861 | 21.77% | -5.09% |
| 2023 double costs | 4.8069 | 19.67% | -5.24% |
| 2024 frozen shadow | -3.9514 | -27.84% | -32.90% |

No capacity clipping occurred from CNY 1m through CNY 20m, but all sizes retained the same
negative 2024 result. Capacity is not the failure source.

## Ablation diagnosis

- 2023 raw RankIC: 0.06031.
- 2023 residual RankIC: 0.01625.
- Same candidate/use/breadth unconditional Sharpe: 3.2426.
- Selected `risk_off` Sharpe: 5.2861.
- Double-cost Sharpe: 4.8069.
- 2024 regime mapping Sharpe: -3.9514.

Residualization weakened IC but did not remove 2023 economics; costs and capacity were not the
primary problem. The failure is cross-year migration of the `risk_off` wrapper. V4.2 can prove
within-2023 incremental stability, not that a state definition represents the same mechanism in a
different year.

## Alpha Court

Failed gates:

- `dsr`: about `2.85e-14` after 648 mapping attempts.
- `shadow_sharpe`: -3.9514 versus the required 0.50.
- `shadow_drawdown`: -32.90% versus the 25% limit.

Passing PBO and both placebo tests cannot override the DSR and frozen-shadow failures.

## Historical price-limit upgrade

V4.2 adds deterministic main-board, ChiNext, STAR and Beijing rules, including the dated ChiNext
reform, optional ST state and optional listing-session exemptions. The implementation is based on
official exchange material:

- [SSE STAR trading rules](https://www.sse.com.cn/lawandrules/sselawsrules/repeal/rules/c/10118601/files/f6fc4a1d4c1f469183a013c4dc36a535.pdf)
- [SZSE ChiNext reform guidance](https://investor.szse.cn/index/update/t20200807_580310.html)
- [BSE trading-rule Q&A](https://www.bse.cn/important_news/200010675.html)
- [SSE registration-system main-board explanation](https://www.sse.com.cn/home/component/news/c/c_20230201_5715622.shtml)

The current daily source lacks complete historical ST and listing-session metadata. Runtime rules
therefore label these cases `board_proxy_missing_*`; the board-code proxy is never presented as
exact historical evidence.

## Next boundary

V4.2 demonstrates that adding more 2023 stability metrics can still select a mapping that fails in
2024. Thresholds must not be retuned on 2024. The defensible next step is to freeze a simple
unconditional conversion specification and collect genuinely forward paper-trading evidence from
2026-08-19 onward. No deployable alpha should be claimed before enough forward evidence exists.
