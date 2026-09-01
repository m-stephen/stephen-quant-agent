# V8.7 Available-minute coverage and safe synchronization

## Goal / 目标

V8.7 defines completeness as the data that is actually present and parseable in the local minute
archive folder. It does not synthesize missing trading days and does not claim exchange-calendar
completeness. V8.7 separates source availability from warehouse materialization so that an
incomplete source is not confused with an importer failure.

V8.7 将完整性定义为“本地分钟归档中实际存在且可解析的数据”，不补造缺失交易日，也不宣称
交易所日历完整。系统把源归档可用性与数据库物化状态分开，避免把源文件本身缺失误判为导入失败。

## Canonical schema / 标准字段

All 1/5/15/30/60-minute bars use `trade_date`, `bar_at`, `interval_minutes`, `instrument`,
`open`, `high`, `low`, `close`, `volume`, `amount`, `effective_at`, `available_at`,
`ingested_at`, archive/member SHA-256 lineage and `revision_id`.

## Archive catalog / 归档目录

`minute_archive_catalog` records the relative path, archive SHA-256, compressed size, format,
coverage type and range, interval hint, CSV member counts, selected member counts, uncompressed
bytes, materialized member counts and one of these states:

- `AVAILABLE`: source exists but has not been materialized.
- `PARTIAL`: only some recognized members have been materialized.
- `MATERIALIZED`: all recognized members for the selected intervals are registered.

The catalog is metadata only. It never copies raw QD files into Git.

## Commands / 命令

```text
stephen-quant data-minute-catalog --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-minute-sync-available --paths-config configs/qd-warehouse-paths.local.json \
  --start-date 2026-08-24 --end-date 2026-08-28
stephen-quant data-minute-verify --paths-config configs/qd-warehouse-paths.local.json \
  --snapshot <snapshot-id>
```

Daily archives are processed as isolated restartable batches. A repeated batch is a no-op. A
selected member that crosses the requested date boundary fails closed instead of being silently
truncated and then incorrectly marked as fully consumed.

## Storage policy / 存储策略

Observed 2000-2025 master archives contain about 365 GB of uncompressed CSV. Based on the current
real Parquet ratio, materializing every historical interval plus all 2026 daily archives would use
nearly all currently free E-drive space and leave unsafe temporary capacity. Therefore:

- new daily archives are the hot incremental path;
- historical bundles remain cataloged cold sources until a bounded backfill range is selected;
- `AVAILABLE` never means missing or rejected, and never means materialized.

