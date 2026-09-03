# V9.2 Shenwan Level-2 PIT-Lite warehouse

## Scope

V9.2 stores annual Shenwan Level-2 industry membership snapshots in the local
DuckDB/Parquet warehouse before V10 research begins. It preserves source bytes,
SHA-256 manifests, deterministic membership rows, annual changes and coverage
grades.

This source is **PIT-Lite**, not event-level PIT:

- the supplied file contains year-end snapshots rather than exact constituent
  entry and exit timestamps;
- 2020 is explicitly `PARTIAL` because its coverage is materially incomplete;
- 2021-2024 may be used only with the annual proxy timing disclosed in the
  manifest;
- 2025-2026 are stored but `sealed=true`; candidate generation and tuning must
  not read them;
- the dataset therefore narrows, but does not close, Issue #92.

## Commands

Local paths remain in a Gitignored `configs/*.local.json` file:

```json
{
  "version": 1,
  "paths": {
    "qd_warehouse_root": "D:/local-warehouse",
    "sw_l2_history_json": "D:/local-source/sw_l2_history.json"
  }
}
```

Initial or manually refreshed local-file ingest:

```text
stephen-quant data-sw-l2-ingest --paths-config configs/qd-warehouse-paths.local.json
```

Verification:

```text
stephen-quant data-sw-l2-verify --paths-config configs/qd-warehouse-paths.local.json --snapshot <snapshot-id>
```

Weekly HTTP refresh, suitable for Windows Task Scheduler:

```text
stephen-quant data-sw-l2-fetch --paths-config configs/qd-warehouse-paths.local.json --source-url <https-json-url>
```

The HTTP adapter supports ETag and Last-Modified conditional requests, a timeout,
a response-size ceiling, content-type validation and content-addressed no-op
replay. The supplied `index.html` currently fetches a static relative JSON file;
it does not itself expose a remote collection API. A real weekly fetch URL must
therefore be configured when the upstream page publishes one. Until then, the
local-file command safely ingests each newly generated JSON export.

## Warehouse objects

- `sw_l2_snapshots`: immutable snapshot and artifact lineage;
- `sw_l2_year_quality`: annual counts, grade and sealed state;
- `sw_l2_changes`: deterministic annual added/removed/reclassified evidence;
- `qd_sw_l2_membership_revisions`: all immutable revisions;
- `qd_sw_l2_membership_current`: latest retrieved revision for each year/stock;
- `sw_l2_remote_state`: hashed endpoint state for conditional weekly updates.

No raw source, machine-local path or endpoint URL is committed to Git.
