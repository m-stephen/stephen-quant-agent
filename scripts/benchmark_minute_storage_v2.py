from __future__ import annotations

import argparse
import json
import shutil
import statistics
import time
from pathlib import Path

import duckdb

from stephen_quant.qmt.minute_warehouse import _minute_relation_sql


def _literals(paths: list[Path]) -> str:
    return ",".join(f"'{str(path).replace(chr(39), chr(39) * 2)}'" for path in paths)


def _fingerprint(connection, relation: str) -> tuple[object, ...]:
    return connection.execute(
        "SELECT count(*), bit_xor(hash(trade_date, bar_at, interval_minutes, instrument, "
        '"open", high, low, "close", volume, amount, effective_at, available_at, '
        "ingested_at, archive_sha256, member_path, member_sha256)), min(bar_at), max(bar_at) "
        f"FROM ({relation})"
    ).fetchone()


def _query_seconds(
    connection, legacy_relation: str, compact_relation: str, repetitions: int
) -> tuple[float, float]:
    def query(relation: str) -> str:
        return (
        "SELECT instrument, avg(\"close\"), sum(volume) FROM ("
            f"{relation}) GROUP BY instrument ORDER BY instrument LIMIT 200"
        )

    queries = (query(legacy_relation), query(compact_relation))
    for _ in range(3):
        for item in queries:
            connection.execute(item).fetchall()
    durations: tuple[list[float], list[float]] = ([], [])
    for iteration in range(repetitions):
        order = (0, 1) if iteration % 2 == 0 else (1, 0)
        for index in order:
            started = time.perf_counter()
            connection.execute(queries[index]).fetchall()
            durations[index].append(time.perf_counter() - started)
    return statistics.median(durations[0]), statistics.median(durations[1])


def benchmark(
    warehouse: Path,
    archive_relative_path: str,
    output_dir: Path,
    repetitions: int,
    reuse_output: bool,
) -> dict[str, object]:
    catalog = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        relative_paths = [
            str(row[0])
            for row in catalog.execute(
                "SELECT parquet_relative_path FROM minute_range_partitions "
                "WHERE archive_relative_path=? ORDER BY parquet_relative_path",
                [archive_relative_path],
            ).fetchall()
        ]
    finally:
        catalog.close()
    if not relative_paths:
        raise ValueError("archive has no registered range partitions")
    legacy_paths = [(warehouse / relative).resolve() for relative in relative_paths]
    if output_dir.exists() and not reuse_output:
        raise ValueError(f"benchmark output already exists: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=reuse_output)
    connection = duckdb.connect()
    try:
        legacy_relation = _minute_relation_sql(
            connection, _literals(legacy_paths), revision_mode="none"
        )
        compact_paths = sorted(output_dir.glob("part-*.parquet")) if reuse_output else []
        if compact_paths and len(compact_paths) != len(legacy_paths):
            raise ValueError("reused benchmark output has an unexpected partition count")
        if not compact_paths:
            for index, legacy in enumerate(legacy_paths):
                raw = f"read_parquet('{str(legacy).replace(chr(39), chr(39) * 2)}')"
                compact = output_dir / f"part-{index:04d}.parquet"
                target = str(compact).replace("'", "''")
                connection.execute(
                    "COPY (SELECT trade_date, bar_at, interval_minutes, instrument, \"open\", "
                    "high, low, \"close\", volume, amount, ingested_at, archive_sha256, "
                    "member_path, member_sha256, CAST(2 AS UTINYINT) storage_schema_version "
                    f"FROM {raw}) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                compact_paths.append(compact)
        compact_relation = _minute_relation_sql(
            connection, _literals(compact_paths), revision_mode="none"
        )
        legacy_fingerprint = _fingerprint(connection, legacy_relation)
        compact_fingerprint = _fingerprint(connection, compact_relation)
    finally:
        connection.close()
    query_connection = duckdb.connect()
    try:
        legacy_relation = _minute_relation_sql(
            query_connection, _literals(legacy_paths), revision_mode="none"
        )
        compact_relation = _minute_relation_sql(
            query_connection, _literals(compact_paths), revision_mode="none"
        )
        legacy_seconds, compact_seconds = _query_seconds(
            query_connection, legacy_relation, compact_relation, repetitions
        )
    finally:
        query_connection.close()
    legacy_bytes = sum(path.stat().st_size for path in legacy_paths)
    compact_bytes = sum(path.stat().st_size for path in compact_paths)
    return {
        "archive_relative_path": archive_relative_path,
        "partition_count": len(legacy_paths),
        "row_count": int(legacy_fingerprint[0]),
        "fingerprint_equal": legacy_fingerprint == compact_fingerprint,
        "legacy_bytes": legacy_bytes,
        "compact_bytes": compact_bytes,
        "size_reduction_fraction": 1.0 - compact_bytes / legacy_bytes,
        "legacy_query_median_seconds": legacy_seconds,
        "compact_query_median_seconds": compact_seconds,
        "query_regression_fraction": compact_seconds / legacy_seconds - 1.0,
        "free_bytes_after": shutil.disk_usage(output_dir).free,
    }


def _select_archive(warehouse: Path, coverage_kind: str) -> str:
    connection = duckdb.connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        row = connection.execute(
            "SELECT c.archive_relative_path FROM minute_archive_catalog c "
            "JOIN minute_range_partitions p USING (archive_relative_path, archive_sha256) "
            "WHERE c.coverage_kind=? GROUP BY c.archive_relative_path "
            "ORDER BY sum(p.size_bytes) LIMIT 1",
            [coverage_kind],
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"no materialized range archive has coverage_kind={coverage_kind}")
    return str(row[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", required=True, type=Path)
    archive = parser.add_mutually_exclusive_group(required=True)
    archive.add_argument("--archive-relative-path")
    archive.add_argument(
        "--coverage-kind", choices=("annual", "historical_bundle", "unbounded")
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--reuse-output", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise ValueError("repetitions must be positive")
    warehouse = args.warehouse.resolve()
    archive_relative_path = args.archive_relative_path or _select_archive(
        warehouse, args.coverage_kind
    )
    result = benchmark(
        warehouse,
        archive_relative_path,
        args.output_dir.resolve(),
        args.repetitions,
        args.reuse_output,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
