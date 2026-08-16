# V1.8.13 — Dynamic-Universe Stateful Engineering Backtest

## Objective

Connect the V1.8.11 daily point-in-time membership, QD sparse daily bars, immutable factor
registry, and V1.8.12 stateful execution engine in one registered 2022–2024 backtest.

This is an engineering integration run. The factor fixture was already rejected in V1.8.9, so
its return cannot be promoted as alpha evidence.

## Frozen run

- Data history: 2021-07-01 through 2024-12-31.
- Research execution: 2022-01-05 through 2024-12-31.
- Reserved validation: 2025-01-03 through 2025-12-31.
- Reserved final test: 2026-01-05 through 2026-08-14.
- Membership: frozen V1.8.11 daily Top-300 JSONL.
- Factor fixture: `mom_120_skip_20@1.0.0`, direction-adjusted exactly as registered.
- Portfolio: Top 20, equal weight, 2% cash reserve, 5% maximum position.
- Rebalance: every five execution sessions. Non-rebalance sessions retain drifted actual weights.
- Immediate exit intent when a previously targeted asset leaves the point-in-time membership.
- Capacity: 5% of mean amount over the prior 20 observed sessions, timestamped before open.
- Costs: 3 bps commission, 5 bps sell tax, 5 bps slippage.
- Sparse holdings: V1.8.12 stale valuation, 20-session zero-write-off, recovery, and price-limit
  blocking rules.
- Engineering benchmark: CSI 300 over the matched continuous NAV dates.

## Integrity requirements

- The market snapshot, membership JSONL, factor version, config, Experiment, and Trial are hashed
  or registered before execution.
- Signals and membership decided at close `t` may first trade at the next session open.
- Same-day amount is prohibited from order capacity.
- A missing held bar cannot delete a position or create a synthetic return.
- 2025 and 2026 files may not be loaded or hashed.
- Output must include the complete target audit, sparse-accounting report, data audit, costs,
  blocked orders, stale position-days, write-offs, recoveries, and benchmark comparison.
