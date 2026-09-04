# V11.0 Research Reset specification / 研究重置规范

V11.0 implements [Issue #170](https://github.com/m-stephen/stephen-quant-agent/issues/170).
It replaces continuous V10 historical-return search with a fail-closed research
contract.

## Frozen boundaries / 冻结边界

- 2022–2024 are `DEVELOPMENT_ONLY`.
- 2025–2026 historical labels remain `SEALED`; maintenance may inspect only
  allowlisted, label-free metadata.
- The historical raw count is permanently disclosed as 743 trials.
- Legacy V10 search commands fail closed.
- No statistical, cost, capacity, drawdown or stability gate is lowered.

## Statistical contract / 统计合同

The calibration suite distinguishes deterministic universe robustness from
stratified signal/return nulls and a matched universe-construction null. Every
null declares its estimand, exchangeable unit, preserved constraints and
destroyed relationship. Insufficient exchangeability returns
`NOT_IDENTIFIABLE`, never PASS.

PBO eligibility requires candidate rankings to vary across audited folds.
Invariant rankings and repeated path coverage return `NOT_IDENTIFIABLE` rather
than a precise probability.

校准套件将股票池扰动稳健性与分层信号/收益零假设、匹配股票池构造零假设明确
分离。样本交换性不足时返回 `NOT_IDENTIFIABLE`。候选排序在审计折间没有变化时，
PBO 同样失败关闭。

## Prospective shadow / 前向影子

Two exact historical clues are frozen with their positive direction, candidate
and trial fingerprints, method version, 20-session horizon, T+1-open decision
time, CNY 3m Top-40 policy, ten-name buffer, standard/double costs and capacity.

The first eligible date is strictly after both the protocol freeze date and the
maximum date already present at freeze. Existing data cannot be backfilled.
Day 25 is runtime-only, day 126 descriptive-only and day 252 is the sole primary
Holm-corrected checkpoint. Interim returns cannot replace or modify candidates.

## One-shot epoch / 一次性研究

After the machine Gate A passes, exactly twelve preregistered candidates are
tested once: three per mechanism at fixed 3/5/10/20-session horizons. One per
family is a non-promotable negative control. Every candidate consumes exactly
one inferential Trial before labels are loaded. The epoch always stops after the
report and cannot automatically create a successor.

Promotion requires positive standard and double-cost development return,
positive year/regime results, capacity, positive universe-robustness lower
quartile, three identifiable null tests with p <= 0.05, DSR >= 0.95 and
identifiable PBO <= 0.05. Passing only means eligibility for independent forward
evidence, not reliable alpha or trading authorization.
