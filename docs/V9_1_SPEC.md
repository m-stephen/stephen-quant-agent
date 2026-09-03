# V9.1 Storage-efficient complete minute materialization

## Objective / 目标

Materialize every recognized local 1/5/15/30/60-minute archive into the verified DuckDB/Parquet
warehouse without modifying the source tree, exhausting disk space, or losing restartability.

将所有可识别的本地 1/5/15/30/60 分钟归档物化到可验证的 DuckDB/Parquet 仓库，同时不修改
原始目录、不耗尽磁盘，并保留断点续跑能力。

## Required gates / 强制门禁

- V9.0.1 Schema V2 must pass before full materialization resumes.
- Physical facts omit redundant row-level revision and derivable PIT columns; logical views restore
  the complete contract deterministically.
- Only the parent process writes DuckDB. Eight workers may parse source members in parallel.
- Every committed partition is content-addressed and linked to archive/member hashes.
- The source tree is read-only and local absolute paths remain Git-ignored.
- At least 100,000,000,000 free bytes must remain on the warehouse drive.
- A completed run must replay with zero pending archives and an unchanged snapshot ID.
- Final verification must validate every Parquet SHA-256, all rows, current-key uniqueness, and PIT
  timing before the PR can become Ready.

Implementation details inherited from the earlier engineering design remain in
[`V8_9_SPEC.md`](V8_9_SPEC.md); storage evidence is recorded in
[`V9_0_1_STORAGE_SCHEMA_V2_RESULT_EN.md`](V9_0_1_STORAGE_SCHEMA_V2_RESULT_EN.md) and
[`V9_0_1_STORAGE_SCHEMA_V2_RESULT_ZH.md`](V9_0_1_STORAGE_SCHEMA_V2_RESULT_ZH.md).
