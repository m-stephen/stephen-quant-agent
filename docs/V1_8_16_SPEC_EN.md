# V1.8.16 — Audited Automated Factor Discovery

## Objective

V1.8.16 turns factor research into a bounded, reproducible pipeline that can generate,
screen, falsify, and backtest structured factor candidates without opening the 2025
validation or 2026 final-test windows.

## Frozen workflow

1. Compile `FactorSchema` contracts with source/field validation and deterministic
   structural fingerprints.
2. Record every proposal, including duplicates, in a campaign ledger with frozen
   schema, CPCV, execution, and suite-wide Trial budgets.
3. Evaluate coverage, stability, redundancy, and training-only RankIC. Every measured
   candidate creates a Trial.
4. Align the eligible common panel and run purged/embargoed CPCV plus PBO.
5. Run cost-, capacity-, and tradability-aware Top-K execution only after the signal
   gate passes.
6. Apply signal-shuffle and return-permutation placebos, DSR with the global Trial
   count, PBO, and expanding walk-forward selection.
7. Produce immutable JSON plus detailed English and Chinese reports, research memory,
   an Alpha Card, and a fail-closed portfolio authorization result.

## Data and temporal boundaries

- Daily bars, fund flow, opening auction, margin financing, industry indices, dynamic
  universe membership, and normalized industry/concept membership have explicit
  effective, available, and ingestion semantics.
- Missing or stale alternative data cannot create a new position. Existing positions
  retain a liquidation channel. A missing held bar uses an explicit, conservative
  zero-return stale mark and blocks trading; the default baseline policy remains an
  error.
- AlphaPai is hypothesis-generation evidence only. Historical research reads exact,
  immutable cache entries with prompt/model/tool provenance. Cache misses, future
  references, incomplete streams, exhausted retries, and responses fetched after the
  decision time fail closed.
- Local paths, raw vendor data, generated reports, databases, credentials, and caches
  remain git-ignored.

## Research memory and portfolio gate

Research-only outcomes are persisted as success, failure, duplicate, invalid, or
screened-out experiences. The deterministic policy emits Explore, Exploit, and
single-dimension Mutate recommendations. Mutations carry the parent fingerprint and
must be evaluated in a newly frozen campaign; sealed-window feedback is never accepted.

Every execution winner receives an Alpha Card containing coverage, CPCV stability,
turnover, return, Sharpe, drawdown, costs, capacity assumptions, lineage, and exposure
status. Portfolio/PPO consumption is authorized only when both Alpha Court and
walk-forward gates pass. V1.8.16 does not add PPO, GNN, or live trading.

## Reproduction

Configure machine-specific paths in ignored `configs/qd-paths.local.json`, then run:

```powershell
python -m stephen_quant.cli --db artifacts/qd-v1.8.16.sqlite3 qd-auto-discover-suite `
  --paths-config configs/qd-paths.local.json `
  --suite-manifest configs/v1.8.16-suite.json `
  --ingested-at 2026-08-17T12:00:00+08:00 `
  --output reports/qd-v1.8.16
```

The command is successful when it completes and emits audited results. A factor may
still be rejected; rejection is a valid result and never opens a sealed window.
