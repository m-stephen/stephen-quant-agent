from __future__ import annotations

import csv
import hashlib
import io
import json
import multiprocessing
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from collections import defaultdict
from concurrent.futures import Future, ProcessPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path, PurePosixPath

from .asset_inventory import _archive_members
from .data_warehouse import _atomic_json, _duckdb, _sha256, initialize_warehouse
from .models import QmtDataError

MINUTE_SCHEMA_VERSION = 2
MINUTE_PARQUET_SCHEMA_VERSION = 2
MINUTE_FOLDER = "分钟K线合集"
MINUTE_INTERVALS = (1, 5, 15, 30, 60)
_INTERVAL = re.compile(r"(?<!\d)(1|5|15|30|60)\s*(?:min|分钟)", re.IGNORECASE)
_INSTRUMENT = re.compile(r"^(bj|sh|sz)(\d{6})$", re.IGNORECASE)
_DATE_STEM = re.compile(r"^(20\d{6})$")
_YEAR = re.compile(r"^(20\d{2})$")
_SHANGHAI = timezone(timedelta(hours=8))
_MemberParseResult = tuple[
    int,
    list[tuple[str, str]],
    str,
    str | None,
    str | None,
    float | None,
    float | None,
]


def initialize_minute_warehouse(root: str | Path) -> None:
    warehouse = Path(root).expanduser().resolve()
    initialize_warehouse(warehouse)
    (warehouse / "minute-snapshots").mkdir(exist_ok=True)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_batches (batch_id VARCHAR PRIMARY KEY, "
            "started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, status VARCHAR, "
            "snapshot_id VARCHAR, new_archives BIGINT, new_members BIGINT, new_revisions BIGINT, "
            "quarantined_rows BIGINT, error VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_source_members (archive_relative_path VARCHAR, "
            "archive_sha256 VARCHAR, archive_size_bytes BIGINT, member_path VARCHAR, "
            "member_sha256 VARCHAR, member_size_bytes BIGINT, interval_minutes INTEGER, "
            "batch_id VARCHAR, PRIMARY KEY(archive_relative_path, archive_sha256, member_path))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_partitions (interval_minutes INTEGER, "
            "trade_date DATE, parquet_relative_path VARCHAR PRIMARY KEY, sha256 VARCHAR, "
            "size_bytes BIGINT, row_count BIGINT, min_bar_at TIMESTAMPTZ, max_bar_at TIMESTAMPTZ, "
            "batch_id VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_range_partitions (partition_id VARCHAR PRIMARY KEY, "
            "archive_relative_path VARCHAR, archive_sha256 VARCHAR, interval_minutes INTEGER, "
            "parquet_relative_path VARCHAR UNIQUE, sha256 VARCHAR, size_bytes BIGINT, "
            "row_count BIGINT, min_date DATE, max_date DATE, min_bar_at TIMESTAMPTZ, "
            "max_bar_at TIMESTAMPTZ, batch_id VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_snapshots (snapshot_id VARCHAR PRIMARY KEY, "
            "manifest_sha256 VARCHAR, created_at TIMESTAMPTZ, manifest_relative_path VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_quarantines (batch_id VARCHAR, source_identity VARCHAR, "
            "reason VARCHAR, row_sha256 VARCHAR, created_at TIMESTAMPTZ)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_archive_catalog (archive_relative_path VARCHAR, "
            "archive_sha256 VARCHAR, archive_size_bytes BIGINT, archive_format VARCHAR, "
            "coverage_kind VARCHAR, coverage_start DATE, coverage_end DATE, interval_hint INTEGER, "
            "csv_member_count BIGINT, selected_member_count BIGINT, uncompressed_bytes BIGINT, "
            "materialized_member_count BIGINT, materialization_status VARCHAR, inventoried_at TIMESTAMPTZ, "
            "PRIMARY KEY(archive_relative_path, archive_sha256))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS minute_materialization_scopes (scope_id VARCHAR PRIMARY KEY, "
            "archive_relative_path VARCHAR, archive_sha256 VARCHAR, member_path VARCHAR, "
            "member_sha256 VARCHAR, interval_minutes INTEGER, instrument VARCHAR, "
            "scope_start DATE, scope_end DATE, row_count BIGINT, batch_id VARCHAR, created_at TIMESTAMPTZ, "
            "UNIQUE(archive_relative_path, archive_sha256, member_path, member_sha256, "
            "scope_start, scope_end))"
        )
    finally:
        connection.close()


def _archive_in_range(path: Path, start: date | None, end: date | None) -> bool:
    match = _DATE_STEM.match(path.stem)
    if match:
        day = date.fromisoformat(
            f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        )
        return not ((start and day < start) or (end and day > end))
    years = [int(part) for part in path.parts if _YEAR.match(part)]
    if years:
        year = years[-1]
        return not ((start and year < start.year) or (end and year > end.year))
    if "2000-2025" in path.parts:
        return not ((start and start.year > 2025) or (end and end.year < 2000))
    return start is None and end is None


def _selected_archives(source_root: Path, start: date | None, end: date | None) -> tuple[Path, ...]:
    minute_root = source_root / MINUTE_FOLDER
    if not minute_root.is_dir():
        raise QmtDataError(f"minute archive root is missing: {minute_root}")
    return tuple(
        path
        for path in sorted(minute_root.rglob("*"), key=lambda item: item.as_posix().casefold())
        if path.is_file()
        and path.suffix.lower() in {".zip", ".7z", ".rar"}
        and _archive_in_range(path, start, end)
        and path.name != "全部复权因子.zip"
    )


def _archive_coverage(path: Path) -> tuple[str, date | None, date | None]:
    match = _DATE_STEM.match(path.stem)
    if match:
        day = date.fromisoformat(
            f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
        )
        return "daily", day, day
    years = [int(part) for part in path.parts if _YEAR.match(part)]
    if years:
        year = years[-1]
        return "annual", date(year, 1, 1), date(year, 12, 31)
    if "2000-2025" in path.parts:
        return "historical_bundle", date(2000, 1, 1), date(2025, 12, 31)
    return "unbounded", None, None


def catalog_minute_archives(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    """Inventory every available minute archive without assuming calendar completeness."""
    requested = tuple(sorted(set(intervals)))
    if not requested or any(item not in MINUTE_INTERVALS for item in requested):
        raise QmtDataError(f"minute intervals must be selected from {MINUTE_INTERVALS}")
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    seven_zip = (
        Path(seven_zip_executable).expanduser().resolve() if seven_zip_executable else None
    )
    initialize_minute_warehouse(warehouse)
    archives = _selected_archives(source, None, None)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    now = datetime.now(timezone.utc)
    rows: list[tuple[object, ...]] = []
    try:
        fully_materialized = {
            (str(row[0]), str(row[1])): int(row[2])
            for row in connection.execute(
                "SELECT archive_relative_path, archive_sha256, count(*) "
                "FROM minute_source_members GROUP BY 1,2"
            ).fetchall()
        }
        scoped_members = {
            (str(row[0]), str(row[1])): int(row[2])
            for row in connection.execute(
                "SELECT archive_relative_path, archive_sha256, count(DISTINCT member_path) "
                "FROM minute_materialization_scopes GROUP BY 1,2"
            ).fetchall()
        }
        for archive in archives:
            relative = archive.relative_to(source).as_posix()
            archive_sha = _sha256(archive)
            listed = _archive_members(archive, seven_zip)
            csv_members = [item for item in listed if item[0].lower().endswith(".csv")]
            selected = [
                item
                for item in csv_members
                if _interval(item[0], archive) in requested and _instrument(item[0]) is not None
            ]
            coverage_kind, coverage_start, coverage_end = _archive_coverage(archive)
            interval_hint = _interval(archive.stem, archive)
            fully_done = fully_materialized.get((relative, archive_sha), 0)
            scoped_done = scoped_members.get((relative, archive_sha), 0)
            observed_done = max(fully_done, scoped_done)
            status = "MATERIALIZED" if selected and fully_done >= len(selected) else (
                "PARTIAL" if observed_done else "AVAILABLE"
            )
            rows.append(
                (
                    relative,
                    archive_sha,
                    archive.stat().st_size,
                    archive.suffix.lower().lstrip("."),
                    coverage_kind,
                    coverage_start,
                    coverage_end,
                    interval_hint,
                    len(csv_members),
                    len(selected),
                    sum(int(item[1]) for item in selected),
                    observed_done,
                    status,
                    now,
                )
            )
        connection.execute("BEGIN TRANSACTION")
        connection.execute("DELETE FROM minute_archive_catalog")
        connection.executemany(
            "INSERT OR REPLACE INTO minute_archive_catalog VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.execute("COMMIT")
        summary_rows = connection.execute(
            "SELECT materialization_status, count(*), sum(selected_member_count), "
            "sum(uncompressed_bytes) FROM minute_archive_catalog GROUP BY 1 ORDER BY 1"
        ).fetchall()
    finally:
        connection.close()
    return {
        "archive_count": len(rows),
        "summaries": [
            {
                "status": str(row[0]),
                "archive_count": int(row[1]),
                "selected_member_count": int(row[2] or 0),
                "uncompressed_bytes": int(row[3] or 0),
            }
            for row in summary_rows
        ],
        "coverage_semantics": "observed archives only; no exchange-calendar completeness claim",
    }


def sync_available_daily_minutes(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    """Materialize each observed daily archive as an isolated, restartable batch."""
    source = Path(source_root).expanduser().resolve()
    archives = [
        path
        for path in _selected_archives(source, start_date, end_date)
        if _archive_coverage(path)[0] == "daily"
    ]
    observed_days = sorted(
        {day for path in archives if (day := _archive_coverage(path)[1]) is not None}
    )
    if not observed_days:
        raise QmtDataError("no daily minute archives match the requested range")
    batches: list[dict[str, object]] = []
    for day in observed_days:
        batches.append(
            ingest_minute_archives(
                source,
                warehouse_root,
                start_date=day,
                end_date=day,
                intervals=intervals,
                seven_zip_executable=seven_zip_executable,
            )
        )
    completed = [item for item in batches if item["status"] == "COMPLETED"]
    latest_snapshot = next(
        (item.get("snapshot_id") for item in reversed(batches) if item.get("snapshot_id")), None
    )
    return {
        "status": "COMPLETED",
        "coverage_semantics": "observed daily archives only; gaps are not synthesized",
        "observed_trade_days": len(observed_days),
        "coverage_start": observed_days[0].isoformat(),
        "coverage_end": observed_days[-1].isoformat(),
        "completed_batches": len(completed),
        "replay_noop_batches": len(batches) - len(completed),
        "new_members": sum(int(item.get("new_members", 0)) for item in completed),
        "new_revisions": sum(int(item.get("new_revisions", 0)) for item in completed),
        "quarantined_rows": sum(int(item.get("quarantined_rows", 0)) for item in completed),
        "snapshot_id": latest_snapshot,
    }


def _interval(path: str, archive: Path) -> int | None:
    match = _INTERVAL.search(path.replace("\\", "/")) or _INTERVAL.search(archive.stem)
    return int(match.group(1)) if match else None


def _instrument(member_path: str) -> str | None:
    match = _INSTRUMENT.match(PurePosixPath(member_path.replace("\\", "/")).stem)
    if not match:
        return None
    return f"{match.group(2)}.{match.group(1).upper()}"


def _decode(raw: bytes, source: str) -> str:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            text = raw.decode(encoding)
        except UnicodeError:
            continue
        if "日期" in text.splitlines()[0] and "时间" in text.splitlines()[0]:
            return text
    raise QmtDataError(f"unsupported minute CSV encoding: {source}")


def _parse_day(value: str) -> date:
    normalized = value.strip().replace("/", "-")
    if len(normalized) == 8 and normalized.isdigit():
        normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:]}"
    return date.fromisoformat(normalized)


def _parse_clock(value: str) -> time:
    normalized = value.strip()
    if ":" in normalized:
        try:
            return time.fromisoformat(normalized)
        except ValueError:
            pass
    if normalized.isdigit() and len(normalized) in {4, 6}:
        return time(
            int(normalized[:2]),
            int(normalized[2:4]),
            int(normalized[4:6]) if len(normalized) == 6 else 0,
        )
    raise ValueError("invalid clock")


def _iter_member_records(
    raw: bytes,
    *,
    identity: str,
    member_path: str,
    instrument: str,
    interval: int,
    archive_sha256: str,
    member_sha256: str,
    ingested_at: datetime,
):
    reader = csv.DictReader(io.StringIO(_decode(raw, identity), newline=""))
    aliases = {
        "日期": "trade_date",
        "时间": "bar_time",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
    }
    mapping = {name.strip(): aliases.get(name.strip()) for name in (reader.fieldnames or ())}
    if set(mapping.values()) - {None} != set(aliases.values()):
        raise QmtDataError(f"minute CSV schema mismatch: {identity}")
    seen: set[str] = set()
    for number, raw_row in enumerate(reader, start=2):
        values = {
            canonical: (raw_row.get(source) or "").strip()
            for source, canonical in mapping.items()
            if canonical
        }
        reason: str | None = None
        try:
            trade_day = _parse_day(values["trade_date"])
            clock = _parse_clock(values["bar_time"])
            numeric = {
                key: float(values[key])
                for key in ("open", "high", "low", "close", "volume", "amount")
            }
        except (KeyError, ValueError):
            reason = "invalid minute value"
        if reason is None and not (
            time(9, 30) <= clock <= time(11, 30) or time(13, 0) <= clock <= time(15, 0)
        ):
            reason = "bar timestamp outside A-share session"
        if reason is None and min(numeric[key] for key in ("open", "high", "low", "close")) <= 0:
            reason = "non-positive OHLC"
        if reason is None and numeric["high"] < max(
            numeric["open"], numeric["low"], numeric["close"]
        ):
            reason = "inconsistent high"
        if reason is None and numeric["low"] > min(
            numeric["open"], numeric["high"], numeric["close"]
        ):
            reason = "inconsistent low"
        if reason is None and (numeric["volume"] < 0 or numeric["amount"] < 0):
            reason = "negative volume or amount"
        if reason is not None:
            row_hash = hashlib.sha256(
                json.dumps(raw_row, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            yield None, (f"row {number}: {reason}", row_hash)
            continue
        bar_at = datetime.combine(trade_day, clock, tzinfo=_SHANGHAI)
        key = bar_at.isoformat()
        if key in seen:
            row_hash = hashlib.sha256(
                json.dumps(raw_row, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            yield None, (f"row {number}: duplicate member key", row_hash)
            continue
        seen.add(key)
        stable = {
            "trade_date": trade_day.isoformat(),
            "bar_at": bar_at.isoformat(),
            "interval_minutes": interval,
            "instrument": instrument,
            **numeric,
            "effective_at": bar_at.isoformat(),
            "available_at": (bar_at + timedelta(seconds=1)).isoformat(),
            "archive_sha256": archive_sha256,
            "member_path": member_path.replace("\\", "/"),
            "member_sha256": member_sha256,
        }
        revision_id = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        yield {
            **stable,
            "bar_at_epoch": bar_at.timestamp(),
            "effective_at_epoch": bar_at.timestamp(),
            "available_at_epoch": (bar_at + timedelta(seconds=1)).timestamp(),
            "ingested_at_epoch": ingested_at.timestamp(),
            "revision_id": revision_id,
            "ingested_at": ingested_at.isoformat(),
        }, None


def _parse_member(
    raw: bytes,
    *,
    identity: str,
    member_path: str,
    instrument: str,
    interval: int,
    archive_sha256: str,
    member_sha256: str,
    ingested_at: datetime,
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    rows: list[dict[str, object]] = []
    quarantines: list[tuple[str, str]] = []
    for row, rejected in _iter_member_records(
        raw,
        identity=identity,
        member_path=member_path,
        instrument=instrument,
        interval=interval,
        archive_sha256=archive_sha256,
        member_sha256=member_sha256,
        ingested_at=ingested_at,
    ):
        if row is not None:
            rows.append(row)
        elif rejected is not None:
            quarantines.append(rejected)
    return rows, quarantines


def _parse_member_to_jsonl(
    raw: bytes,
    *,
    output_path: str,
    identity: str,
    member_path: str,
    instrument: str,
    interval: int,
    archive_sha256: str,
    ingested_at: datetime,
) -> _MemberParseResult:
    """Parse one member in an isolated worker and persist deterministic JSONL evidence."""
    member_sha = hashlib.sha256(raw).hexdigest()
    row_count = 0
    min_date: str | None = None
    max_date: str | None = None
    min_bar_epoch: float | None = None
    max_bar_epoch: float | None = None
    quarantines: list[tuple[str, str]] = []
    target = Path(output_path)
    with target.open("w", encoding="utf-8") as handle:
        for parsed, rejected in _iter_member_records(
            raw,
            identity=identity,
            member_path=member_path,
            instrument=instrument,
            interval=interval,
            archive_sha256=archive_sha256,
            member_sha256=member_sha,
            ingested_at=ingested_at,
        ):
            if parsed is not None:
                handle.write(json.dumps(parsed, separators=(",", ":")) + "\n")
                row_count += 1
                trade_date = str(parsed["trade_date"])
                bar_epoch = float(parsed["bar_at_epoch"])
                min_date = trade_date if min_date is None else min(min_date, trade_date)
                max_date = trade_date if max_date is None else max(max_date, trade_date)
                min_bar_epoch = (
                    bar_epoch if min_bar_epoch is None else min(min_bar_epoch, bar_epoch)
                )
                max_bar_epoch = (
                    bar_epoch if max_bar_epoch is None else max(max_bar_epoch, bar_epoch)
                )
            elif rejected is not None:
                quarantines.append(rejected)
    return (
        row_count,
        quarantines,
        member_sha,
        min_date,
        max_date,
        min_bar_epoch,
        max_bar_epoch,
    )


def _write_minute_parquet(connection, staging: Path, target: Path) -> None:
    source_sql = str(staging).replace("'", "''")
    target_sql = str(target).replace("'", "''")
    connection.execute(
        "COPY (SELECT CAST(trade_date AS DATE) trade_date, to_timestamp(bar_at_epoch) bar_at, "
        "CAST(interval_minutes AS INTEGER) interval_minutes, instrument, "
        'CAST("open" AS DOUBLE) "open", CAST(high AS DOUBLE) high, CAST(low AS DOUBLE) low, '
        'CAST("close" AS DOUBLE) "close", CAST(volume AS DOUBLE) volume, CAST(amount AS DOUBLE) amount, '
        "to_timestamp(ingested_at_epoch) ingested_at, archive_sha256, member_path, member_sha256, "
        f"CAST({MINUTE_PARQUET_SCHEMA_VERSION} AS UTINYINT) storage_schema_version "
        f"FROM read_json_auto('{source_sql}')) TO '{target_sql}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _revision_v2_expression() -> str:
    return (
        "sha256(concat_ws('|', 'minute-parquet-v2', CAST(bar_at AS VARCHAR), "
        "CAST(interval_minutes AS VARCHAR), instrument, CAST(\"open\" AS VARCHAR), "
        "CAST(high AS VARCHAR), CAST(low AS VARCHAR), CAST(\"close\" AS VARCHAR), "
        "CAST(volume AS VARCHAR), CAST(amount AS VARCHAR), archive_sha256, member_path, "
        "member_sha256))"
    )


def _minute_relation_sql(
    connection, literals: str, *, revision_mode: str = "logical"
) -> str:
    """Return the stable logical contract for legacy, V2, or mixed Parquet files."""
    if revision_mode not in {"logical", "stored", "none"}:
        raise ValueError(f"unsupported minute revision mode: {revision_mode}")
    raw = f"read_parquet([{literals}], union_by_name=true)"
    columns = {
        str(row[0])
        for row in connection.execute(f"DESCRIBE SELECT * FROM {raw}").fetchall()
    }

    def compatible(name: str, derived: str) -> str:
        return f"coalesce({name}, {derived})" if name in columns else derived

    effective_at = compatible("effective_at", "bar_at")
    available_at = compatible("available_at", "bar_at + INTERVAL 1 SECOND")
    revision_sql = ""
    if revision_mode == "logical":
        revision_sql = f", {compatible('revision_id', _revision_v2_expression())} AS revision_id"
    elif revision_mode == "stored":
        stored = "revision_id" if "revision_id" in columns else "NULL::VARCHAR"
        revision_sql = f", {stored} AS stored_revision_id"
    return (
        "SELECT trade_date, bar_at, interval_minutes, instrument, \"open\", high, low, "
        "\"close\", volume, amount, "
        f"{effective_at} AS effective_at, {available_at} AS available_at, ingested_at, "
        f"archive_sha256, member_path, member_sha256{revision_sql} FROM {raw}"
    )


def _insert_quarantines(
    connection,
    *,
    quarantines: list[tuple[str, str, str]],
    batch_id: str,
    started: datetime,
    staging: Path,
) -> None:
    """Bulk-load quarantine evidence without row-at-a-time DuckDB calls."""
    if not quarantines:
        return
    quarantine_staging = staging.with_name(f"{staging.name}.quarantines.jsonl")
    try:
        with quarantine_staging.open("w", encoding="utf-8") as handle:
            for identity, reason, row_hash in quarantines:
                handle.write(
                    json.dumps(
                        {
                            "batch_id": batch_id,
                            "source_identity": identity,
                            "reason": reason,
                            "row_sha256": row_hash,
                            "created_at_epoch": started.timestamp(),
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        source_sql = str(quarantine_staging).replace("'", "''")
        connection.execute(
            "INSERT INTO minute_quarantines SELECT batch_id, source_identity, reason, "
            f"row_sha256, to_timestamp(created_at_epoch) FROM read_json_auto('{source_sql}')"
        )
    finally:
        quarantine_staging.unlink(missing_ok=True)


def _refresh_views(connection, warehouse: Path) -> None:
    daily_paths = [
        str(warehouse / row[0]).replace("'", "''")
        for row in connection.execute(
            "SELECT parquet_relative_path FROM minute_partitions ORDER BY parquet_relative_path"
        ).fetchall()
    ]
    range_paths = [
        str(warehouse / row[0]).replace("'", "''")
        for row in connection.execute(
            "SELECT parquet_relative_path FROM minute_range_partitions ORDER BY parquet_relative_path"
        ).fetchall()
    ]
    paths = daily_paths + range_paths
    if not paths:
        return
    literals = ",".join(f"'{path}'" for path in paths)
    relation = _minute_relation_sql(connection, literals)
    connection.execute(
        f"CREATE OR REPLACE VIEW qd_minute_revisions AS {relation}"
    )
    base = _minute_relation_sql(connection, literals, revision_mode="stored")
    revision_v2 = _revision_v2_expression()
    connection.execute(
        "CREATE OR REPLACE VIEW qd_minute_current AS SELECT trade_date, bar_at, "
        "interval_minutes, instrument, \"open\", high, low, \"close\", volume, amount, "
        "effective_at, available_at, ingested_at, archive_sha256, member_path, member_sha256, "
        f"coalesce(stored_revision_id, {revision_v2}) AS revision_id FROM (SELECT *, "
        "row_number() OVER (PARTITION BY interval_minutes, bar_at, instrument ORDER BY "
        "ingested_at DESC, archive_sha256 DESC, member_sha256 DESC, member_path DESC) rn "
        f"FROM ({base})) WHERE rn=1"
    )


def _minute_snapshot(connection, warehouse: Path) -> str:
    partitions = [
        [int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]), int(row[5])]
        for row in connection.execute(
            "SELECT interval_minutes, CAST(trade_date AS VARCHAR), parquet_relative_path, sha256, "
            "size_bytes, row_count FROM minute_partitions ORDER BY 1,2,3"
        ).fetchall()
    ]
    range_partitions = [
        [
            str(row[0]),
            str(row[1]),
            str(row[2]),
            int(row[3]),
            str(row[4]),
            str(row[5]),
            int(row[6]),
            int(row[7]),
            str(row[8]),
            str(row[9]),
        ]
        for row in connection.execute(
            "SELECT partition_id, archive_relative_path, archive_sha256, interval_minutes, "
            "parquet_relative_path, sha256, size_bytes, row_count, "
            "CAST(min_date AS VARCHAR), CAST(max_date AS VARCHAR) "
            "FROM minute_range_partitions ORDER BY 1"
        ).fetchall()
    ]
    stable = {
        "schema_version": MINUTE_SCHEMA_VERSION,
        "partitions": partitions,
        "range_partitions": range_partitions,
    }
    snapshot_id = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = {**stable, "snapshot_id": snapshot_id}
    path = warehouse / "minute-snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        _atomic_json(path, payload)
    connection.execute(
        "INSERT OR IGNORE INTO minute_snapshots VALUES (?, ?, ?, ?)",
        [
            snapshot_id,
            snapshot_id,
            datetime.now(timezone.utc),
            path.relative_to(warehouse).as_posix(),
        ],
    )
    return snapshot_id


def _read_archive_members(
    archive: Path,
    members: list[tuple[str, int, str | None]],
    *,
    seven_zip_executable: Path | None,
    targeted: bool = False,
    temporary_parent: Path | None = None,
):
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as handle:
            for member, _, _ in members:
                yield member, handle.read(member)
        return
    if seven_zip_executable is None or not seven_zip_executable.is_file():
        raise QmtDataError("7z/rar minute archives require qd_7zip_executable")
    with tempfile.TemporaryDirectory(
        prefix="stephen-quant-minute-",
        dir=str(temporary_parent) if temporary_parent else None,
    ) as temporary:
        root = Path(temporary).resolve()
        try:
            command = [
                str(seven_zip_executable),
                "x",
                "-y",
                "-sccUTF-8",
                f"-o{root}",
                str(archive),
            ]
            if targeted:
                selection = root / "selected-members.txt"
                selection.write_text(
                    "\n".join(member for member, _, _ in members), encoding="utf-8"
                )
                command.extend(["-scsUTF-8", f"@{selection}"])
            subprocess.run(
                command,
                check=True,
                capture_output=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise QmtDataError(f"cannot extract minute archive: {archive.name}") from exc
        for member, _, _ in members:
            path = (root / Path(member.replace("/", "\\"))).resolve()
            if root not in path.parents or not path.is_file():
                raise QmtDataError(f"minute member missing after extraction: {member}")
            yield member, path.read_bytes()


def _normalized_instruments(instruments: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in instruments:
        item = value.strip().upper()
        if re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", item) is None:
            raise QmtDataError(f"invalid minute instrument: {value}")
        normalized.append(item)
    return tuple(sorted(set(normalized)))


def _historical_archives(
    source: Path, start: date, end: date, intervals: tuple[int, ...]
) -> tuple[Path, ...]:
    if start.year > 2025 or end.year < 2000:
        return ()
    return tuple(
        archive
        for archive in _selected_archives(source, start, end)
        if "2000-2025" in archive.parts and _interval(archive.stem, archive) in intervals
    )


def ensure_minute_range(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    start_date: date,
    end_date: date,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    instruments: tuple[str, ...] = (),
    max_source_bytes: int = 2_000_000_000,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    """Locate, materialize and expose a bounded minute range through qd_minute_current."""
    if start_date > end_date:
        raise QmtDataError("start_date must not be after end_date")
    requested = tuple(sorted(set(intervals)))
    if not requested or any(item not in MINUTE_INTERVALS for item in requested):
        raise QmtDataError(f"minute intervals must be selected from {MINUTE_INTERVALS}")
    selected_instruments = _normalized_instruments(instruments)
    if start_date.year <= 2025 and not selected_instruments:
        raise QmtDataError(
            "historical on-demand minute loading requires an explicit instrument allowlist"
        )
    if max_source_bytes <= 0:
        raise QmtDataError("max_source_bytes must be positive")
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    seven_zip = (
        Path(seven_zip_executable).expanduser().resolve() if seven_zip_executable else None
    )
    initialize_minute_warehouse(warehouse)
    daily_results: list[dict[str, object]] = []
    available_daily_dates: list[str] = []
    daily_archives = [
        archive
        for archive in _selected_archives(source, start_date, end_date)
        if _archive_coverage(archive)[0] == "daily"
    ]
    source_gaps: list[dict[str, object]] = []
    if start_date == end_date and start_date.year >= 2026 and not daily_archives:
        source_gaps.append(
            {
                "date": start_date.isoformat(),
                "reason": "no dated source archive is present",
            }
        )
    for archive in daily_archives:
        archive_day = _archive_coverage(archive)[1]
        if archive_day is None:
            continue
        available_daily_dates.append(archive_day.isoformat())
        daily_results.append(
            ingest_minute_archives(
                source,
                warehouse,
                start_date=archive_day,
                end_date=archive_day,
                intervals=requested,
                seven_zip_executable=seven_zip,
            )
        )
    historical_start = max(start_date, date(2000, 1, 1))
    historical_end = min(end_date, date(2025, 12, 31))
    archives = _historical_archives(source, start_date, end_date, requested)
    plans: list[tuple[Path, str, list[tuple[str, int, str | None]]]] = []
    if start_date.year <= 2025:
        located_intervals = {_interval(archive.stem, archive) for archive in archives}
        for interval in sorted(set(requested) - located_intervals):
            source_gaps.append(
                {
                    "interval_minutes": interval,
                    "reason": "no historical source archive is present",
                }
            )
    estimated_bytes = 0
    for archive in archives:
        archive_sha = _sha256(archive)
        listed = _archive_members(archive, seven_zip)
        members = [
            item
            for item in listed
            if item[0].lower().endswith(".csv")
            and _interval(item[0], archive) in requested
            and _instrument(item[0]) in selected_instruments
        ]
        present = {_instrument(item[0]) for item in members}
        for instrument in sorted(set(selected_instruments) - present):
            source_gaps.append(
                {
                    "interval_minutes": _interval(archive.stem, archive),
                    "instrument": instrument,
                    "reason": "source member is absent",
                }
            )
        estimated_bytes += sum(int(item[1]) for item in members)
        plans.append((archive, archive_sha, members))
    if estimated_bytes > max_source_bytes:
        raise QmtDataError(
            f"on-demand minute request needs {estimated_bytes} source bytes, exceeding "
            f"max_source_bytes={max_source_bytes}"
        )
    historical_result: dict[str, object] = {
        "status": "NOT_REQUESTED",
        "new_members": 0,
        "new_revisions": 0,
        "partition_count": 0,
        "snapshot_id": None,
    }
    if plans:
        connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
        batch_id = uuid.uuid4().hex
        started = datetime.now(timezone.utc)
        connection.execute(
            "INSERT INTO minute_batches VALUES (?, ?, NULL, 'RUNNING', NULL, 0, 0, 0, 0, NULL)",
            [batch_id, started],
        )
        staging_root = warehouse / "staging" / f"minute-range-{batch_id}"
        staging_root.mkdir(parents=True, exist_ok=False)
        staged: dict[tuple[int, date], Path] = {}
        row_counts: defaultdict[tuple[int, date], int] = defaultdict(int)
        scopes: list[tuple[object, ...]] = []
        created: list[Path] = []
        transaction_open = False
        try:
            known_scopes: defaultdict[tuple[str, str, str], list[tuple[date, date]]] = (
                defaultdict(list)
            )
            for row in connection.execute(
                    "SELECT archive_relative_path, archive_sha256, member_path, "
                    "scope_start, scope_end "
                    "FROM minute_materialization_scopes"
                ).fetchall():
                known_scopes[(str(row[0]), str(row[1]), str(row[2]))].append(
                    (row[3], row[4])
                )
            for archive, archive_sha, members in plans:
                relative = archive.relative_to(source).as_posix()
                pending = [
                    item
                    for item in members
                    if not any(
                        scope_start <= historical_start and scope_end >= historical_end
                        for scope_start, scope_end in known_scopes.get(
                            (relative, archive_sha, item[0].replace("\\", "/")), []
                        )
                    )
                ]
                if not pending:
                    continue
                handles: dict[tuple[int, date], object] = {}
                try:
                    for member_path, raw in _read_archive_members(
                        archive,
                        pending,
                        seven_zip_executable=seven_zip,
                        targeted=True,
                    ):
                        normalized_member = member_path.replace("\\", "/")
                        interval = _interval(normalized_member, archive)
                        instrument = _instrument(normalized_member)
                        if interval is None or instrument is None:
                            continue
                        member_sha = hashlib.sha256(raw).hexdigest()
                        identity = f"{relative}@{archive_sha}!{normalized_member}"
                        rows, rejected = _parse_member(
                            raw,
                            identity=identity,
                            member_path=normalized_member,
                            instrument=instrument,
                            interval=interval,
                            archive_sha256=archive_sha,
                            member_sha256=member_sha,
                            ingested_at=started,
                        )
                        if rejected:
                            connection.executemany(
                                "INSERT INTO minute_quarantines VALUES (?, ?, ?, ?, ?)",
                                [
                                    (batch_id, identity, reason, row_hash, started)
                                    for reason, row_hash in rejected
                                ],
                            )
                        prior_scopes = known_scopes.get(
                            (relative, archive_sha, normalized_member), []
                        )
                        kept = [
                            row
                            for row in rows
                            if historical_start
                            <= date.fromisoformat(str(row["trade_date"]))
                            <= historical_end
                            and not any(
                                scope_start
                                <= date.fromisoformat(str(row["trade_date"]))
                                <= scope_end
                                for scope_start, scope_end in prior_scopes
                            )
                        ]
                        for row in kept:
                            key = (interval, date.fromisoformat(str(row["trade_date"])))
                            path = staged.setdefault(
                                key, staging_root / f"{interval}m-{key[1].isoformat()}.jsonl"
                            )
                            handle = handles.get(key)
                            if handle is None:
                                handle = path.open("a", encoding="utf-8")
                                handles[key] = handle
                            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
                            row_counts[key] += 1
                        scope_id = hashlib.sha256(
                            f"{identity}|{member_sha}|{historical_start}|{historical_end}".encode()
                        ).hexdigest()
                        scopes.append(
                            (
                                scope_id,
                                relative,
                                archive_sha,
                                normalized_member,
                                member_sha,
                                interval,
                                instrument,
                                historical_start,
                                historical_end,
                                len(kept),
                                batch_id,
                                started,
                            )
                        )
                finally:
                    for handle in handles.values():
                        handle.close()
            partition_rows: list[tuple[object, ...]] = []
            for (interval, trade_day), staging in sorted(staged.items()):
                folder = (
                    warehouse
                    / "parquet"
                    / "qd_minute"
                    / f"interval={interval}"
                    / f"year={trade_day.year}"
                    / f"month={trade_day.month:02d}"
                    / f"day={trade_day.day:02d}"
                )
                folder.mkdir(parents=True, exist_ok=True)
                temporary = folder / f"pending-{batch_id}.parquet"
                _write_minute_parquet(connection, staging, temporary)
                digest = _sha256(temporary)
                target = folder / f"{digest}.parquet"
                if target.exists():
                    temporary.unlink()
                else:
                    temporary.replace(target)
                    created.append(target)
                stats = connection.execute(
                    "SELECT count(*), CAST(min(bar_at) AS VARCHAR), CAST(max(bar_at) AS VARCHAR) "
                    "FROM read_parquet(?)",
                    [str(target)],
                ).fetchone()
                partition_rows.append(
                    (
                        interval,
                        trade_day,
                        target.relative_to(warehouse).as_posix(),
                        digest,
                        target.stat().st_size,
                        int(stats[0]),
                        stats[1],
                        stats[2],
                        batch_id,
                    )
                )
            connection.execute("BEGIN TRANSACTION")
            transaction_open = True
            if scopes:
                connection.executemany(
                    "INSERT INTO minute_materialization_scopes VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    scopes,
                )
            if partition_rows:
                connection.executemany(
                    "INSERT OR IGNORE INTO minute_partitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    partition_rows,
                )
                _refresh_views(connection, warehouse)
            snapshot_id = _minute_snapshot(connection, warehouse)
            revisions = sum(row_counts.values())
            connection.execute(
                "UPDATE minute_batches SET completed_at=?, status=?, snapshot_id=?, "
                "new_archives=?, new_members=?, new_revisions=?, quarantined_rows=0 WHERE batch_id=?",
                [
                    datetime.now(timezone.utc),
                    "COMPLETED" if scopes else "REPLAY_NOOP",
                    snapshot_id,
                    len({scope[1] for scope in scopes}),
                    len(scopes),
                    revisions,
                    batch_id,
                ],
            )
            connection.execute("COMMIT")
            transaction_open = False
            historical_result = {
                "status": "COMPLETED" if scopes else "REPLAY_NOOP",
                "new_members": len(scopes),
                "new_revisions": revisions,
                "partition_count": len(partition_rows),
                "snapshot_id": snapshot_id,
            }
        except Exception as exc:
            if transaction_open:
                connection.execute("ROLLBACK")
            for path in created:
                path.unlink(missing_ok=True)
            connection.execute(
                "UPDATE minute_batches SET completed_at=?, status='FAILED', error=? WHERE batch_id=?",
                [datetime.now(timezone.utc), str(exc), batch_id],
            )
            raise
        finally:
            connection.close()
            for path in staging_root.glob("*"):
                path.unlink(missing_ok=True)
            staging_root.rmdir()
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        clauses = ["trade_date BETWEEN ? AND ?"]
        parameters: list[object] = [start_date, end_date]
        clauses.append(f"interval_minutes IN ({','.join('?' for _ in requested)})")
        parameters.extend(requested)
        if selected_instruments:
            clauses.append(f"instrument IN ({','.join('?' for _ in selected_instruments)})")
            parameters.extend(selected_instruments)
        where = " AND ".join(clauses)
        has_partitions = int(
            connection.execute("SELECT count(*) FROM minute_partitions").fetchone()[0]
        )
        coverage = (
            connection.execute(
                f"SELECT interval_minutes, count(*), count(DISTINCT instrument), "
                f"count(DISTINCT trade_date), min(trade_date), max(trade_date) "
                f"FROM qd_minute_current WHERE {where} GROUP BY 1 ORDER BY 1",
                parameters,
            ).fetchall()
            if has_partitions
            else []
        )
    finally:
        connection.close()
    return {
        "status": "READY",
        "request": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "intervals": list(requested),
            "instruments": list(selected_instruments),
        },
        "source_bytes_planned": estimated_bytes,
        "daily_archive_dates": sorted(set(available_daily_dates)),
        "daily_batches": daily_results,
        "historical_batch": historical_result,
        "source_gaps": source_gaps,
        "coverage": [
            {
                "interval_minutes": int(row[0]),
                "rows": int(row[1]),
                "instruments": int(row[2]),
                "trade_days": int(row[3]),
                "min_date": str(row[4]),
                "max_date": str(row[5]),
            }
            for row in coverage
        ],
        "query_view": "qd_minute_current",
    }


def _commit_range_chunk(
    connection,
    warehouse: Path,
    *,
    staging: Path,
    archive_relative_path: str,
    archive_sha256: str,
    interval: int,
    members: list[tuple[object, ...]],
    quarantines: list[tuple[str, str, str]],
    row_count: int,
    min_date: str,
    max_date: str,
    min_bar_epoch: float,
    max_bar_epoch: float,
    batch_id: str,
    started: datetime,
) -> tuple[int, str]:
    member_identity = "|".join(sorted(str(row[4]) for row in members))
    partition_id = hashlib.sha256(
        f"{archive_sha256}|{interval}|{member_identity}".encode()
    ).hexdigest()
    existing = connection.execute(
        "SELECT row_count FROM minute_range_partitions WHERE partition_id=?",
        [partition_id],
    ).fetchone()
    if existing is not None:
        return int(existing[0]), partition_id
    folder = (
        warehouse
        / "parquet"
        / "qd_minute_ranges"
        / f"interval={interval}"
        / f"archive={archive_sha256[:16]}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"pending-{partition_id}.parquet"
    _write_minute_parquet(connection, staging, temporary)
    digest = _sha256(temporary)
    target = folder / f"{digest}.parquet"
    created = False
    if target.exists():
        temporary.unlink()
    else:
        temporary.replace(target)
        created = True
    try:
        connection.execute("BEGIN TRANSACTION")
        connection.executemany(
            "INSERT OR IGNORE INTO minute_source_members VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            members,
        )
        _insert_quarantines(
            connection,
            quarantines=quarantines,
            batch_id=batch_id,
            started=started,
            staging=staging,
        )
        connection.execute(
            "INSERT OR IGNORE INTO minute_range_partitions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                partition_id,
                archive_relative_path,
                archive_sha256,
                interval,
                target.relative_to(warehouse).as_posix(),
                digest,
                target.stat().st_size,
                row_count,
                date.fromisoformat(min_date),
                date.fromisoformat(max_date),
                datetime.fromtimestamp(min_bar_epoch, timezone.utc),
                datetime.fromtimestamp(max_bar_epoch, timezone.utc),
                batch_id,
            ],
        )
        _refresh_views(connection, warehouse)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        if created:
            target.unlink(missing_ok=True)
        raise
    return row_count, partition_id


def materialize_minute_archive(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    archive_relative_path: str,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    chunk_source_bytes: int = 512_000_000,
    minimum_free_bytes: int = 100_000_000_000,
    parse_workers: int = 1,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    """Fully materialize one cataloged archive in restartable range partitions."""
    if chunk_source_bytes <= 0 or minimum_free_bytes < 0:
        raise QmtDataError("minute materialization storage limits must be non-negative")
    if not 1 <= parse_workers <= 16:
        raise QmtDataError("parse_workers must be between 1 and 16")
    requested = tuple(sorted(set(intervals)))
    if not requested or any(item not in MINUTE_INTERVALS for item in requested):
        raise QmtDataError(f"minute intervals must be selected from {MINUTE_INTERVALS}")
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    seven_zip = (
        Path(seven_zip_executable).expanduser().resolve() if seven_zip_executable else None
    )
    initialize_minute_warehouse(warehouse)
    archive = (source / Path(*PurePosixPath(archive_relative_path).parts)).resolve()
    if source not in archive.parents or not archive.is_file():
        raise QmtDataError(f"minute archive is outside the source root or missing: {archive_relative_path}")
    relative = archive.relative_to(source).as_posix()
    archive_sha = _sha256(archive)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    row = connection.execute(
        "SELECT archive_sha256 FROM minute_archive_catalog "
        "WHERE archive_relative_path=? AND archive_sha256=?",
        [relative, archive_sha],
    ).fetchone()
    if row is None:
        connection.close()
        raise QmtDataError("minute archive must be cataloged with its current SHA-256 first")
    known = {
        str(item[0])
        for item in connection.execute(
            "SELECT member_path FROM minute_source_members "
            "WHERE archive_relative_path=? AND archive_sha256=?",
            [relative, archive_sha],
        ).fetchall()
    }
    selected = [
        item
        for item in _archive_members(archive, seven_zip)
        if item[0].lower().endswith(".csv")
        and _interval(item[0], archive) in requested
        and _instrument(item[0]) is not None
        and item[0].replace("\\", "/") not in known
    ]
    if not selected:
        latest = connection.execute(
            "SELECT snapshot_id FROM minute_snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        connection.close()
        return {
            "status": "REPLAY_NOOP",
            "archive_relative_path": relative,
            "new_members": 0,
            "new_revisions": 0,
            "partition_count": 0,
            "snapshot_id": latest[0] if latest else None,
        }
    batch_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    connection.execute(
        "UPDATE minute_batches SET completed_at=?, status='INTERRUPTED', "
        "error='recovered after an interrupted local process' WHERE status='RUNNING'",
        [started],
    )
    connection.execute(
        "INSERT INTO minute_batches VALUES (?, ?, NULL, 'RUNNING', NULL, 0, 0, 0, 0, NULL)",
        [batch_id, started],
    )
    staging_root = warehouse / "staging" / f"minute-full-{batch_id}"
    staging_root.mkdir(parents=True, exist_ok=False)
    new_members = new_revisions = partition_count = quarantined_rows = 0
    executor = (
        ProcessPoolExecutor(
            max_workers=parse_workers,
            mp_context=multiprocessing.get_context("spawn"),
        )
        if parse_workers > 1
        else None
    )
    try:
        by_interval: defaultdict[int, list[tuple[str, int, str | None]]] = defaultdict(list)
        for item in selected:
            interval = _interval(item[0], archive)
            if interval is not None:
                by_interval[interval].append(item)
        for interval, interval_members in sorted(by_interval.items()):
            chunk_number = 0
            staging = staging_root / f"{interval}m-{chunk_number:06d}.jsonl"
            handle = staging.open("wb")
            chunk_bytes = chunk_rows = 0
            chunk_min_date: str | None = None
            chunk_max_date: str | None = None
            chunk_min_bar_epoch: float | None = None
            chunk_max_bar_epoch: float | None = None
            registrations: list[tuple[object, ...]] = []
            rejected_rows: list[tuple[str, str, str]] = []
            pending: list[
                tuple[
                    Future[_MemberParseResult],
                    Path,
                    str,
                    str,
                    int,
                ]
            ] = []
            submission_number = 0

            def merge_stats(
                rows: int,
                min_date: str | None,
                max_date: str | None,
                min_bar_epoch: float | None,
                max_bar_epoch: float | None,
            ) -> None:
                nonlocal chunk_min_date, chunk_max_date
                nonlocal chunk_min_bar_epoch, chunk_max_bar_epoch
                if not rows:
                    return
                if None in (min_date, max_date, min_bar_epoch, max_bar_epoch):
                    raise QmtDataError("non-empty minute parse result is missing range statistics")
                assert min_date is not None and max_date is not None
                assert min_bar_epoch is not None and max_bar_epoch is not None
                chunk_min_date = (
                    min_date if chunk_min_date is None else min(chunk_min_date, min_date)
                )
                chunk_max_date = (
                    max_date if chunk_max_date is None else max(chunk_max_date, max_date)
                )
                chunk_min_bar_epoch = (
                    min_bar_epoch
                    if chunk_min_bar_epoch is None
                    else min(chunk_min_bar_epoch, min_bar_epoch)
                )
                chunk_max_bar_epoch = (
                    max_bar_epoch
                    if chunk_max_bar_epoch is None
                    else max(chunk_max_bar_epoch, max_bar_epoch)
                )

            def drain_one(
                pending_items: list[
                    tuple[
                        Future[_MemberParseResult],
                        Path,
                        str,
                        str,
                        int,
                    ]
                ],
                output_handle,
                registration_rows: list[tuple[object, ...]],
                quarantine_rows: list[tuple[str, str, str]],
                member_interval: int,
            ) -> None:
                nonlocal chunk_rows, new_members, quarantined_rows
                future, worker_output, normalized_member, identity, raw_size = pending_items.pop(0)
                try:
                    (
                        rows,
                        rejected,
                        member_sha,
                        min_date,
                        max_date,
                        min_bar_epoch,
                        max_bar_epoch,
                    ) = future.result()
                    with worker_output.open("rb") as source_handle:
                        shutil.copyfileobj(source_handle, output_handle, length=1024 * 1024)
                finally:
                    worker_output.unlink(missing_ok=True)
                merge_stats(rows, min_date, max_date, min_bar_epoch, max_bar_epoch)
                registration_rows.append(
                    (
                        relative,
                        archive_sha,
                        archive.stat().st_size,
                        normalized_member,
                        member_sha,
                        raw_size,
                        member_interval,
                        batch_id,
                    )
                )
                quarantine_rows.extend(
                    (identity, reason, row_hash) for reason, row_hash in rejected
                )
                chunk_rows += rows
                quarantined_rows += len(rejected)
                new_members += 1

            def drain_all(
                pending_items: list[
                    tuple[
                        Future[_MemberParseResult],
                        Path,
                        str,
                        str,
                        int,
                    ]
                ],
                output_handle,
                registration_rows: list[tuple[object, ...]],
                quarantine_rows: list[tuple[str, str, str]],
                member_interval: int,
            ) -> None:
                while pending_items:
                    drain_one(
                        pending_items,
                        output_handle,
                        registration_rows,
                        quarantine_rows,
                        member_interval,
                    )

            def flush(interval: int = interval) -> None:
                nonlocal handle, staging, chunk_number, chunk_bytes, chunk_rows
                nonlocal registrations, rejected_rows, new_revisions, partition_count
                nonlocal chunk_min_date, chunk_max_date
                nonlocal chunk_min_bar_epoch, chunk_max_bar_epoch
                if not registrations:
                    return
                handle.close()
                if chunk_rows:
                    if None in (
                        chunk_min_date,
                        chunk_max_date,
                        chunk_min_bar_epoch,
                        chunk_max_bar_epoch,
                    ):
                        raise QmtDataError("minute chunk is missing range statistics")
                    assert chunk_min_date is not None and chunk_max_date is not None
                    assert chunk_min_bar_epoch is not None and chunk_max_bar_epoch is not None
                    rows, _ = _commit_range_chunk(
                        connection,
                        warehouse,
                        staging=staging,
                        archive_relative_path=relative,
                        archive_sha256=archive_sha,
                        interval=interval,
                        members=registrations,
                        quarantines=rejected_rows,
                        row_count=chunk_rows,
                        min_date=chunk_min_date,
                        max_date=chunk_max_date,
                        min_bar_epoch=chunk_min_bar_epoch,
                        max_bar_epoch=chunk_max_bar_epoch,
                        batch_id=batch_id,
                        started=started,
                    )
                    new_revisions += rows
                    partition_count += 1
                else:
                    connection.execute("BEGIN TRANSACTION")
                    connection.executemany(
                        "INSERT OR IGNORE INTO minute_source_members VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        registrations,
                    )
                    _insert_quarantines(
                        connection,
                        quarantines=rejected_rows,
                        batch_id=batch_id,
                        started=started,
                        staging=staging,
                    )
                    connection.execute("COMMIT")
                staging.unlink(missing_ok=True)
                chunk_number += 1
                staging = staging_root / f"{interval}m-{chunk_number:06d}.jsonl"
                handle = staging.open("wb")
                chunk_bytes = chunk_rows = 0
                chunk_min_date = chunk_max_date = None
                chunk_min_bar_epoch = chunk_max_bar_epoch = None
                registrations = []
                rejected_rows = []

            try:
                for member_path, raw in _read_archive_members(
                    archive,
                    interval_members,
                    seven_zip_executable=seven_zip,
                    targeted=False,
                    temporary_parent=staging_root,
                ):
                    if chunk_bytes and chunk_bytes + len(raw) > chunk_source_bytes:
                        drain_all(pending, handle, registrations, rejected_rows, interval)
                        flush()
                    if shutil.disk_usage(warehouse).free < minimum_free_bytes:
                        raise QmtDataError(
                            "minute materialization stopped at the configured free-space reserve"
                        )
                    normalized_member = member_path.replace("\\", "/")
                    instrument = _instrument(normalized_member)
                    if instrument is None:
                        continue
                    identity = f"{relative}@{archive_sha}!{normalized_member}"
                    if executor is None:
                        member_sha = hashlib.sha256(raw).hexdigest()
                        for parsed, rejected in _iter_member_records(
                            raw,
                            identity=identity,
                            member_path=normalized_member,
                            instrument=instrument,
                            interval=interval,
                            archive_sha256=archive_sha,
                            member_sha256=member_sha,
                            ingested_at=started,
                        ):
                            if parsed is not None:
                                handle.write(
                                    (json.dumps(parsed, separators=(",", ":")) + "\n").encode()
                                )
                                chunk_rows += 1
                                merge_stats(
                                    1,
                                    str(parsed["trade_date"]),
                                    str(parsed["trade_date"]),
                                    float(parsed["bar_at_epoch"]),
                                    float(parsed["bar_at_epoch"]),
                                )
                            elif rejected is not None:
                                rejected_rows.append((identity, rejected[0], rejected[1]))
                                quarantined_rows += 1
                        registrations.append(
                            (
                                relative,
                                archive_sha,
                                archive.stat().st_size,
                                normalized_member,
                                member_sha,
                                len(raw),
                                interval,
                                batch_id,
                            )
                        )
                        new_members += 1
                    else:
                        worker_output = staging_root / (
                            f"worker-{interval}m-{submission_number:08d}.jsonl"
                        )
                        submission_number += 1
                        pending.append(
                            (
                                executor.submit(
                                    _parse_member_to_jsonl,
                                    raw,
                                    output_path=str(worker_output),
                                    identity=identity,
                                    member_path=normalized_member,
                                    instrument=instrument,
                                    interval=interval,
                                    archive_sha256=archive_sha,
                                    ingested_at=started,
                                ),
                                worker_output,
                                normalized_member,
                                identity,
                                len(raw),
                            )
                        )
                        if len(pending) >= parse_workers * 2:
                            drain_one(pending, handle, registrations, rejected_rows, interval)
                    chunk_bytes += len(raw)
                drain_all(pending, handle, registrations, rejected_rows, interval)
                flush()
            finally:
                if not handle.closed:
                    handle.close()
                staging.unlink(missing_ok=True)
        _refresh_views(connection, warehouse)
        snapshot_id = _minute_snapshot(connection, warehouse)
        connection.execute(
            "UPDATE minute_batches SET completed_at=?, status='COMPLETED', snapshot_id=?, "
            "new_archives=1, new_members=?, new_revisions=?, quarantined_rows=? WHERE batch_id=?",
            [
                datetime.now(timezone.utc),
                snapshot_id,
                new_members,
                new_revisions,
                quarantined_rows,
                batch_id,
            ],
        )
        return {
            "status": "COMPLETED",
            "archive_relative_path": relative,
            "new_members": new_members,
            "new_revisions": new_revisions,
            "partition_count": partition_count,
            "quarantined_rows": quarantined_rows,
            "snapshot_id": snapshot_id,
        }
    except Exception as exc:
        connection.execute(
            "UPDATE minute_batches SET completed_at=?, status='FAILED', error=?, "
            "new_members=?, new_revisions=?, quarantined_rows=? WHERE batch_id=?",
            [
                datetime.now(timezone.utc),
                str(exc),
                new_members,
                new_revisions,
                quarantined_rows,
                batch_id,
            ],
        )
        raise
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
        connection.close()
        for path in staging_root.glob("*"):
            path.unlink(missing_ok=True)
        staging_root.rmdir()


def materialize_all_available_minutes(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    chunk_source_bytes: int = 512_000_000,
    minimum_free_bytes: int = 100_000_000_000,
    parse_workers: int = 1,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    """Materialize every recognized archive with restartable archive-level progress."""
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    catalog_minute_archives(
        source,
        warehouse,
        intervals=intervals,
        seven_zip_executable=seven_zip_executable,
    )
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    pending = [
        (str(row[0]), str(row[1]), int(row[2]))
        for row in connection.execute(
            "SELECT archive_relative_path, coverage_kind, uncompressed_bytes "
            "FROM minute_archive_catalog WHERE materialization_status<>'MATERIALIZED' "
            "ORDER BY CASE coverage_kind WHEN 'unbounded' THEN 0 "
            "WHEN 'historical_bundle' THEN 1 WHEN 'annual' THEN 2 "
            "WHEN 'daily' THEN 3 ELSE 4 END, coverage_start, archive_relative_path"
        ).fetchall()
    ]
    connection.close()
    estimated_parquet_bytes = int(sum(row[2] for row in pending) * 0.70)
    free_before = shutil.disk_usage(warehouse).free
    if pending and free_before - estimated_parquet_bytes < minimum_free_bytes:
        raise QmtDataError(
            "estimated full minute materialization would violate the configured free-space reserve"
        )
    results: list[dict[str, object]] = []
    for relative, kind, _ in pending:
        if kind == "daily":
            archive = (source / Path(*PurePosixPath(relative).parts)).resolve()
            day = _archive_coverage(archive)[1]
            if day is None:
                raise QmtDataError(f"daily archive has no date: {relative}")
            results.append(
                ingest_minute_archives(
                    source,
                    warehouse,
                    start_date=day,
                    end_date=day,
                    intervals=intervals,
                    seven_zip_executable=seven_zip_executable,
                )
            )
        else:
            results.append(
                materialize_minute_archive(
                    source,
                    warehouse,
                    archive_relative_path=relative,
                    intervals=intervals,
                    chunk_source_bytes=chunk_source_bytes,
                    minimum_free_bytes=minimum_free_bytes,
                    parse_workers=parse_workers,
                    seven_zip_executable=seven_zip_executable,
                )
            )
    final_catalog = catalog_minute_archives(
        source,
        warehouse,
        intervals=intervals,
        seven_zip_executable=seven_zip_executable,
    )
    incomplete = [
        item for item in final_catalog["summaries"] if item["status"] != "MATERIALIZED"
    ]
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    latest = connection.execute(
        "SELECT snapshot_id FROM minute_snapshots ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    connection.close()
    return {
        "status": "COMPLETED" if not incomplete else "INCOMPLETE",
        "pending_archives_at_start": len(pending),
        "estimated_parquet_bytes": estimated_parquet_bytes,
        "free_bytes_before": free_before,
        "free_bytes_after": shutil.disk_usage(warehouse).free,
        "archive_results": results,
        "catalog": final_catalog,
        "snapshot_id": latest[0] if latest else None,
    }


def ingest_minute_archives(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    intervals: tuple[int, ...] = MINUTE_INTERVALS,
    seven_zip_executable: str | Path | None = None,
) -> dict[str, object]:
    requested = tuple(sorted(set(intervals)))
    if not requested or any(item not in MINUTE_INTERVALS for item in requested):
        raise QmtDataError(f"minute intervals must be selected from {MINUTE_INTERVALS}")
    if start_date and end_date and start_date > end_date:
        raise QmtDataError("start_date must not be after end_date")
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    seven_zip = (
        Path(seven_zip_executable).expanduser().resolve() if seven_zip_executable else None
    )
    initialize_minute_warehouse(warehouse)
    archives = _selected_archives(source, start_date, end_date)
    if not archives:
        raise QmtDataError("no minute archives match the requested range")
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    batch_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    connection.execute(
        "UPDATE minute_batches SET completed_at=?, status='INTERRUPTED', "
        "error='recovered after an interrupted local process' WHERE status='RUNNING'",
        [started],
    )
    connection.execute(
        "INSERT INTO minute_batches VALUES (?, ?, NULL, 'RUNNING', NULL, 0, 0, 0, 0, NULL)",
        [batch_id, started],
    )
    staging_root = warehouse / "staging" / f"minute-{batch_id}"
    staging_root.mkdir(parents=True, exist_ok=False)
    staged: dict[tuple[int, date], Path] = {}
    row_counts: defaultdict[tuple[int, date], int] = defaultdict(int)
    members_to_register: list[tuple[object, ...]] = []
    quarantines: list[tuple[str, str, str]] = []
    new_archives = new_members = new_revisions = 0
    created: list[Path] = []
    transaction_open = False
    try:
        known = {
            (str(row[0]), str(row[1]), str(row[2]))
            for row in connection.execute(
                "SELECT archive_relative_path, archive_sha256, member_path FROM minute_source_members"
            ).fetchall()
        }
        for archive in archives:
            relative = archive.relative_to(source).as_posix()
            archive_sha = _sha256(archive)
            listed = _archive_members(archive, seven_zip)
            selected = [
                item
                for item in listed
                if item[0].lower().endswith(".csv")
                and _interval(item[0], archive) in requested
                and _instrument(item[0]) is not None
                and (relative, archive_sha, item[0].replace("\\", "/")) not in known
            ]
            if not selected:
                continue
            new_archives += 1
            archive_handles: dict[tuple[int, date], object] = {}
            try:
                for member_path, raw in _read_archive_members(
                    archive, selected, seven_zip_executable=seven_zip
                ):
                    normalized_member = member_path.replace("\\", "/")
                    interval = _interval(normalized_member, archive)
                    instrument = _instrument(normalized_member)
                    if interval is None or instrument is None:
                        continue
                    member_sha = hashlib.sha256(raw).hexdigest()
                    identity = f"{relative}@{archive_sha}!{normalized_member}"
                    rows, rejected = _parse_member(
                        raw,
                        identity=identity,
                        member_path=normalized_member,
                        instrument=instrument,
                        interval=interval,
                        archive_sha256=archive_sha,
                        member_sha256=member_sha,
                        ingested_at=started,
                    )
                    outside_requested_range = any(
                        (start_date and date.fromisoformat(str(row["trade_date"])) < start_date)
                        or (end_date and date.fromisoformat(str(row["trade_date"])) > end_date)
                        for row in rows
                    )
                    if outside_requested_range:
                        raise QmtDataError(
                            "a selected minute member crosses the requested date boundary; "
                            "use an archive-complete range instead of silently truncating it: "
                            f"{identity}"
                        )
                    for row in rows:
                        key = (interval, date.fromisoformat(str(row["trade_date"])))
                        path = staged.setdefault(
                            key, staging_root / f"{interval}m-{key[1].isoformat()}.jsonl"
                        )
                        handle = archive_handles.get(key)
                        if handle is None:
                            handle = path.open("a", encoding="utf-8")
                            archive_handles[key] = handle
                        handle.write(json.dumps(row, separators=(",", ":")) + "\n")
                        row_counts[key] += 1
                    quarantines.extend(
                        (identity, reason, row_hash) for reason, row_hash in rejected
                    )
                    members_to_register.append(
                        (
                            relative,
                            archive_sha,
                            archive.stat().st_size,
                            normalized_member,
                            member_sha,
                            len(raw),
                            interval,
                            batch_id,
                        )
                    )
                    new_members += 1
                    new_revisions += len(rows)
            finally:
                for handle in archive_handles.values():
                    handle.close()
        if not members_to_register:
            latest = connection.execute(
                "SELECT snapshot_id FROM minute_snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            connection.execute(
                "UPDATE minute_batches SET completed_at=?, status='REPLAY_NOOP', snapshot_id=? "
                "WHERE batch_id=?",
                [datetime.now(timezone.utc), latest[0] if latest else None, batch_id],
            )
            return {
                "batch_id": batch_id,
                "status": "REPLAY_NOOP",
                "new_archives": 0,
                "new_members": 0,
                "new_revisions": 0,
                "quarantined_rows": 0,
                "snapshot_id": latest[0] if latest else None,
            }
        partition_rows: list[tuple[object, ...]] = []
        for (interval, trade_day), staging in sorted(staged.items()):
            folder = (
                warehouse
                / "parquet"
                / "qd_minute"
                / f"interval={interval}"
                / f"year={trade_day.year}"
                / f"month={trade_day.month:02d}"
                / f"day={trade_day.day:02d}"
            )
            folder.mkdir(parents=True, exist_ok=True)
            temporary = folder / f"pending-{batch_id}.parquet"
            _write_minute_parquet(connection, staging, temporary)
            digest = _sha256(temporary)
            target = folder / f"{digest}.parquet"
            if target.exists():
                temporary.unlink()
            else:
                temporary.replace(target)
                created.append(target)
            stats = connection.execute(
                "SELECT count(*), CAST(min(bar_at) AS VARCHAR), CAST(max(bar_at) AS VARCHAR) "
                "FROM read_parquet(?)",
                [str(target)],
            ).fetchone()
            partition_rows.append(
                (
                    interval,
                    trade_day,
                    target.relative_to(warehouse).as_posix(),
                    digest,
                    target.stat().st_size,
                    int(stats[0]),
                    stats[1],
                    stats[2],
                    batch_id,
                )
            )
        connection.execute("BEGIN TRANSACTION")
        transaction_open = True
        connection.executemany(
            "INSERT INTO minute_source_members VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            members_to_register,
        )
        connection.executemany(
            "INSERT OR IGNORE INTO minute_partitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            partition_rows,
        )
        if quarantines:
            connection.executemany(
                "INSERT INTO minute_quarantines VALUES (?, ?, ?, ?, ?)",
                [
                    (batch_id, identity, reason, row_hash, started)
                    for identity, reason, row_hash in quarantines
                ],
            )
        _refresh_views(connection, warehouse)
        snapshot_id = _minute_snapshot(connection, warehouse)
        connection.execute(
            "UPDATE minute_batches SET completed_at=?, status='COMPLETED', snapshot_id=?, "
            "new_archives=?, new_members=?, new_revisions=?, quarantined_rows=? WHERE batch_id=?",
            [
                datetime.now(timezone.utc),
                snapshot_id,
                new_archives,
                new_members,
                new_revisions,
                len(quarantines),
                batch_id,
            ],
        )
        connection.execute("COMMIT")
        transaction_open = False
        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "new_archives": new_archives,
            "new_members": new_members,
            "new_revisions": new_revisions,
            "quarantined_rows": len(quarantines),
            "partition_count": len(partition_rows),
            "snapshot_id": snapshot_id,
        }
    except Exception as exc:
        if transaction_open:
            connection.execute("ROLLBACK")
        for path in created:
            path.unlink(missing_ok=True)
        connection.execute(
            "UPDATE minute_batches SET completed_at=?, status='FAILED', error=? WHERE batch_id=?",
            [datetime.now(timezone.utc), str(exc), batch_id],
        )
        raise
    finally:
        connection.close()
        for path in staging_root.glob("*"):
            path.unlink(missing_ok=True)
        staging_root.rmdir()


def verify_minute_snapshot(warehouse_root: str | Path, snapshot_id: str) -> dict[str, object]:
    warehouse = Path(warehouse_root).expanduser().resolve()
    path = warehouse / "minute-snapshots" / f"{snapshot_id}.json"
    if not path.is_file():
        raise QmtDataError(f"minute snapshot does not exist: {snapshot_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    stable = {
        "schema_version": payload["schema_version"],
        "partitions": payload["partitions"],
    }
    if "range_partitions" in payload:
        stable["range_partitions"] = payload["range_partitions"]
    computed = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    failures: list[str] = []
    if computed != snapshot_id:
        failures.append("minute snapshot hash mismatch")
    paths: list[str] = []
    for row in payload["partitions"]:
        relative, expected_sha, expected_size = str(row[2]), str(row[3]), int(row[4])
        partition = (warehouse / relative).resolve()
        if warehouse not in partition.parents or not partition.is_file():
            failures.append(f"missing minute partition: {relative}")
            continue
        if partition.stat().st_size != expected_size or _sha256(partition) != expected_sha:
            failures.append(f"minute partition integrity mismatch: {relative}")
        paths.append(str(partition))
    for row in payload.get("range_partitions", []):
        relative, expected_sha, expected_size = str(row[4]), str(row[5]), int(row[6])
        partition = (warehouse / relative).resolve()
        if warehouse not in partition.parents or not partition.is_file():
            failures.append(f"missing minute range partition: {relative}")
            continue
        if partition.stat().st_size != expected_size or _sha256(partition) != expected_sha:
            failures.append(f"minute range partition integrity mismatch: {relative}")
        paths.append(str(partition))
    rows = duplicates = timing = 0
    if paths:
        connection = _duckdb().connect()
        try:
            literals = ",".join(
                f"'{path.replace(chr(39), chr(39) * 2)}'" for path in paths
            )
            relation = _minute_relation_sql(connection, literals, revision_mode="none")
            rows = int(connection.execute(f"SELECT count(*) FROM ({relation})").fetchone()[0])
            current = (
                "SELECT * EXCLUDE(rn) FROM (SELECT *, row_number() OVER (PARTITION BY "
                "interval_minutes, bar_at, instrument ORDER BY ingested_at DESC, "
                "archive_sha256 DESC, member_sha256 DESC, member_path DESC) rn "
                f"FROM ({relation})) WHERE rn=1"
            )
            duplicates = int(
                connection.execute(
                    f"SELECT count(*) FROM (SELECT interval_minutes, bar_at, instrument, count(*) n "
                    f"FROM ({current}) GROUP BY 1,2,3 HAVING n>1)"
                ).fetchone()[0]
            )
            timing = int(
                connection.execute(
                    f"SELECT count(*) FROM ({relation}) WHERE effective_at > available_at "
                    "OR available_at > ingested_at"
                ).fetchone()[0]
            )
        finally:
            connection.close()
    if duplicates:
        failures.append("duplicate minute current keys")
    if timing:
        failures.append("minute PIT timing violations")
    return {
        "snapshot_id": snapshot_id,
        "passed": not failures,
        "failures": failures,
        "partition_count": len(paths),
        "revision_rows": rows,
        "duplicate_current_keys": duplicates,
        "timing_violations": timing,
    }
