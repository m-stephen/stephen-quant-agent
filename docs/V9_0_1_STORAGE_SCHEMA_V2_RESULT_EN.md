# V9.0.1 Minute Storage Schema V2 Benchmark

Status: **The core minute-schema gate passes; Issue #160 remains in progress.**

## Design

- Physical Parquet no longer stores row-level `revision_id`, `effective_at`, or `available_at`.
- Compatibility views restore `effective_at = bar_at` and `available_at = bar_at + 1 second`.
- `revision_id` is deterministically derived from business values and source-member identity. Current-row selection uses batch time and source identity, so ordinary scans do not need to calculate SHA-256.
- Legacy and V2 Parquet files can coexist. Source hashes, member paths, member hashes, batch time, and snapshot hashes remain available.

## Real-data dual-write benchmark

| Scope | Rows | V1 | V2 | Size reduction | Query change | Data fingerprint |
|---|---:|---:|---:|---:|---:|---|
| Complete 2000 annual 5-minute archive | 5,571,408 | 247.45 MiB | 55.56 MiB | 77.55% | +2.45% | Equal |
| Cross-year 2009–2026 1-minute archive | 101,858,903 | 5.00 GiB | 1.06 GiB | 78.74% | +8.54% | Equal |

Both cases exceed the 40% minimum size-reduction gate, and both query regressions remain below 10%. The fingerprint covers business keys, OHLCV, PIT timestamps, ingestion time, and source identity. It intentionally excludes the revision string representation that changes with the storage schema.

## Tests

- Minute warehouse: 8 passed
- Full suite: 594 passed, 1 skipped
- Ruff: passed

The first full-suite run was correctly blocked by AlphaPai maintenance variables inherited from a local maintenance process. The suite passed after those variables were removed from the test process. No credential was written to code, reports, or Git.

## Remaining work

- Lossless cold compression for historical Inventory snapshots.
- Equivalence audit between vendor 1/5/15/30/60-minute bars and deterministic resampling.
- Resume full materialization on Schema V2, migrate legacy partitions precisely, and run final snapshot, replay, CI, and release gates.

