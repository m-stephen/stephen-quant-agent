# V8.4 Single-user incremental data warehouse

## Goal / 目标

Turn the existing QD archive and CSV folder into a reproducible local warehouse without changing
the source directory. The warehouse is optimized for one user and keeps integrity controls that
directly protect research validity.

将现有 QD 压缩包与 CSV 目录转换为可重复构建的本地数据仓库，且不改动源目录。仓库面向单机单用户，
仅保留直接保护研究可信度的完整性门禁。

## Storage contract / 存储契约

- The configured `qd_asset_root` is read-only. Inventory, extraction lineage and hashes are written
  to the separate configured `qd_warehouse_root`.
- Raw archives remain the source of record. Already-extracted files are classified by archive
  member name, uncompressed size and CRC32 where the archive format exposes it.
- Canonical daily bars are stored as immutable, content-addressed monthly Parquet partitions.
- DuckDB stores batches, source-file identities, active partition pointers and snapshots.
- Corrections append a new revision. They never overwrite the historical revision.
- A snapshot binds the source inventory and every active Parquet hash.
- Machine-local absolute paths live only in `configs/*.local.json`, which Git ignores.

## Commands / 命令

```powershell
pip install -e ".[warehouse]"
Copy-Item configs/qd-warehouse-paths.example.json configs/qd-warehouse-paths.local.json
# Edit only the local ignored file.

stephen-quant data-asset-inventory --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-warehouse-init --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-update-weekly --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-warehouse-verify --paths-config configs/qd-warehouse-paths.local.json --snapshot <ID>
```

For `.7z` archives, set `qd_7zip_executable` in the ignored local path config. The adapter uses
7-Zip structured listing and stdout extraction because Windows `tar.exe` may lack the required
LZMA/LZMA2 codec. The executable path is never recorded in a committed manifest.

The weekly command inventories the source folder, reuses cached hashes for unchanged files,
imports only unseen `(relative_path, sha256)` identities and verifies the resulting snapshot. A new
ZIP/7z/RAR may remain compressed: accepted daily CSV members are streamed into warehouse staging
without modifying the source tree. If an identical extracted copy is already present, archive
lineage prevents double ingestion.

Archive lineage is retained across inventory snapshots. If an extracted CSV disappears because a
user replaces the folder with the original archive, an unchanged archive member remains recognized
as already ingested. A packaging-only change therefore cannot trigger a full historical reimport.

每周命令会重新盘点源目录，对未变化文件复用哈希缓存，仅导入未见过的
`(relative_path, sha256)` 文件身份，并自动验证新快照。

## Current dataset coverage / 当前数据集覆盖

V8.4 ships the end-to-end path for `qd_daily` (`股票日K_按日期`). Other QD folders are inventoried
and retained with provenance, but are not silently coerced into a guessed schema. They will be added
dataset by dataset with explicit field contracts.

V8.4 首先完整支持 `qd_daily`（股票日K_按日期）。其他 QD 目录已纳入资产盘点和血缘记录，
但不会在没有字段契约时被强行转换；后续按数据集逐一增加显式 schema。

## Failure behavior / 失败行为

- File hash or byte size changed after inventory: reject.
- Missing required daily columns, invalid encoding or a file with no valid rows: reject before
  snapshot. Isolated row-level numeric/OHLC defects are excluded and hash-bound in quarantine.
- Snapshot or Parquet hash mismatch: verification fails.
- Replaying the same source manifest: zero new revisions and the same snapshot ID.
- A missing or failing 7-Zip executable: explicit archive error; never silently treated as empty.
