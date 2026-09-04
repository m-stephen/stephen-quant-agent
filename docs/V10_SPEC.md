# V10.0 automatic alpha platform

V10 turns the verified warehouse into one reproducible research path:

```text
frozen minute snapshot
  -> monthly minute feature snapshots
  -> label-free cross-source candidate policy
  -> bounded empirical trials
  -> purged CPCV / PBO / DSR / placebo
  -> unified path, cost, capacity and execution court
```

## Minute feature factory

The registry contains price-path, volatility, VWAP, volume-shape, liquidity and
multi-scale features. Full-session observations are available only at the next
session open. Missing sessions are not filled; every row carries `bar_count_1m`,
`multiscale_intervals` and `quality_state`. Materialization is monthly to cap
memory, and every partition has an immutable source snapshot, policy identity,
Parquet SHA-256 and verifier.

No winsorization, standardization or residualization is fitted globally. Any
fitted transform belongs inside its training fold.

## Automatic generator

The generator is deterministic and label-free. It covers daily bars, minute
structure, fund flow, auction and chip inputs and emits bounded single-source,
two-source and selected three-source expressions. Candidate identity binds the
operator, typed fields and direction. Historical semantic identities can be
supplied as tombstones, preventing a failed idea from being silently retried.

The mechanism catalog includes flow/price divergence, auction price discovery,
intraday absorption, liquidity compensation, crowding reversal and multi-scale
divergence. An LLM may propose a hypothesis in future versions, but cannot alter
the policy snapshot or bypass the court.

## Unified Alpha Court

The existing immutable minimums remain in force: DSR at least 0.95, PBO and both
placebo p-values at most 0.05, at least CNY 3 million capacity, standard and
double-cost gates, purged/embargoed CPCV, walk-forward evidence, three-year and
three-regime breadth, return concentration, drawdown and minute-vs-daily
execution reconciliation. Missing evidence fails closed.

2025-2026 remain sealed. They may only be opened once for a candidate frozen
before that evaluation; they cannot be used to generate, select or tune a
replacement candidate.

## CLI

```text
stephen-quant v10-alpha-discover --paths-config configs/qd-warehouse-paths.local.json --minute-snapshot <sha256>
stephen-quant v10-alpha-test --warehouse-root <local-path> --feature-snapshot <sha256>
```

For a long monthly resume immediately after the same snapshot has successfully
passed `data-minute-verify`, `--reuse-verified-minute-snapshot` avoids repeating
the expensive full scan. It does not bypass partition manifests or feature
snapshot verification and must never be used with an unverified snapshot ID.

The first command verifies the source and builds/reuses monthly feature
partitions before freezing a candidate packet. The second records exactly one
Trial per tested candidate and emits JSON plus Chinese and English reports.

`PASS` is reserved for a complete sealed-forward court. Historical research can
only return `NO_RELIABLE_ALPHA` or a frozen candidate awaiting that court.
