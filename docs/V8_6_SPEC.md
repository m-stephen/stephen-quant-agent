# V8.6 Multi-source warehouse and factor discovery

## Objective

Make every declared directory below the machine-local QD asset root inspectable through an explicit
schema contract, immutable source lineage, DuckDB metadata and content-addressed Parquet. Replace
temporary extracted CSV inputs in automatic factor discovery with verified warehouse reads.

## Data contract

`DATASET_SPECS` declares all 19 folders and records the canonical dataset name, row grain, date and
entity keys, effective/available clocks, uniqueness rule, supported container types and optional
factor-source mapping. The 17 non-bar sources are stored as wide Parquet: every vendor column is
preserved as text and every observed header is registered by SHA-256. These normalized fields are
always present:

- `_dataset`, `_source_container`, `_source_container_sha256`, `_source_file`
- `_trade_date`, `_entity_id`, `_entity_name`
- `_effective_at`, `_available_at`, `_ingested_at`

Daily and minute bars keep their V8.4/V8.5 typed canonical adapters and share the same DuckDB
catalog. Text files, schema workbooks and unreadable vendor workbook wrappers are retained as hashed
provenance documents; they are never invented into observation rows.

## Integrity rules

- The source asset root is read-only and never committed.
- ZIP, 7z and RAR extraction occurs in temporary directories.
- Each source container, Parquet partition and schema variant is SHA-256 bound.
- Replaced source objects deactivate older partitions without deleting history.
- Unique daily/entity datasets are deterministically deduplicated across byte-identical backup
  files. Other grains retain all rows.
- Unparseable dated workbooks are registered as documents instead of silently discarded.
- PIT clocks are schema-fixed; warehouse timestamps are emitted as strict ISO-8601.
- A snapshot ID binds dataset specs, objects, partitions and schema variants.
- A no-change replay must write zero objects/rows and reproduce the same snapshot ID.

## Commands

```powershell
stephen-quant data-multisource-ingest `
  --paths-config configs/qd-warehouse-paths.local.json

stephen-quant data-multisource-verify `
  --paths-config configs/qd-warehouse-paths.local.json `
  --snapshot <snapshot-id>

stephen-quant --db artifacts/v8.6/registry.sqlite3 discover-alpha `
  --profile multi-source `
  --paths-config configs/qd-warehouse-paths.local.json `
  --output artifacts/v8.6/discovery
```

The ignored local config supplies `qd_asset_root`, `qd_warehouse_root`, the 7-Zip executable and
dynamic membership path. It must not be committed.

## Research protocol

Research uses 2022–2024 only. The continuous pass is direction-complete across daily, fund-flow,
margin, chip and cross-source proposals. The event pass includes auction candidates. Screening,
purged CPCV/PBO, placebo tests, costs, DSR and Alpha Court retain every Trial. Validation and final
test windows remain unopened during candidate generation.

