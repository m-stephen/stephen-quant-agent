# V8.9 Restartable full minute materialization

## Goal / 目标

Materialize every recognized local 1/5/15/30/60-minute archive without copying raw QD data into
Git, exhausting the E drive with a warehouse-sized staging file, or losing completed work after an
interruption.

将本地可识别的1/5/15/30/60分钟归档全部物化，同时保证原始QD数据不进入Git、暂存文件不会按
全仓规模膨胀，并且中断后可以从已完成归档和分块继续执行。

## Storage model / 存储模型

- Observed daily archives retain the existing date-partitioned `minute_partitions` path.
- Large annual and historical bundles use `minute_range_partitions`.
- A range partition contains a bounded group of complete instrument members and records its
  archive SHA-256, member SHA-256 identities, interval, date range, row count and Parquet hash.
- `qd_minute_revisions` unions both partition families; `qd_minute_current` resolves duplicate
  source revisions at `interval_minutes + instrument + bar_at` grain.
- All temporary extraction for RAR/7z archives is placed under the warehouse staging directory.

## Safety and replay / 安全与重放

- Default source-byte chunk: 512,000,000 bytes.
- Default free-space reserve: 100,000,000,000 bytes.
- Every committed chunk registers source members and its immutable Parquet file atomically.
- A restart skips already registered members; a complete replay returns no pending archives.
- CPU-heavy CSV parsing may use 1-16 spawned worker processes. Worker results are drained in
  deterministic source-member order and only the parent process writes DuckDB, so parallel parsing
  does not weaken replay ordering or create concurrent database writers.
- The source directory remains read-only. Local paths remain in the Git-ignored path config.

## Command / 命令

```text
stephen-quant data-minute-materialize-all \
  --paths-config configs/qd-warehouse-paths.local.json \
  --intervals 1,5,15,30,60 \
  --chunk-source-bytes 512000000 \
  --minimum-free-bytes 100000000000 \
  --parse-workers 6
```

`--parse-workers` defaults to `1` for backwards compatibility. On the current 12-core workstation,
a 12-member historical-minute sample containing 3,782,308 rows took 127.35 seconds with one parser
and 38.37 seconds with six parsers (`3.32x` faster), with identical canonical rows and revision IDs.
Six workers are therefore the recommended local full-materialization setting; DuckDB registration
and Parquet commit remain single-writer operations.

The command first refreshes the archive catalog and estimates Parquet capacity. Broad or unbounded
bundles are processed before historical bundles, annual archives and dated daily archives. This
ensures that more specific/newer archive families win deterministic current-view revision ordering.
It then refreshes the catalog and reports `COMPLETED` only when every selected archive is
`MATERIALIZED`.
