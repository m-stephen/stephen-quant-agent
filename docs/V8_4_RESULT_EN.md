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
- Regression suite: **583 passed, 1 skipped**; Ruff passed.

## Known limitations

- Six minute-bar 7z archives could not be listed by the local `tar` implementation. They are
  explicit inventory errors and do not affect this daily-bar acceptance.
- V8.4 canonicalizes daily bars only. Fund flow, auction, ranking and margin datasets are inventoried
  but require explicit schemas and PIT availability contracts before canonical ingestion.
- Deletion is historical, not destructive: a missing source file never erases an existing revision.
  Corrections append a revision and the current view selects the latest one.

## 2026-08-31 full-folder replacement update

- New inventory: 11,469 files and 93,861,393,606 bytes; 429 raw archives, 5,546 extracted
  copies and 5,494 standalone source files.
- Asset snapshot: `2f8e3160b09337799a76b7a1668c4d67139a90082eb572c71b84c55b1a049305`.
- Fifteen daily sources produced 83,132 revisions. Ten dates from 2026-08-17 through 2026-08-28
  were new; five dates from 2026-08-10 through 2026-08-14 were overlapping metadata revisions.
- Overlapping sources changed zero OHLC, volume, amount or adjustment values. Eighteen names and
  five industry labels changed.
- Coverage now ends on 2026-08-28: 8,714 trading dates, 5,892 instruments and 18,168,503 current
  keys, with zero duplicate current keys and zero PIT timing violations.
- Warehouse snapshot: `9ba3320edf76036e5431c0360eed5bf54ca641936a3fa2f1ab12064019cfebd5`.
- No-change replay added zero files and zero revisions and retained both snapshots.
- Cross-manifest extracted lineage is regression-tested: removing an extracted copy while retaining
  the same archive no longer reimports the complete historical archive.

## 7z archive repair and organization

- Root cause: Windows `tar.exe` lacks the LZMA/LZMA2 codec used by these archives; none of the six
  files was corrupt.
- The adapter now resolves 7-Zip through ignored local configuration and uses structured listing and
  stdout extraction without writing into the source tree.
- All six archives passed 7-Zip CRC tests and yielded 27,141 members with 28,764,610,441
  uncompressed bytes.
- The complete inventory now indexes 4,516,991 archive members and `archive_error_count` fell from
  six to zero.
- New asset snapshot: `028dd17afe26d8c4efcf729bf8b7a3c6477e4b68680a337376ff9c42b1eb01e3`.
- Warehouse replay remained `REPLAY_NOOP`: zero new sources and revisions, with the warehouse
  snapshot and current keys unchanged.

## Direct warehouse-to-factor acceptance

- A read-only DuckDB research adapter now queries `qd_daily_current` directly; this path no longer
  scans the daily CSV directory.
- The warehouse snapshot was fully verified before reading. The 200-stock universe used only 2021
  mean traded value; the 2022 evaluation window did not influence selection. The only predeclared
  factor was `ret_20@1.0.0`, recorded as one Trial.
- The run read 61,699 rows and produced 48,048 observations over 242 evaluation sessions.
- Path verdict: `DATABASE_FACTOR_PATH_OPERATIONAL`.
- Factor diagnostic: mean RankIC -0.015806, RankICIR -1.019630, 44.63% positive RankIC sessions,
  and -0.078881% mean gross top-minus-bottom daily return. `ret_20` is not a usable alpha in this
  frozen window.
- This command tests connectivity, PIT signal construction and forward labels only. It does not
  replace CPCV, placebo, DSR/PBO, cost or Alpha Court gates.
