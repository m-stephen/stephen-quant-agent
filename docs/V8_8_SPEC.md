# V8.8 On-demand minute range loader

## Objective / 目标

Given a date range, minute interval and optional instrument allowlist, V8.8 automatically locates
the smallest applicable local archive set, checks prior materialization, extracts only required
historical members, writes immutable Parquet partitions and exposes the result through
`qd_minute_current`.

用户给出日期区间、分钟周期和股票列表后，系统自动定位最小源归档、检查已有覆盖、只抽取缺失
历史成员、写入不可变 Parquet，并通过 `qd_minute_current` 直接使用。

## Source routing / 源路由

- Observed daily archives are selected by their `YYYYMMDD` filename and loaded as restartable
  whole-day batches.
- Dates from 2000 through 2025 route to the matching 1/5/15/30/60-minute historical bundle.
- Historical requests require an explicit instrument allowlist. This prevents accidental expansion
  of hundreds of gigabytes.
- `max_source_bytes` is checked before extraction.
- Missing source members are returned as `source_gaps`; they are not parser failures.

## Partial-materialization contract / 局部物化契约

`minute_materialization_scopes` records archive/member SHA-256, interval, instrument, requested
start/end, materialized row count and batch lineage. A scoped load never marks an entire historical
member as fully consumed. Exact replay is a no-op. An overlapping request writes only dates not
covered by prior scopes.

## Command / 命令

```text
stephen-quant data-minute-ensure-range \
  --paths-config configs/qd-warehouse-paths.local.json \
  --start-date 2020-01-02 --end-date 2020-01-10 \
  --intervals 5 --instruments 000001.SZ \
  --max-source-bytes 100000000
```

Downstream code uses the same canonical view:

```sql
SELECT *
FROM qd_minute_current
WHERE interval_minutes = 5
  AND instrument = '000001.SZ'
  AND trade_date BETWEEN DATE '2020-01-02' AND DATE '2020-01-10'
ORDER BY bar_at;
```

The command returns actual row, instrument and trading-day coverage so callers can fail closed when
the requested source is absent or sparse.

