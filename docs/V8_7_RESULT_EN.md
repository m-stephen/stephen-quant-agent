# V8.7 final test report

## Verdict

The minute schema, archive catalog, incremental synchronization, replay guard and snapshot
verification are implemented and passing. Source gaps are allowed but disclosed. The database
currently materializes five observed days from 2026-08-24 through 2026-08-28; it does not claim
that all of 2026 is loaded.

## Dataset and grain

- Dataset: local QD minute archives, read-only source.
- Grain: `interval_minutes + instrument + bar_at`.
- Intervals: 1, 5, 15, 30 and 60 minutes.
- Catalog: 194 recognized archives; 5 `MATERIALIZED`, 189 `AVAILABLE`.
- Materialized members: 138,660; recognized members awaiting materialization: 4,308,931.
- Hot store: 25 Parquet partitions, approximately 285 MB.

| Interval | Rows | Observed days | Coverage |
|---:|---:|---:|---|
| 1 minute | 6,655,680 | 5 | 2026-08-24 to 2026-08-28 |
| 5 minutes | 1,331,136 | 5 | same |
| 15 minutes | 443,712 | 5 | same |
| 30 minutes | 221,856 | 5 | same |
| 60 minutes | 110,928 | 5 | same |
| Total | 8,763,312 | 5 | same |

## Integrity checks

- Snapshot: `bd1c0ee2b45a34cbbf4ffe1054a7d40f1067887751d849a73c3f18dd4bb32f58`.
- Snapshot and partition hashes: pass.
- Duplicate current keys: 0.
- PIT timing violations: 0.
- Quarantined rows in the real batches: 0.
- Same-day replay: 0 new members, 0 new revisions and unchanged snapshot.
- Tests: 588 passed, 1 skipped.
- Ruff: all checks passed.

## Gaps and severity

1. **High, confirmed:** 189 archives remain unmaterialized. This is an explicit backlog, not an
   importer failure.
2. **High, confirmed:** the historical master bundles contain about 365 GB of uncompressed CSV.
   One-shot materialization would consume nearly all free E-drive capacity.
3. **Medium, confirmed:** one daily archive contains about 27,000 small CSV files and takes roughly
   five minutes with the low-memory integrity path. This is suitable for weekly increments, not an
   interactive first-time annual backfill.
4. **Low, confirmed:** two initial regression failures were expected policy rejections caused by
   AlphaPai variables injected into the desktop process. With those variables removed only in the
   test subprocess, all 588 tests passed.

These dates were used for data-engineering validation only, not factor tuning or Alpha Court
threshold changes.
