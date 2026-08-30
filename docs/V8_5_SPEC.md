# V8.5 Database-native research and minute-bar warehouse

## Goal / 目标

Make the verified local warehouse the normal research input instead of repeatedly scanning source
CSV files. Standardize QD minute archives into immutable Parquet partitions indexed by DuckDB,
without modifying the source folder or committing machine-local paths.

以经校验的本地仓库作为默认研究入口，不再反复扫描源 CSV；同时把 QD 分钟 K 压缩包标准化为
不可变 Parquet 分区并由 DuckDB 建立索引。源目录保持只读，本机路径不进入 Git。

## Daily research contract / 日频研究契约

- `discover-alpha` defaults to `--profile daily` and prefers configured `qd_warehouse_root`.
- The current warehouse snapshot is verified before any bar is read.
- The verified snapshot SHA-256 is registered with the experiment and Trial ledger.
- `--profile multi-source` is explicit and fails closed while alternative datasets still lack
  canonical archive-to-warehouse schemas.
- A direct `daily_dir` remains available only as a compatibility input; exactly one daily source is
  accepted per run.

## Minute-bar contract / 分钟 K 契约

- Accepted intervals are 1, 5, 15, 30 and 60 minutes.
- ZIP and 7z/RAR sources are read without changing the source archive.
- Canonical fields are instrument, interval, event time, trading date, OHLC, volume, amount,
  source identity, source member and ingestion time.
- Event time is parsed in Asia/Shanghai and stored as a timezone-aware instant. Epoch-based staging
  prevents host/session timezone reinterpretation.
- Only A-share sessions are accepted; invalid OHLC, negative volume/amount and malformed rows are
  quarantined.
- Parquet paths are content-addressed and partitioned by interval/year/month/day.
- DuckDB retains batches, member lineage, active partitions, snapshots and quarantine evidence.
- Verification recomputes Parquet hashes and rejects duplicate current keys or PIT violations.
- Replaying the same source identities writes zero new revisions and returns the same snapshot.

## Commands / 命令

```powershell
stephen-quant data-update-weekly --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-minute-ingest --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-minute-verify --paths-config configs/qd-warehouse-paths.local.json --snapshot <ID>
stephen-quant discover-alpha --profile daily --paths-config configs/qd-warehouse-paths.local.json
stephen-quant data-warehouse-factor-test --paths-config configs/qd-warehouse-paths.local.json
```

## Scope boundary / 范围边界

V8.5 completes canonical database paths for daily bars and minute bars. Fund flow, auction, margin,
chip, limit-event and temporary industry sources remain inventoried but are not silently coerced
into guessed schemas. Their compressed-archive database adapters are subsequent dataset-specific
work. This boundary prevents a successful daily test from being misreported as a complete
multi-source migration.

V8.5 完成日 K 与分钟 K 的标准数据库通路。资金流、竞价、融资融券、筹码、涨跌停事件和临时行业
数据仍保留资产血缘，但尚未被强制映射到猜测 schema；它们需要逐数据集实现压缩包适配器。
