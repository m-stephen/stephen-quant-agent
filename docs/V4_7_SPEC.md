# V4.7 Frozen Low-Turnover Alpha Protocol

V4.7 does not search for more factors. It freezes the two V4.6 signal structures and asks whether
a deterministic rank buffer can convert their information into a cost-robust development candidate.

## Frozen grid

- Signals: flow-price divergence alone; equal percentile-rank flow plus auction ensemble.
- Holding buffers: 0, 5 and 10 ranks.
- Costs: standard and 2x.
- NAV: CNY 3 million; horizon: 20 trading days; AVOID breadth: 10.
- Evidence: 2022-2025 reused development data. Data from 2026 is not read for tuning.
- Budget: exactly 12 recorded inferential Trials.
- DSR reference: the complete 40-estimate distribution from the frozen V4.6 Trial ledger plus all
  12 V4.7 estimates. Using only the tightly clustered V4.7 grid would understate historical search
  dispersion and is prohibited.

For each of the 20 non-overlapping offset paths, an existing holding is retained until its signal rank
falls below `breadth - buffer`. Empty slots are filled from the strongest remaining names. The rule is
stateful only within an offset path and never shares positions across paths.

## Development gate

The selected pair must, at standard and doubled costs, have positive full excess and matched-control
incremental returns, at least 16/20 profitable paths, non-negative median path Sharpe, positive evidence
in at least three of four years, positive 2025 incremental return, and both placebo p-values at or below
0.05. DSR remains a separate Alpha Court requirement and is not hidden by a development-level pass.

A development pass means only `WORTH_FORWARD_VALIDATION`. Independent proof can begin no earlier
than the append-only shadow period starting 2026-08-19.
