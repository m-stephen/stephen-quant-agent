from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
import tempfile
import uuid
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path, PurePosixPath

from .asset_inventory import _archive_members
from .data_warehouse import _atomic_json, _duckdb, _sha256, initialize_warehouse
from .models import QmtDataError

MINUTE_SCHEMA_VERSION = 1
MINUTE_FOLDER = "分钟K线合集"
MINUTE_INTERVALS = (1, 5, 15, 30, 60)
_INTERVAL = re.compile(r"(?<!\d)(1|5|15|30|60)\s*(?:min|分钟)", re.IGNORECASE)
_INSTRUMENT = re.compile(r"^(bj|sh|sz)(\d{6})$", re.IGNORECASE)
_DATE_STEM = re.compile(r"^(20\d{6})$")
_YEAR = re.compile(r"^(20\d{2})$")
_SHANGHAI = timezone(timedelta(hours=8))


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
        materialized = {
            (str(row[0]), str(row[1])): int(row[2])
            for row in connection.execute(
                "SELECT archive_relative_path, archive_sha256, count(*) "
                "FROM minute_source_members GROUP BY 1,2"
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
            done = materialized.get((relative, archive_sha), 0)
            status = "MATERIALIZED" if selected and done >= len(selected) else (
                "PARTIAL" if done else "AVAILABLE"
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
                    done,
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
    rows: list[dict[str, object]] = []
    quarantines: list[tuple[str, str]] = []
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
            quarantines.append((f"row {number}: {reason}", row_hash))
            continue
        bar_at = datetime.combine(trade_day, clock, tzinfo=_SHANGHAI)
        key = bar_at.isoformat()
        if key in seen:
            row_hash = hashlib.sha256(
                json.dumps(raw_row, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest()
            quarantines.append((f"row {number}: duplicate member key", row_hash))
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
        rows.append(
            {
                **stable,
                "bar_at_epoch": bar_at.timestamp(),
                "effective_at_epoch": bar_at.timestamp(),
                "available_at_epoch": (bar_at + timedelta(seconds=1)).timestamp(),
                "ingested_at_epoch": ingested_at.timestamp(),
                "revision_id": revision_id,
                "ingested_at": ingested_at.isoformat(),
            }
        )
    return rows, quarantines


def _write_minute_parquet(connection, staging: Path, target: Path) -> None:
    source_sql = str(staging).replace("'", "''")
    target_sql = str(target).replace("'", "''")
    connection.execute(
        "COPY (SELECT CAST(trade_date AS DATE) trade_date, to_timestamp(bar_at_epoch) bar_at, "
        "CAST(interval_minutes AS INTEGER) interval_minutes, instrument, "
        'CAST("open" AS DOUBLE) "open", CAST(high AS DOUBLE) high, CAST(low AS DOUBLE) low, '
        'CAST("close" AS DOUBLE) "close", CAST(volume AS DOUBLE) volume, CAST(amount AS DOUBLE) amount, '
        "to_timestamp(effective_at_epoch) effective_at, "
        "to_timestamp(available_at_epoch) available_at, "
        "to_timestamp(ingested_at_epoch) ingested_at, archive_sha256, member_path, member_sha256, "
        f"revision_id FROM read_json_auto('{source_sql}')) TO '{target_sql}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def _refresh_views(connection, warehouse: Path) -> None:
    paths = [
        str(warehouse / row[0]).replace("'", "''")
        for row in connection.execute(
            "SELECT parquet_relative_path FROM minute_partitions ORDER BY parquet_relative_path"
        ).fetchall()
    ]
    if not paths:
        return
    literals = ",".join(f"'{path}'" for path in paths)
    connection.execute(
        f"CREATE OR REPLACE VIEW qd_minute_revisions AS SELECT * FROM read_parquet([{literals}])"
    )
    connection.execute(
        "CREATE OR REPLACE VIEW qd_minute_current AS SELECT * EXCLUDE(rn) FROM (SELECT *, "
        "row_number() OVER (PARTITION BY interval_minutes, bar_at, instrument ORDER BY "
        "ingested_at DESC, revision_id DESC) rn FROM qd_minute_revisions) WHERE rn=1"
    )


def _minute_snapshot(connection, warehouse: Path) -> str:
    partitions = [
        [int(row[0]), str(row[1]), str(row[2]), str(row[3]), int(row[4]), int(row[5])]
        for row in connection.execute(
            "SELECT interval_minutes, CAST(trade_date AS VARCHAR), parquet_relative_path, sha256, "
            "size_bytes, row_count FROM minute_partitions ORDER BY 1,2,3"
        ).fetchall()
    ]
    stable = {"schema_version": MINUTE_SCHEMA_VERSION, "partitions": partitions}
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
):
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as handle:
            for member, _, _ in members:
                yield member, handle.read(member)
        return
    if seven_zip_executable is None or not seven_zip_executable.is_file():
        raise QmtDataError("7z/rar minute archives require qd_7zip_executable")
    with tempfile.TemporaryDirectory(prefix="stephen-quant-minute-") as temporary:
        root = Path(temporary).resolve()
        try:
            subprocess.run(
                [
                    str(seven_zip_executable),
                    "x",
                    "-y",
                    "-sccUTF-8",
                    f"-o{root}",
                    str(archive),
                ],
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
    rows = duplicates = timing = 0
    if paths:
        connection = _duckdb().connect()
        try:
            rows = int(connection.execute("SELECT count(*) FROM read_parquet(?)", [paths]).fetchone()[0])
            current = (
                "SELECT * EXCLUDE(rn) FROM (SELECT *, row_number() OVER (PARTITION BY "
                "interval_minutes, bar_at, instrument ORDER BY ingested_at DESC, revision_id DESC) rn "
                "FROM read_parquet(?)) WHERE rn=1"
            )
            duplicates = int(
                connection.execute(
                    f"SELECT count(*) FROM (SELECT interval_minutes, bar_at, instrument, count(*) n "
                    f"FROM ({current}) GROUP BY 1,2,3 HAVING n>1)",
                    [paths],
                ).fetchone()[0]
            )
            timing = int(
                connection.execute(
                    "SELECT count(*) FROM read_parquet(?) WHERE effective_at > available_at "
                    "OR available_at > ingested_at",
                    [paths],
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
