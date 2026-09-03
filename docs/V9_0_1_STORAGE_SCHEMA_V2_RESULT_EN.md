# V9.0.1 Minute Storage Schema V2 Benchmark

Status: **Schema, Inventory, resampling decision, and full-migration gates pass.**

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

## Inventory cold archive

Three historical Inventory JSON files were converted to deterministic gzip after byte-for-byte SHA-256 decompression verification. The latest Inventory remains a hot JSON file:

- Plain JSON total: 4,514,007,467 bytes
- Compressed total: 84,427,596 bytes
- Reduction: 98.13%, releasing about 4.13 GiB
- Current Inventory directory: about 1.52 GiB

Future Inventory builds can still read cold manifests. A plain JSON file is removed only after its corresponding compressed file passes decompressed-hash verification.

## Multi-interval resampling audit

The full-market 1/5/15/30/60-minute data for 2026-08-28 was compared bucket by bucket. Time keys, OHLC, and volume match for every interval, but turnover amount cannot be reconstructed exactly from already-rounded one-minute amounts:

| Interval | Vendor rows | Fully equal | Amount mismatches | Maximum absolute difference |
|---|---:|---:|---:|---:|
| 5 minutes | 266,256 | 97.98% | 5,379 | 0.20 |
| 15 minutes | 88,752 | 96.06% | 3,495 | 0.40 |
| 30 minutes | 44,376 | 94.69% | 2,358 | 0.60 |
| 60 minutes | 22,188 | 93.58% | 1,425 | 0.70 |

Vendor 5/15/30/60-minute data must therefore be retained. One-minute resampling may be used for research features, but it must not be represented as the original vendor interval data.

## Full migration and verification

- Registered partitions: 1,040; already V2: 1; migrated in this run: 1,039.
- Physical minute Parquet fell from 132,528,331,617 bytes (123.43 GiB) to
  30,604,833,803 bytes (28.50 GiB), a 76.91% reduction.
- New snapshot: `57d3c90115c2106fb6746c78de38ad161b58b637304ba1cc7e7bd798f28b983a`.
- Full verification covered 2,510,466,687 rows. File SHA-256, row counts, and PIT timing
  passed. The deterministic `row_number(...)=1` current-row contract guarantees key
  uniqueness; duplicate current keys and timing violations are both zero.
- Every partition's business fingerprint was compared before migration. Its legacy file was
  removed only after the Catalog transaction committed. The pre-migration Catalog backup,
  migration ledger, and legacy-snapshot mappings remain available.
- The former global-window verifier spilled about 371 GiB at real scale. It was replaced by
  exact full-row streaming in fixed batches of 16 files. The new verifier used about 0.45 GiB
  resident memory; the obsolete spill files were removed precisely after the process exited.

## Next gate

- Issue #160 may close and V9.1 may resume only after the complete pytest suite, Ruff, and
  remote CI pass.
