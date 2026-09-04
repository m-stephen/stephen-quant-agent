# V11.1 Mechanism Discovery result / 机制化 Alpha 研究结果

V11.1 implements [Issue #172](https://github.com/m-stephen/stephen-quant-agent/issues/172).
The frozen implementation commit is
`7e3a00b9c7407957dbf44a3569b714be25fa298c`.

## Final decision / 最终结论

`NO_CANDIDATE_FOR_FORWARD_OBSERVATION`

All fifteen preregistered candidates completed the same fail-closed Alpha
Court. None passed every gate, so no candidate was added to the prospective
forward protocol and no trading claim is made.

15 个预注册候选均完成同一套失败关闭 Alpha Court。没有候选通过全部硬门禁，
因此没有候选进入前向协议，也不构成实盘授权。

## Integrity evidence / 完整性证据

- Label-free screen: `15/15` passed before any return-label query.
- Eligible date coverage: `85.4%–92.3%`; variable eligible dates: `100%`.
- All score fingerprints were distinct; estimated capacity exceeded CNY 350m.
- Inferential Trial budget: exactly `15`; raw disclosed count: `755 -> 770`.
- Local registry: all `15/15` V11.1 Trials have immutable results.
- Unauthorized 2025–2026 historical label reads: `0`.
- Forced stop: `true`; automatic successor epoch: disabled.
- Report SHA-256:
  `6999406bd8151d51aa42a797cc26503fe12ff8101d229e5cea30e18e9937173f`.

## Candidate results / 候选结果

All returns below are cumulative net excess returns over the 2022–2024
development period, relative to the contemporaneous investable-universe
equal-weight benchmark.

| Mechanism | Candidate | H | Net excess | Sharpe | Double cost | DSR | PBO | Main failures |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Chip state | `concentration_change - profit_ratio_change` | 20 | -3.39% | -0.061 | -16.03% | 0.000006 | 0.60 | Return, stability, nulls, DSR, PBO |
| Chip state | `concentration_change × closing_volume_share` | 20 | -7.77% | -0.283 | -19.21% | 0.000001 | 0.60 | Return, stability, nulls, DSR, PBO |
| Chip state | `-(concentration_change × vwap_deviation)` | 20 | -20.32% | -0.525 | -30.06% | 0.000000 | 0.60 | Return, stability, nulls, DSR, PBO |
| Chip state | `concentration_change × main_inflow_ratio` | 20 | **8.22%** | **0.381** | **-4.95%** | 0.000136 | 0.60 | Cost, 2024/down regime, universe, return null, DSR, PBO |
| Chip control | `concentration × profit_ratio_change` | 20 | -8.85% | -0.249 | -20.56% | 0.000001 | 0.60 | Negative control and broad failures |
| Flow mismatch | `net_inflow_persistence - ret_20` | 10 | -6.14% | -0.147 | -24.66% | 0.000000 | 0.05 | Return, stability, return null, DSR |
| Flow mismatch | `main_inflow_persistence - ret_20` | 10 | -4.86% | -0.131 | -23.63% | 0.000000 | 0.05 | Return, stability, return null, DSR |
| Flow mismatch | `net_inflow_persistence × closing_volume_share` | 10 | -41.12% | -2.062 | -54.95% | 0.000000 | 0.05 | Broad failures |
| Flow mismatch | `-(main_inflow_persistence × vwap_deviation)` | 10 | -40.91% | -1.906 | -54.96% | 0.000000 | 0.05 | Broad failures |
| Flow control | `net_inflow_change` | 10 | -35.04% | -1.871 | -51.54% | 0.000000 | 0.05 | Negative control and broad failures |
| Auction/close | `closing_volume_share - auction_return` | 5 | -65.86% | -3.751 | -80.18% | 0.000000 | 0.00 | Return, stability, nulls, DSR |
| Auction/close | `late_30_return - auction_return` | 5 | -73.24% | -3.579 | -84.48% | 0.000000 | 0.00 | Return, stability, nulls, DSR |
| Auction/close | `-(auction_return × intraday_return)` | 5 | -82.36% | -3.884 | -89.64% | 0.000000 | 0.00 | Return, stability, nulls, DSR |
| Auction/close | `vwap_deviation - auction_return` | 5 | -77.63% | -3.695 | -86.99% | 0.000000 | 0.00 | Return, stability, nulls, DSR |
| Auction control | `realized_volatility` | 5 | -15.91% | -0.488 | -37.41% | 0.000000 | 0.00 | Negative control and broad failures |

Rank expressions and cross-sectional neutralization are omitted from the short
formula labels above; the machine JSON preserves the exact formulas and lineage.

## Strongest descriptive clue / 最强描述性线索

The strongest promotable candidate combines rising chip concentration with
main-fund inflow. Its net excess return is `8.22%`, but this falls to `-4.95%`
under double costs. It loses `3.20%` in 2024, loses `1.98%` in benchmark-down
periods, has universe-robustness q25 of `-9.75%`, return-null p=`0.06`, DSR
`0.000136` and PBO `0.60`. It is neither stable nor selection-bias resistant.

最强正式候选把筹码集中度上升与主力净流入结合。其净超额为 `8.22%`，但双倍
成本后降至 `-4.95%`；2024 年为 `-3.20%`，基准下跌状态为 `-1.98%`，股票池
扰动 q25 为 `-9.75%`，Return null p=`0.06`、DSR=`0.000136`、PBO=`0.60`。
它既不稳定，也无法抵御选择偏差。

## Research interpretation / 研究解释

1. Capacity is not the bottleneck. Every candidate supports far more than the
   frozen CNY 3m capital assumption.
2. The strong V11 level-based chip result did not translate into a robust
   state-transition mechanism after industry, liquidity and volatility
   cleaning. A material part of the earlier result may be exposure or
   specification dependent.
3. Flow-price divergence occasionally rejects signal and universe nulls, but
   return signs reverse across years and market regimes; PBO alone cannot rescue
   a losing economic strategy.
4. The preregistered auction/close directions are consistently wrong in this
   development window. Their reversed signs are post-result hypotheses only and
   were not tested or promoted in this epoch.
5. Adding more formulas around these exact constructions would increase
   multiplicity without addressing their mechanism instability.

本轮没有发现可用 Alpha，但排除了三组具体机制表达，并表明下一步若继续研究，
重点应是重新提出独立经济机制，而不是围绕当前公式调参数或事后翻转方向。
