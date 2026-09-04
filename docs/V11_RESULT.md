# V11.0 Research Reset result / 研究重置结果

V11.0 implements the executable contract in
[Issue #170](https://github.com/m-stephen/stephen-quant-agent/issues/170).
It corrects the interpretation of earlier evidence, freezes historical search,
creates an append-only forward protocol, and permits one bounded development
epoch only after the statistical contract passes.

## Final decision / 最终结论

`NO_CANDIDATE_FOR_FORWARD_OBSERVATION`

The implementation is operational, but none of the twelve preregistered
candidates passed Alpha Court. This is a successful fail-closed research result,
not an alpha discovery. No candidate is authorized for forward promotion or
trading.

实现已经可运行，但 12 个预注册候选均未通过 Alpha Court。这是一次正确的
失败关闭结果，不代表发现了 Alpha。当前没有候选获准进入前向晋级或实盘。

## Statistical contract / 统计合同

- Gate A: `READY_FOR_BOUNDED_EPOCH`.
- Historical search is frozen; legacy V10 return-search commands fail closed.
- 2022–2024 are classified as `DEVELOPMENT_ONLY`.
- 2025–2026 historical return labels remain sealed; unauthorized reads: `0`.
- The planted signal survives universe robustness and rejects the signal and
  universe-construction nulls at `p=0.01`.
- Noise does not reject the null (`p=0.36`).
- Rank-reversal paths produce identifiable PBO; repeated invariant paths return
  `NOT_IDENTIFIABLE` rather than a misleading probability.

## Prospective protocol / 前向协议

- Frozen candidates: the exact V10.1 and V10.3 candidate fingerprints.
- Capital/universe: CNY 3 million, Top 40, ten-name buffer.
- Costs: 41 bps standard and 82 bps double-cost; participation limit 5%.
- Checkpoints: day 25 runtime-only, day 126 descriptive-only, day 252 primary.
- The first eligible date is strictly after `2026-09-05`; eligible dates at
  freeze: `0`. Current status: `COVERAGE_ONLY`.
- Protocol SHA-256:
  `71ba4f198f2f3dcbc4877d684f5a5fd8023d806a469e2d2a482ead4174a77106`.

An initial engineering attempt converted a local freeze timestamp through UTC
before deriving its trading date. It produced no label read and no Trial, was
rejected, and was replaced by the local-date-preserving protocol above.

第一次工程运行曾在确定交易日期前把本地冻结时间转换为 UTC。该运行没有读取
收益标签、没有增加 Trial，已被拒绝，并由上述保持本地日期语义的协议替代。

## Bounded epoch / 一次性封闭研究

- Budget: exactly `12` inferential candidates, four mechanisms and three
  candidates per mechanism.
- Negative controls: one non-promotable control per mechanism.
- Trial accounting: `743 -> 755`; inferential Trials added: `12`.
- Forced stop: `true`; automatic successor epoch: disabled.
- Unauthorized sealed-label reads: `0`.

| Mechanism / 机制 | Best development candidate / 最佳开发候选 | Horizon | Net excess return | Sharpe | Double-cost excess | DSR | PBO | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Auction absorption / 竞价吸收 | `-(rank(auction_return))` | 3 | -86.12% | -2.991 | -93.81% | 0.000 | 1.000 | Reject |
| Closing structure / 尾盘结构 | `-(rank(vwap_deviation))` | 5 | -65.10% | -1.831 | -79.48% | 0.000 | 1.000 | Reject |
| Flow-price mismatch / 资金价格错配 | `rank(main_inflow_ratio)-rank(ret_20)` | 10 | 13.62% | 0.464 | -12.52% | 0.000 | 0.900 | Reject |
| Chip crowding / 筹码拥挤 | `-(rank(profit_ratio)-rank(concentration))` | 20 | 62.66% | 1.249 | 47.42% | 0.001 | 0.300 | Reject |

The chip-crowding candidate is the strongest descriptive result. It passed the
return, double-cost, year/regime, universe, null and capacity checks, but failed
the predeclared multiplicity gates: `DSR >= 0.95` and `PBO <= 0.05`. Its observed
DSR is `0.001229` and PBO is `0.30`; therefore it is not promoted.

筹码拥挤候选是本轮最强的描述性结果。它通过收益、双倍成本、年份/市场状态、
股票池、零假设和容量检查，但未通过预先声明的多重检验门槛：`DSR >= 0.95`
与 `PBO <= 0.05`。其 DSR 为 `0.001229`、PBO 为 `0.30`，因此不晋级。

## Interpretation / 解释

V11.0 resolves the statistical-contract defect identified in Issue #169. It
does not manufacture a positive alpha result. The honest next state is to keep
the two historical clues frozen for genuinely new append-only observations and
to stop historical return-guided generation until a separately preregistered
research question is approved.

V11.0 修复了 Issue #169 指出的统计契约问题，但不会制造正向 Alpha 结论。
当前应保持两个历史线索冻结，等待真正新增的 append-only 数据；在新的独立研究
问题完成预注册前，不再进行历史收益引导的自动生成。
