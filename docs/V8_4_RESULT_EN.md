# V8.4 Test Result

> Accepted on 2026-08-30. Generated warehouse files, absolute paths and raw data are excluded from Git.

## Acceptance gates

- Read-only source directory: **PASS**. Both runs produced the same asset snapshot and all outputs
  were written to a separate warehouse.
- Deterministic inventory: **PASS**. 74,855 files and 189,736,253,336 bytes. The second run reused
  all 74,855 cached hashes and retained snapshot
  `72ee5948d01255fb0860a596b5d64eefb1b0be72e5b0886916f36e14ccd8357a`.
- Provenance classes: 449 raw archives, 69,120 extracted archive members and 5,286 standalone files.
- Initial 2026 ingest: **PASS**. 149 trading-day files, 818,655 revisions and eight monthly
  partitions, covering 2026-01-05 through 2026-08-14 and 5,563 instruments.
- Full-history daily baseline: **PASS**. 1990-12-19 through 2026-08-14, 8,704 trading dates,
  5,884 instruments, 18,113,067 current rows and 429 active monthly partitions.
- Replay: **PASS**. Zero new source files, zero new revisions and the same snapshot ID.
- Snapshot integrity: **PASS**. Full-history snapshot
  `24f28d0a19061cf0fa088c7f8242eb69d0887e18b1227976f0131856bc4e4b61`, zero duplicate current
  keys, zero PIT timing violations and zero Parquet hash failures.
- Quarantine: 253 rows (232 missing required numeric values, 16 inconsistent lows and five
  inconsistent highs), about 0.0014% of current history. None entered canonical data and all evidence
  is snapshot-bound.
- Storage: 429 active Parquet files totaling 1,015,672,869 bytes; DuckDB catalog about 7.9MB.
- Regression suite: **580 passed, 1 skipped**; Ruff passed.

## Known limitations

- Six minute-bar 7z archives could not be listed by the local `tar` implementation. They are
  explicit inventory errors and do not affect this daily-bar acceptance.
- V8.4 canonicalizes daily bars only. Fund flow, auction, ranking and margin datasets are inventoried
  but require explicit schemas and PIT availability contracts before canonical ingestion.
- Deletion is historical, not destructive: a missing source file never erases an existing revision.
  Corrections append a revision and the current view selects the latest one.
