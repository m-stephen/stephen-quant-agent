from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import uuid
import zipfile
import zlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .models import QmtDataError

DAILY_FOLDER = "股票日K_按日期"
DAILY_COLUMNS = {
    "日期": "trade_date",
    "代码": "instrument",
    "名称": "name",
    "行业": "industry",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量(手)": "volume",
    "成交额(千元)": "amount",
    "复权因子": "adjustment_factor",
}
REQUIRED = {"trade_date", "instrument", "open", "high", "low", "close", "volume", "amount"}


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise QmtDataError("DuckDB is required; install with pip install -e .[warehouse]") from exc
    return duckdb


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def initialize_warehouse(root: str | Path) -> dict[str, str]:
    warehouse = Path(root).expanduser().resolve()
    warehouse.mkdir(parents=True, exist_ok=True)
    for folder in ("catalog", "parquet", "snapshots", "staging", "reports"):
        (warehouse / folder).mkdir(exist_ok=True)
    db_path = warehouse / "catalog" / "warehouse.duckdb"
    connection = _duckdb().connect(str(db_path))
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS warehouse_meta (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL)")
        connection.execute("INSERT OR REPLACE INTO warehouse_meta VALUES ('schema_version', '1')")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS ingest_batches (batch_id VARCHAR PRIMARY KEY, started_at TIMESTAMPTZ, "
            "completed_at TIMESTAMPTZ, inventory_sha256 VARCHAR, status VARCHAR, new_source_files BIGINT, "
            "new_revisions BIGINT, snapshot_id VARCHAR, error VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS source_files (relative_path VARCHAR, sha256 VARCHAR, size_bytes BIGINT, "
            "dataset VARCHAR, first_batch_id VARCHAR, PRIMARY KEY(relative_path, sha256))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS partitions (dataset VARCHAR, year INTEGER, month INTEGER, "
            "parquet_relative_path VARCHAR, sha256 VARCHAR, size_bytes BIGINT, row_count BIGINT, "
            "min_date DATE, max_date DATE, active BOOLEAN, batch_id VARCHAR, PRIMARY KEY(parquet_relative_path))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS snapshots (snapshot_id VARCHAR PRIMARY KEY, manifest_sha256 VARCHAR, "
            "created_at TIMESTAMPTZ, manifest_relative_path VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS quarantines (batch_id VARCHAR, relative_path VARCHAR, "
            "reason VARCHAR, created_at TIMESTAMPTZ, row_sha256 VARCHAR)"
        )
        connection.execute("ALTER TABLE quarantines ADD COLUMN IF NOT EXISTS row_sha256 VARCHAR")
    finally:
        connection.close()
    return {"warehouse_root": str(warehouse), "catalog": str(db_path), "schema_version": "1"}


def _read_csv_bytes(
    raw_bytes: bytes, display_name: str, source_sha: str, ingested_at: datetime
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    decoded: str | None = None
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            candidate = raw_bytes.decode(encoding)
            header = candidate.splitlines()[0] if candidate.splitlines() else ""
            if "日期" in header and "代码" in header:
                decoded = candidate
                break
        except UnicodeError:
            continue
    if decoded is None:
        raise QmtDataError(f"unsupported CSV encoding: {display_name}")
    reader = csv.DictReader(decoded.splitlines())
    if reader.fieldnames is None:
        raise QmtDataError(f"CSV has no header: {display_name}")
    mapped = {name.strip(): DAILY_COLUMNS.get(name.strip()) for name in reader.fieldnames}
    present = {value for value in mapped.values() if value}
    missing = sorted(REQUIRED - present)
    if missing:
        raise QmtDataError(f"daily CSV {display_name} missing columns: {missing}")
    rows: list[dict[str, object]] = []
    quarantines: list[dict[str, object]] = []
    shanghai = timezone(timedelta(hours=8))
    for number, raw in enumerate(reader, start=2):
        row = {canonical: (raw.get(source) or "").strip() for source, canonical in mapped.items() if canonical}
        reason: str | None = None
        try:
            raw_day = str(row["trade_date"])
            trade_day = date.fromisoformat(f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:8]}")
            instrument = str(row["instrument"]).zfill(6)
            numeric = {key: float(row[key]) for key in ("open", "high", "low", "close", "volume", "amount")}
            adjustment = float(row.get("adjustment_factor") or 1.0)
        except (KeyError, TypeError, ValueError):
            reason = "invalid daily value"
        if reason is None and min(
            numeric["open"], numeric["high"], numeric["low"], numeric["close"]
        ) <= 0:
            reason = "non-positive OHLC"
        if reason is None and numeric["high"] < max(
            numeric["open"], numeric["low"], numeric["close"]
        ):
            reason = "inconsistent high"
        if reason is None and numeric["low"] > min(
            numeric["open"], numeric["high"], numeric["close"]
        ):
            reason = "inconsistent low"
        if reason is None and (
            numeric["volume"] < 0 or numeric["amount"] < 0 or adjustment <= 0
        ):
            reason = "invalid volume, amount, or adjustment"
        if reason is not None:
            row_sha = hashlib.sha256(
                json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            quarantines.append(
                {
                    "relative_path": display_name,
                    "row_number": number,
                    "row_sha256": row_sha,
                    "reason": reason,
                }
            )
            continue
        effective = datetime.combine(trade_day, time(15), tzinfo=shanghai)
        available = datetime.combine(trade_day, time(18), tzinfo=shanghai)
        stable = {
            "trade_date": trade_day.isoformat(),
            "instrument": instrument,
            "name": row.get("name", ""),
            "industry": row.get("industry", ""),
            **numeric,
            "adjustment_factor": adjustment,
            "effective_at": effective.isoformat(),
            "available_at": available.isoformat(),
            "source_file_sha256": source_sha,
        }
        revision = hashlib.sha256(
            json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        rows.append({**stable, "revision_id": revision, "ingested_at": ingested_at.isoformat()})
    if not rows:
        detail = quarantines[0]["reason"] if quarantines else "empty file"
        raise QmtDataError(f"daily CSV contains no valid rows: {display_name}; {detail}")
    return rows, quarantines


@dataclass(frozen=True)
class _SourceCandidate:
    identity: str
    container: Path
    expected_container_sha256: str
    expected_container_size: int
    day: date
    member_path: str | None = None
    expected_member_size: int | None = None
    expected_member_crc32: str | None = None


def _inventory_files(manifest_path: Path, source_root: Path, start: date | None, end: date | None):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    accepted = {"extracted_from_archive", "source_uncompressed"}
    selected: list[_SourceCandidate] = []
    prefix = f"{DAILY_FOLDER}/"
    extracted_members = {
        (entry.get("archive_relative_path"), entry.get("archive_member_path"))
        for entry in manifest.get("entries", [])
        if entry.get("status") == "extracted_from_archive"
    }
    historical_extracted_members = {
        (
            item.get("archive_relative_path"),
            item.get("archive_sha256"),
            item.get("member_path"),
        )
        for item in manifest.get("previously_extracted_archive_members", [])
    }
    for entry in manifest.get("entries", []):
        relative = str(entry.get("relative_path", ""))
        if not relative.startswith(prefix) or not relative.lower().endswith(".csv"):
            continue
        stem = Path(relative).stem
        try:
            day = date.fromisoformat(f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}")
        except ValueError:
            continue
        if entry.get("status") not in accepted or (start and day < start) or (end and day > end):
            continue
        resolved = (source_root / Path(relative)).resolve()
        if source_root not in resolved.parents or not resolved.is_file():
            raise QmtDataError(f"inventory source path is invalid: {relative}")
        selected.append(
            _SourceCandidate(
                identity=relative,
                container=resolved,
                expected_container_sha256=str(entry["sha256"]),
                expected_container_size=int(entry["size_bytes"]),
                day=day,
            )
        )
    for member in manifest.get("archive_members", []):
        archive_relative = str(member.get("archive_relative_path", ""))
        member_path = str(member.get("member_path", ""))
        archive_sha = str(member.get("archive_sha256", ""))
        if (
            not archive_relative.startswith(prefix)
            or (archive_relative, member_path) in extracted_members
            or (archive_relative, archive_sha, member_path) in historical_extracted_members
        ):
            continue
        member_name = Path(member_path).name
        if not member_name.lower().endswith(".csv"):
            continue
        stem = Path(member_name).stem
        try:
            day = date.fromisoformat(f"{stem[:4]}-{stem[4:6]}-{stem[6:8]}")
        except ValueError:
            continue
        if (start and day < start) or (end and day > end):
            continue
        archive = (source_root / Path(archive_relative)).resolve()
        if source_root not in archive.parents or not archive.is_file():
            raise QmtDataError(f"inventory archive path is invalid: {archive_relative}")
        selected.append(
            _SourceCandidate(
                identity=f"{archive_relative}@{member['archive_sha256']}!{member_path}",
                container=archive,
                expected_container_sha256=str(member["archive_sha256"]),
                expected_container_size=int(member["archive_size_bytes"]),
                day=day,
                member_path=member_path,
                expected_member_size=int(member["member_size_bytes"]),
                expected_member_crc32=member.get("member_crc32"),
            )
        )
    return manifest, sorted(selected, key=lambda item: item.identity.casefold())


def _candidate_bytes(candidate: _SourceCandidate) -> tuple[bytes, str]:
    if (
        candidate.container.stat().st_size != candidate.expected_container_size
        or _sha256(candidate.container) != candidate.expected_container_sha256
    ):
        raise QmtDataError(f"source changed after inventory: {candidate.identity}")
    if candidate.member_path is None:
        raw = candidate.container.read_bytes()
    elif candidate.container.suffix.lower() == ".zip":
        with zipfile.ZipFile(candidate.container) as archive:
            raw = archive.read(candidate.member_path)
    else:
        try:
            raw = subprocess.run(
                ["tar", "-xOf", str(candidate.container), candidate.member_path],
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            raise QmtDataError(f"cannot read archive member: {candidate.identity}") from exc
    if candidate.expected_member_size is not None and len(raw) != candidate.expected_member_size:
        raise QmtDataError(f"archive member size mismatch: {candidate.identity}")
    if candidate.expected_member_crc32 is not None:
        crc = f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
        if crc != candidate.expected_member_crc32.lower():
            raise QmtDataError(f"archive member CRC32 mismatch: {candidate.identity}")
    return raw, hashlib.sha256(raw).hexdigest()


def _write_rows_parquet(connection, rows: list[dict[str, object]], path: Path) -> None:
    staging = path.with_suffix(".jsonl")
    with staging.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        source_sql = str(staging).replace("'", "''")
        target_sql = str(path).replace("'", "''")
        connection.execute(
            'COPY (SELECT CAST(trade_date AS DATE) trade_date, instrument, name, industry, '
            'CAST("open" AS DOUBLE) "open", CAST(high AS DOUBLE) high, CAST(low AS DOUBLE) low, '
            'CAST("close" AS DOUBLE) "close", CAST(volume AS DOUBLE) volume, CAST(amount AS DOUBLE) amount, '
            "CAST(adjustment_factor AS DOUBLE) adjustment_factor, CAST(effective_at AS TIMESTAMPTZ) effective_at, "
            "CAST(available_at AS TIMESTAMPTZ) available_at, CAST(ingested_at AS TIMESTAMPTZ) ingested_at, "
            f"source_file_sha256, revision_id FROM read_json_auto('{source_sql}')) "
            f"TO '{target_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)",
        )
    finally:
        staging.unlink(missing_ok=True)


def ingest_daily(
    source_root: str | Path,
    warehouse_root: str | Path,
    inventory_manifest: str | Path,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    initialize_warehouse(warehouse)
    manifest_path = Path(inventory_manifest).expanduser().resolve()
    manifest, files = _inventory_files(manifest_path, source, start_date, end_date)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    batch_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    connection.execute(
        "UPDATE ingest_batches SET completed_at=?, status='INTERRUPTED', "
        "error='recovered after an interrupted local process' WHERE status='RUNNING'",
        [started],
    )
    connection.execute(
        "INSERT INTO ingest_batches VALUES (?, ?, NULL, ?, 'RUNNING', 0, 0, NULL, NULL)",
        [batch_id, started, manifest["snapshot_sha256"]],
    )
    transaction_open = False
    created_snapshot_path: Path | None = None
    try:
        known = {
            (row[0], row[1])
            for row in connection.execute("SELECT relative_path, sha256 FROM source_files").fetchall()
        }
        known_identities = {item[0] for item in known}
        pending = [
            candidate
            for candidate in files
            if (
                candidate.member_path is not None and candidate.identity not in known_identities
            )
            or (
                candidate.member_path is None
                and (candidate.identity, candidate.expected_container_sha256) not in known
            )
        ]
        if not pending:
            latest = connection.execute(
                "SELECT snapshot_id FROM snapshots ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if latest is None:
                raise QmtDataError(
                    "inventory contains no accepted qd_daily CSV files for the requested range"
                )
            connection.execute(
                "UPDATE ingest_batches SET completed_at=?, status='REPLAY_NOOP', snapshot_id=? WHERE batch_id=?",
                [datetime.now(timezone.utc), latest[0] if latest else None, batch_id],
            )
            return {
                "batch_id": batch_id,
                "status": "REPLAY_NOOP",
                "new_source_files": 0,
                "new_revisions": 0,
                "snapshot_id": latest[0] if latest else None,
            }
        ingested_at = datetime.now(timezone.utc)
        connection.execute("BEGIN TRANSACTION")
        transaction_open = True
        pending_by_month: dict[tuple[int, int], list[_SourceCandidate]] = {}
        for candidate in pending:
            pending_by_month.setdefault((candidate.day.year, candidate.day.month), []).append(candidate)
        total_new_files = 0
        total_new_revisions = 0
        total_quarantined_rows = 0
        for (year, month), month_candidates in sorted(pending_by_month.items()):
            month_rows: list[dict[str, object]] = []
            for candidate in month_candidates:
                raw, member_sha = _candidate_bytes(candidate)
                if (candidate.identity, member_sha) in known:
                    continue
                parsed_rows, quarantined = _read_csv_bytes(
                    raw, candidate.identity, member_sha, ingested_at
                )
                month_rows.extend(parsed_rows)
                for item in quarantined:
                    connection.execute(
                        "INSERT INTO quarantines VALUES (?, ?, ?, ?, ?)",
                        [
                            batch_id,
                            item["relative_path"],
                            f"row {item['row_number']}: {item['reason']}",
                            ingested_at,
                            item["row_sha256"],
                        ],
                    )
                total_quarantined_rows += len(quarantined)
                connection.execute(
                    "INSERT INTO source_files VALUES (?, ?, ?, 'qd_daily', ?)",
                    [candidate.identity, member_sha, len(raw), batch_id],
                )
                total_new_files += 1
            if not month_rows:
                continue
            total_new_revisions += len(month_rows)
            partition_dir = warehouse / "parquet" / "qd_daily" / f"year={year}" / f"month={month:02d}"
            partition_dir.mkdir(parents=True, exist_ok=True)
            temp = partition_dir / f"pending-{batch_id}.parquet"
            _write_rows_parquet(connection, month_rows, temp)
            prior = connection.execute(
                "SELECT parquet_relative_path FROM partitions WHERE dataset='qd_daily' AND year=? AND month=? AND active",
                [year, month],
            ).fetchall()
            if prior:
                combined = partition_dir / f"combined-{batch_id}.parquet"
                inputs = [str(warehouse / row[0]) for row in prior] + [str(temp)]
                output_sql = str(combined).replace("'", "''")
                connection.execute(
                    "COPY (SELECT * EXCLUDE(rn) FROM (SELECT *, row_number() OVER "
                    "(PARTITION BY revision_id ORDER BY ingested_at DESC) rn FROM read_parquet(?)) WHERE rn=1 "
                    f"ORDER BY trade_date, instrument, revision_id) TO '{output_sql}' "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)",
                    [inputs],
                )
                temp.unlink()
                temp = combined
            part_sha = _sha256(temp)
            final = partition_dir / f"part-{part_sha}.parquet"
            temp.replace(final)
            stats = connection.execute(
                "SELECT count(*), min(trade_date), max(trade_date) FROM read_parquet(?)", [str(final)]
            ).fetchone()
            connection.execute(
                "UPDATE partitions SET active=false WHERE dataset='qd_daily' AND year=? AND month=? AND active",
                [year, month],
            )
            connection.execute(
                "INSERT INTO partitions VALUES ('qd_daily', ?, ?, ?, ?, ?, ?, ?, ?, true, ?)",
                [
                    year,
                    month,
                    final.relative_to(warehouse).as_posix(),
                    part_sha,
                    final.stat().st_size,
                    stats[0],
                    stats[1],
                    stats[2],
                    batch_id,
                ],
            )
        active = connection.execute(
            "SELECT dataset, year, month, parquet_relative_path, sha256, size_bytes, row_count, "
            "CAST(min_date AS VARCHAR), CAST(max_date AS VARCHAR) FROM partitions WHERE active "
            "ORDER BY dataset, year, month"
        ).fetchall()
        active_paths = [str(warehouse / row[3]) for row in active]
        path_literals = ", ".join(
            "'" + value.replace("'", "''") + "'" for value in active_paths
        )
        connection.execute(
            "CREATE OR REPLACE VIEW qd_daily_revisions AS SELECT * FROM read_parquet(["
            + path_literals
            + "], union_by_name=true)"
        )
        connection.execute(
            "CREATE OR REPLACE VIEW qd_daily_current AS SELECT * EXCLUDE(rn) FROM ("
            "SELECT *, row_number() OVER (PARTITION BY trade_date, instrument ORDER BY "
            "ingested_at DESC, revision_id DESC) rn FROM qd_daily_revisions) WHERE rn=1"
        )
        quarantine_rows = connection.execute(
            "SELECT relative_path, reason, row_sha256 FROM quarantines ORDER BY 1, 2, 3"
        ).fetchall()
        stable = {
            "schema_version": 2,
            "inventory_sha256": manifest["snapshot_sha256"],
            "active_partitions": [list(row) for row in active],
            "quarantines": [list(row) for row in quarantine_rows],
        }
        manifest_sha = hashlib.sha256(
            json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        snapshot_id = manifest_sha
        snapshot = {**stable, "snapshot_id": snapshot_id}
        snapshot_path = warehouse / "snapshots" / f"{snapshot_id}.json"
        snapshot_existed = snapshot_path.exists()
        _atomic_json(snapshot_path, snapshot)
        if not snapshot_existed:
            created_snapshot_path = snapshot_path
        connection.execute(
            "INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?, ?)",
            [snapshot_id, manifest_sha, datetime.now(timezone.utc), snapshot_path.relative_to(warehouse).as_posix()],
        )
        connection.execute(
            "UPDATE ingest_batches SET completed_at=?, status='COMPLETED', new_source_files=?, "
            "new_revisions=?, snapshot_id=? WHERE batch_id=?",
            [datetime.now(timezone.utc), total_new_files, total_new_revisions, snapshot_id, batch_id],
        )
        connection.execute("COMMIT")
        transaction_open = False
        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "new_source_files": total_new_files,
            "new_revisions": total_new_revisions,
            "snapshot_id": snapshot_id,
            "active_partition_count": len(active),
            "quarantined_rows": total_quarantined_rows,
        }
    except Exception as exc:
        if transaction_open:
            connection.execute("ROLLBACK")
        if created_snapshot_path is not None:
            created_snapshot_path.unlink(missing_ok=True)
        connection.execute(
            "UPDATE ingest_batches SET completed_at=?, status='FAILED', error=? WHERE batch_id=?",
            [datetime.now(timezone.utc), str(exc), batch_id],
        )
        raise
    finally:
        connection.close()


def verify_snapshot(warehouse_root: str | Path, snapshot_id: str) -> dict[str, object]:
    warehouse = Path(warehouse_root).expanduser().resolve()
    path = warehouse / "snapshots" / f"{snapshot_id}.json"
    if not path.is_file():
        raise QmtDataError(f"snapshot does not exist: {snapshot_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    stable_keys = ["schema_version", "inventory_sha256", "active_partitions"]
    if int(payload.get("schema_version", 1)) >= 2:
        stable_keys.append("quarantines")
    stable = {key: payload[key] for key in stable_keys}
    computed = hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    failures: list[str] = []
    if computed != snapshot_id:
        failures.append("snapshot hash mismatch")
    catalog = warehouse / "catalog" / "warehouse.duckdb"
    if not catalog.is_file():
        failures.append("warehouse catalog is missing")
    else:
        connection = _duckdb().connect(str(catalog), read_only=True)
        try:
            row = connection.execute(
                "SELECT manifest_sha256 FROM snapshots WHERE snapshot_id=?", [snapshot_id]
            ).fetchone()
        finally:
            connection.close()
        if row is None or row[0] != computed:
            failures.append("snapshot is not bound in the warehouse catalog")
    parquet_paths: list[str] = []
    for row in payload["active_partitions"]:
        relative, expected_sha, size = row[3], row[4], int(row[5])
        file = (warehouse / relative).resolve()
        if warehouse not in file.parents or not file.is_file():
            failures.append(f"missing partition: {relative}")
            continue
        if file.stat().st_size != size or _sha256(file) != expected_sha:
            failures.append(f"partition integrity mismatch: {relative}")
        parquet_paths.append(str(file))
    revision_rows = current_rows = duplicate_current_keys = timing_violations = 0
    if parquet_paths:
        connection = _duckdb().connect()
        try:
            revision_rows = connection.execute("SELECT count(*) FROM read_parquet(?)", [parquet_paths]).fetchone()[0]
            current_sql = (
                "SELECT * EXCLUDE(rn) FROM (SELECT *, row_number() OVER (PARTITION BY trade_date, instrument "
                "ORDER BY ingested_at DESC, revision_id DESC) rn FROM read_parquet(?)) WHERE rn=1"
            )
            current_rows = connection.execute(f"SELECT count(*) FROM ({current_sql})", [parquet_paths]).fetchone()[0]
            duplicate_current_keys = connection.execute(
                f"SELECT count(*) FROM (SELECT trade_date, instrument, count(*) n FROM ({current_sql}) "
                "GROUP BY 1,2 HAVING n>1)", [parquet_paths]
            ).fetchone()[0]
            timing_violations = connection.execute(
                "SELECT count(*) FROM read_parquet(?) WHERE effective_at > available_at OR available_at > ingested_at",
                [parquet_paths],
            ).fetchone()[0]
        finally:
            connection.close()
    if duplicate_current_keys:
        failures.append("duplicate current keys")
    if timing_violations:
        failures.append("PIT timing violations")
    return {
        "snapshot_id": snapshot_id,
        "passed": not failures,
        "failures": failures,
        "active_partition_count": len(parquet_paths),
        "revision_rows": revision_rows,
        "current_rows": current_rows,
        "duplicate_current_keys": duplicate_current_keys,
        "timing_violations": timing_violations,
    }


def weekly_update(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    rehash_all: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    from .asset_inventory import inventory_assets

    warehouse = Path(warehouse_root).expanduser().resolve()
    inventory = inventory_assets(source_root, warehouse / "inventory", rehash_all=rehash_all)
    ingest = ingest_daily(
        source_root,
        warehouse,
        inventory["manifest_path"],
        start_date=start_date,
        end_date=end_date,
    )
    verification = verify_snapshot(warehouse, str(ingest["snapshot_id"])) if ingest["snapshot_id"] else None
    return {"inventory": inventory, "ingest": ingest, "verification": verification}
