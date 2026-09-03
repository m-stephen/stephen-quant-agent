from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb


def _paths(
    warehouse: Path, interval: int, start_date: date | None, end_date: date | None
) -> list[str]:
    connection = duckdb.connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        rows = connection.execute(
            "SELECT parquet_relative_path FROM minute_partitions WHERE interval_minutes=? "
            "AND (?::DATE IS NULL OR trade_date>=?::DATE) "
            "AND (?::DATE IS NULL OR trade_date<=?::DATE) ORDER BY trade_date, parquet_relative_path",
            [interval, start_date, start_date, end_date, end_date],
        ).fetchall()
    finally:
        connection.close()
    return [str((warehouse / str(row[0])).resolve()) for row in rows]


def _literal(paths: list[str]) -> str:
    escaped = [path.replace("'", "''") for path in paths]
    return "[" + ",".join(f"'{path}'" for path in escaped) + "]"


def audit_interval(
    warehouse: Path,
    interval: int,
    start_date: date | None,
    end_date: date | None,
) -> dict[str, object]:
    one_paths = _paths(warehouse, 1, start_date, end_date)
    target_paths = _paths(warehouse, interval, start_date, end_date)
    if not one_paths or not target_paths:
        return {"interval_minutes": interval, "status": "NO_OVERLAP"}
    one = _literal(one_paths)
    target = _literal(target_paths)
    sql = f"""
    WITH one_local AS (
      SELECT trade_date, instrument, timezone('Asia/Shanghai', bar_at) AS local_at,
             "open", high, low, "close", volume, amount,
             CASE
               WHEN hour(timezone('Asia/Shanghai', bar_at)) * 60
                    + minute(timezone('Asia/Shanghai', bar_at)) BETWEEN 571 AND 690
                 THEN hour(timezone('Asia/Shanghai', bar_at)) * 60
                      + minute(timezone('Asia/Shanghai', bar_at)) - 570
               WHEN hour(timezone('Asia/Shanghai', bar_at)) * 60
                    + minute(timezone('Asia/Shanghai', bar_at)) BETWEEN 781 AND 900
                 THEN 120 + hour(timezone('Asia/Shanghai', bar_at)) * 60
                      + minute(timezone('Asia/Shanghai', bar_at)) - 780
             END AS session_minute
      FROM read_parquet({one})
    ), bucketed AS (
      SELECT *, CAST(ceil(session_minute / {interval}.0) * {interval} AS INTEGER) AS bucket
      FROM one_local WHERE session_minute IS NOT NULL
    ), resampled AS (
      SELECT trade_date, instrument,
             CAST(trade_date AS TIMESTAMP)
               + CASE WHEN bucket <= 120
                   THEN INTERVAL 9 HOUR + INTERVAL 30 MINUTE + bucket * INTERVAL 1 MINUTE
                   ELSE INTERVAL 13 HOUR + (bucket - 120) * INTERVAL 1 MINUTE END AS local_at,
             arg_min("open", session_minute) AS "open", max(high) AS high, min(low) AS low,
             arg_max("close", session_minute) AS "close", sum(volume) AS volume,
             sum(amount) AS amount, count(*) AS minute_rows
      FROM bucketed GROUP BY trade_date, instrument, bucket HAVING count(*)={interval}
    ), vendor AS (
      SELECT trade_date, instrument, timezone('Asia/Shanghai', bar_at) AS local_at,
             "open", high, low, "close", volume, amount
      FROM read_parquet({target})
    ), compared AS (
      SELECT v.*,
             r.instrument IS NOT NULL AS joined,
             abs(v."open"-r."open") <= 1e-8 AS open_ok,
             abs(v.high-r.high) <= 1e-8 AS high_ok,
             abs(v.low-r.low) <= 1e-8 AS low_ok,
             abs(v."close"-r."close") <= 1e-8 AS close_ok,
             abs(v.volume-r.volume) <= greatest(1e-6, abs(v.volume)*1e-9) AS volume_ok,
             abs(v.amount-r.amount) <= greatest(1e-4, abs(v.amount)*1e-9) AS amount_ok,
             abs(v.amount-r.amount) AS amount_abs_diff,
             abs(v.amount-r.amount) / greatest(1.0, abs(v.amount)) AS amount_relative_diff
      FROM vendor v LEFT JOIN resampled r USING (trade_date, instrument, local_at)
    )
    SELECT count(*) AS vendor_rows,
           count(*) FILTER (WHERE joined) AS joined_rows,
           count(*) FILTER (WHERE joined AND open_ok AND high_ok AND low_ok AND close_ok
                             AND volume_ok AND amount_ok) AS exact_rows,
           count(*) FILTER (WHERE joined AND NOT open_ok) AS open_mismatches,
           count(*) FILTER (WHERE joined AND NOT high_ok) AS high_mismatches,
           count(*) FILTER (WHERE joined AND NOT low_ok) AS low_mismatches,
           count(*) FILTER (WHERE joined AND NOT close_ok) AS close_mismatches,
           count(*) FILTER (WHERE joined AND NOT volume_ok) AS volume_mismatches,
           count(*) FILTER (WHERE joined AND NOT amount_ok) AS amount_mismatches,
           max(amount_abs_diff) FILTER (WHERE joined) AS max_amount_abs_diff,
           quantile_cont(amount_abs_diff, 0.99) FILTER (WHERE joined) AS p99_amount_abs_diff,
           max(amount_relative_diff) FILTER (WHERE joined) AS max_amount_relative_diff,
           quantile_cont(amount_relative_diff, 0.99) FILTER (WHERE joined)
             AS p99_amount_relative_diff
    FROM compared
    """
    connection = duckdb.connect()
    try:
        row = connection.execute(sql).fetchone()
    finally:
        connection.close()
    names = (
        "vendor_rows",
        "joined_rows",
        "exact_rows",
        "open_mismatches",
        "high_mismatches",
        "low_mismatches",
        "close_mismatches",
        "volume_mismatches",
        "amount_mismatches",
    )
    result = {name: int(value) for name, value in zip(names, row[: len(names)], strict=True)}
    result.update(
        {
            "max_amount_abs_diff": float(row[9] or 0.0),
            "p99_amount_abs_diff": float(row[10] or 0.0),
            "max_amount_relative_diff": float(row[11] or 0.0),
            "p99_amount_relative_diff": float(row[12] or 0.0),
        }
    )
    result.update(
        {
            "interval_minutes": interval,
            "status": "EQUIVALENT"
            if result["vendor_rows"] == result["exact_rows"]
            else "NOT_EQUIVALENT",
            "coverage_fraction": (
                result["joined_rows"] / result["vendor_rows"]
                if result["vendor_rows"]
                else 0.0
            ),
            "exact_fraction": (
                result["exact_rows"] / result["vendor_rows"]
                if result["vendor_rows"]
                else 0.0
            ),
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", required=True, type=Path)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--intervals", default="5,15,30,60")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.start_date and args.end_date and args.start_date > args.end_date:
        raise ValueError("start-date must not be after end-date")
    intervals = tuple(int(item) for item in args.intervals.split(","))
    if not intervals or any(item not in {5, 15, 30, 60} for item in intervals):
        raise ValueError("intervals must be selected from 5,15,30,60")
    results = [
        audit_interval(
            args.warehouse.resolve(), interval, args.start_date, args.end_date
        )
        for interval in intervals
    ]
    payload = {
        "status": "EQUIVALENT"
        if results and all(item["status"] == "EQUIVALENT" for item in results)
        else "NOT_EQUIVALENT",
        "start_date": args.start_date,
        "end_date": args.end_date,
        "results": results,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
