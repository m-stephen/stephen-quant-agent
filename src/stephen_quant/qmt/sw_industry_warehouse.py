from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlparse

from .data_warehouse import _atomic_json, _duckdb, _sha256, initialize_warehouse
from .models import QmtDataError

SW_L2_SCHEMA_VERSION = 1
_SHANGHAI = timezone(timedelta(hours=8))
_INDUSTRY_CODE = re.compile(r"^\d{6}$")
_INSTRUMENT = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


@dataclass(frozen=True)
class SwL2YearQuality:
    year: int
    as_of: str
    coverage_grade: str
    industries: int
    stock_rows: int
    distinct_stocks: int
    sealed: bool


@dataclass(frozen=True)
class SwL2IngestResult:
    status: str
    snapshot_id: str
    source_sha256: str
    source_size_bytes: int
    row_count: int
    change_count: int
    year_quality: tuple[SwL2YearQuality, ...]
    research_tier: str = "PIT_LITE"
    formal_research_eligible: bool = False


def initialize_sw_l2_warehouse(root: str | Path) -> None:
    warehouse = Path(root).expanduser().resolve()
    initialize_warehouse(warehouse)
    for folder in ("sw-l2-sources", "sw-l2-snapshots", "parquet/sw_l2_memberships"):
        (warehouse / folder).mkdir(parents=True, exist_ok=True)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sw_l2_batches (batch_id VARCHAR PRIMARY KEY, "
            "started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, status VARCHAR, "
            "source_kind VARCHAR, source_locator_sha256 VARCHAR, source_sha256 VARCHAR, "
            "source_size_bytes BIGINT, snapshot_id VARCHAR, error VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sw_l2_snapshots (snapshot_id VARCHAR PRIMARY KEY, "
            "schema_version INTEGER, source_sha256 VARCHAR, source_size_bytes BIGINT, "
            "source_relative_path VARCHAR, parquet_relative_path VARCHAR, parquet_sha256 VARCHAR, "
            "parquet_size_bytes BIGINT, row_count BIGINT, change_count BIGINT, "
            "retrieved_at TIMESTAMPTZ, manifest_relative_path VARCHAR, research_tier VARCHAR, "
            "formal_research_eligible BOOLEAN)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sw_l2_year_quality (snapshot_id VARCHAR, snapshot_year INTEGER, "
            "as_of DATE, coverage_grade VARCHAR, industries BIGINT, stock_rows BIGINT, "
            "distinct_stocks BIGINT, sealed BOOLEAN, PRIMARY KEY(snapshot_id, snapshot_year))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sw_l2_changes (snapshot_id VARCHAR, change_year INTEGER, "
            "instrument VARCHAR, from_industry_code VARCHAR, to_industry_code VARCHAR, "
            "change_type VARCHAR, effective_at TIMESTAMPTZ, available_at TIMESTAMPTZ, "
            "PRIMARY KEY(snapshot_id, change_year, instrument, change_type))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sw_l2_remote_state (source_locator_sha256 VARCHAR PRIMARY KEY, "
            "etag VARCHAR, last_modified VARCHAR, last_checked_at TIMESTAMPTZ, "
            "last_success_snapshot_id VARCHAR)"
        )
        _refresh_sw_l2_views(connection, warehouse)
    finally:
        connection.close()


def _timestamp(day: date, clock: time) -> datetime:
    return datetime.combine(day, clock, tzinfo=_SHANGHAI)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise QmtDataError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QmtDataError(f"{label} must be a non-empty string")
    return value.strip()


def _normalize_payload(raw: bytes) -> tuple[list[dict[str, object]], list[dict[str, object]], tuple[SwL2YearQuality, ...], dict[str, object]]:
    try:
        payload = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise QmtDataError(f"invalid Shenwan L2 JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise QmtDataError("Shenwan L2 JSON must contain a meta object")
    years = payload.get("years")
    if not isinstance(years, list) or not years:
        raise QmtDataError("Shenwan L2 JSON must contain non-empty years")
    generated = payload["meta"].get("generated_years")
    if not isinstance(generated, list) or any(not isinstance(item, int) for item in generated):
        raise QmtDataError("meta.generated_years must contain integers")
    snapshot_labels = payload["meta"].get("snapshot_labels")
    if snapshot_labels is not None and not isinstance(snapshot_labels, dict):
        raise QmtDataError("meta.snapshot_labels must be an object when present")

    rows: list[dict[str, object]] = []
    qualities: list[SwL2YearQuality] = []
    seen_years: set[int] = set()
    year_maps: dict[int, dict[str, str]] = {}
    for volume in years:
        if not isinstance(volume, dict) or not isinstance(volume.get("year"), int):
            raise QmtDataError("every year volume must contain an integer year")
        year = int(volume["year"])
        if year in seen_years:
            raise QmtDataError(f"duplicate snapshot year: {year}")
        seen_years.add(year)
        try:
            as_of = date.fromisoformat(_required_string(volume.get("as_of"), f"{year}.as_of"))
        except ValueError as exc:
            raise QmtDataError(f"invalid as_of for {year}") from exc
        if as_of.year != year:
            raise QmtDataError(f"snapshot year/as_of mismatch: {year} vs {as_of}")
        if snapshot_labels is not None:
            declared_label = snapshot_labels.get(str(year))
            if declared_label is not None and declared_label != as_of.isoformat():
                raise QmtDataError(f"meta snapshot label mismatch for {year}")
        industries = volume.get("industries")
        if not isinstance(industries, list):
            raise QmtDataError(f"{year}.industries must be an array")
        if volume.get("industry_count") != len(industries):
            raise QmtDataError(f"{year} declared industry count mismatch")
        industry_codes: set[str] = set()
        stock_codes: set[str] = set()
        mapping: dict[str, str] = {}
        stock_rows = 0
        for industry in industries:
            if not isinstance(industry, dict):
                raise QmtDataError(f"{year} industry must be an object")
            industry_code = _required_string(industry.get("code"), f"{year}.industry.code")
            industry_name = _required_string(industry.get("name"), f"{year}.industry.name")
            if not _INDUSTRY_CODE.fullmatch(industry_code):
                raise QmtDataError(f"invalid industry code: {industry_code}")
            if industry_code in industry_codes:
                raise QmtDataError(f"duplicate industry code in {year}: {industry_code}")
            industry_codes.add(industry_code)
            stocks = industry.get("stocks")
            if not isinstance(stocks, list) or industry.get("count") != len(stocks):
                raise QmtDataError(f"{year}/{industry_code} declared stock count mismatch")
            for stock in stocks:
                if not isinstance(stock, dict):
                    raise QmtDataError(f"{year}/{industry_code} stock must be an object")
                instrument = _required_string(stock.get("code"), "stock.code").upper()
                instrument_name = _required_string(stock.get("name"), "stock.name")
                if not _INSTRUMENT.fullmatch(instrument):
                    raise QmtDataError(f"invalid A-share instrument: {instrument}")
                if instrument in stock_codes:
                    raise QmtDataError(f"duplicate stock assignment in {year}: {instrument}")
                stock_codes.add(instrument)
                mapping[instrument] = industry_code
                stock_rows += 1
                effective_at = _timestamp(as_of, time(15, 0))
                available_at = _timestamp(as_of + timedelta(days=1), time(9, 30))
                rows.append(
                    {
                        "snapshot_year": year,
                        "as_of": as_of.isoformat(),
                        "industry_code": industry_code,
                        "industry_name": industry_name,
                        "instrument": instrument,
                        "instrument_name": instrument_name,
                        "effective_at": effective_at.isoformat(),
                        "available_at": available_at.isoformat(),
                        "availability_quality": "ANNUAL_SNAPSHOT_PROXY",
                        "coverage_grade": "PARTIAL" if year == 2020 else "PIT_LITE_B",
                        "sealed": year >= 2025,
                    }
                )
        if volume.get("stock_total") != stock_rows:
            raise QmtDataError(f"{year} declared stock total mismatch")
        year_maps[year] = mapping
        qualities.append(
            SwL2YearQuality(
                year=year,
                as_of=as_of.isoformat(),
                coverage_grade="PARTIAL" if year == 2020 else "PIT_LITE_B",
                industries=len(industry_codes),
                stock_rows=stock_rows,
                distinct_stocks=len(stock_codes),
                sealed=year >= 2025,
            )
        )
    if sorted(seen_years) != sorted(generated):
        raise QmtDataError("meta.generated_years does not match year volumes")

    changes: list[dict[str, object]] = []
    ordered = sorted(year_maps)
    for previous_year, current_year in pairwise(ordered):
        previous = year_maps[previous_year]
        current = year_maps[current_year]
        current_as_of = date.fromisoformat(next(item.as_of for item in qualities if item.year == current_year))
        effective_at = _timestamp(current_as_of, time(15, 0)).isoformat()
        available_at = _timestamp(current_as_of + timedelta(days=1), time(9, 30)).isoformat()
        for instrument in sorted(set(previous) | set(current)):
            before, after = previous.get(instrument), current.get(instrument)
            if before == after:
                continue
            change_type = "ADDED" if before is None else "REMOVED" if after is None else "RECLASSIFIED"
            changes.append(
                {
                    "change_year": current_year,
                    "instrument": instrument,
                    "from_industry_code": before,
                    "to_industry_code": after,
                    "change_type": change_type,
                    "effective_at": effective_at,
                    "available_at": available_at,
                }
            )
    rows.sort(key=lambda item: (int(item["snapshot_year"]), str(item["industry_code"]), str(item["instrument"])))
    metadata = {
        "title": payload["meta"].get("title"),
        "source": payload["meta"].get("source"),
        "note": payload["meta"].get("note"),
    }
    return rows, changes, tuple(qualities), metadata


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _refresh_sw_l2_views(connection, warehouse: Path) -> None:
    partitions = connection.execute(
        "SELECT parquet_relative_path FROM sw_l2_snapshots ORDER BY retrieved_at, snapshot_id"
    ).fetchall()
    if not partitions:
        return
    literals = ",".join(
        "'" + str(warehouse / str(row[0])).replace("'", "''") + "'" for row in partitions
    )
    connection.execute(
        "CREATE OR REPLACE VIEW qd_sw_l2_membership_revisions AS "
        "SELECT membership.*, snapshots.retrieved_at FROM "
        f"read_parquet([{literals}], union_by_name=true) membership "
        "JOIN sw_l2_snapshots snapshots USING(snapshot_id)"
    )
    connection.execute(
        "CREATE OR REPLACE VIEW qd_sw_l2_membership_current AS SELECT * EXCLUDE(rn) FROM ("
        "SELECT *, row_number() OVER (PARTITION BY snapshot_year, instrument ORDER BY "
        "retrieved_at DESC, snapshot_id DESC) rn FROM qd_sw_l2_membership_revisions) WHERE rn=1"
    )


def ingest_sw_l2_bytes(
    warehouse_root: str | Path,
    raw: bytes,
    *,
    source_kind: str,
    source_locator: str,
    retrieved_at: datetime | None = None,
) -> SwL2IngestResult:
    warehouse = Path(warehouse_root).expanduser().resolve()
    initialize_sw_l2_warehouse(warehouse)
    if not raw:
        raise QmtDataError("empty Shenwan L2 source")
    source_sha = hashlib.sha256(raw).hexdigest()
    locator_sha = hashlib.sha256(source_locator.encode("utf-8")).hexdigest()
    observed_at = retrieved_at or datetime.now(timezone.utc)
    rows, changes, quality, metadata = _normalize_payload(raw)
    stable = {
        "schema_version": SW_L2_SCHEMA_VERSION,
        "source_sha256": source_sha,
        "source_size_bytes": len(raw),
        "rows_sha256": hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "changes_sha256": hashlib.sha256(
            json.dumps(changes, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "quality": [asdict(item) for item in quality],
        "metadata": metadata,
        "research_tier": "PIT_LITE",
        "formal_research_eligible": False,
    }
    snapshot_id = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    existing = connection.execute(
        "SELECT row_count, change_count FROM sw_l2_snapshots WHERE snapshot_id=?", [snapshot_id]
    ).fetchone()
    if existing is not None:
        connection.close()
        return SwL2IngestResult(
            "REPLAY_NOOP", snapshot_id, source_sha, len(raw), int(existing[0]), int(existing[1]), quality
        )

    batch_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO sw_l2_batches VALUES (?, ?, NULL, 'RUNNING', ?, ?, ?, ?, NULL, NULL)",
        [batch_id, observed_at, source_kind, locator_sha, source_sha, len(raw)],
    )
    source_relative = f"sw-l2-sources/{source_sha}.json"
    source_path = warehouse / source_relative
    manifest_relative = f"sw-l2-snapshots/{snapshot_id}.json"
    parquet_folder = warehouse / "parquet" / "sw_l2_memberships" / f"snapshot={snapshot_id}"
    staging = warehouse / "staging" / f"sw-l2-{batch_id}"
    staging.mkdir(parents=True, exist_ok=False)
    staged_json = staging / "memberships.jsonl"
    staged_parquet = staging / "memberships.parquet"
    parquet_target: Path | None = None
    manifest_path = warehouse / manifest_relative
    created_parquet = False
    created_manifest = False
    transaction_started = False
    try:
        if not source_path.exists():
            _atomic_bytes(source_path, raw)
        elif _sha256(source_path) != source_sha:
            raise QmtDataError("content-addressed Shenwan source cache mismatch")
        staged_json.write_text(
            "".join(json.dumps({**row, "snapshot_id": snapshot_id, "source_sha256": source_sha}, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        source_literal = str(staged_json).replace("'", "''")
        target_literal = str(staged_parquet).replace("'", "''")
        connection.execute(
            "COPY (SELECT snapshot_id::VARCHAR snapshot_id, snapshot_year::INTEGER snapshot_year, "
            "as_of::DATE as_of, industry_code::VARCHAR industry_code, industry_name::VARCHAR industry_name, "
            "instrument::VARCHAR instrument, instrument_name::VARCHAR instrument_name, "
            "effective_at::TIMESTAMPTZ effective_at, available_at::TIMESTAMPTZ available_at, "
            "availability_quality::VARCHAR availability_quality, coverage_grade::VARCHAR coverage_grade, "
            "sealed::BOOLEAN sealed, source_sha256::VARCHAR source_sha256 "
            f"FROM read_json_auto('{source_literal}') "
            "ORDER BY snapshot_year, industry_code, instrument) "
            f"TO '{target_literal}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        parquet_sha = _sha256(staged_parquet)
        parquet_relative = f"parquet/sw_l2_memberships/snapshot={snapshot_id}/{parquet_sha}.parquet"
        parquet_target = warehouse / parquet_relative
        parquet_folder.mkdir(parents=True, exist_ok=True)
        staged_parquet.replace(parquet_target)
        created_parquet = True
        manifest = {**stable, "snapshot_id": snapshot_id, "parquet_relative_path": parquet_relative, "parquet_sha256": parquet_sha, "parquet_size_bytes": parquet_target.stat().st_size}
        _atomic_json(manifest_path, manifest)
        created_manifest = True
        connection.execute("BEGIN TRANSACTION")
        transaction_started = True
        connection.execute(
            "INSERT INTO sw_l2_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PIT_LITE', false)",
            [snapshot_id, SW_L2_SCHEMA_VERSION, source_sha, len(raw), source_relative, parquet_relative, parquet_sha, parquet_target.stat().st_size, len(rows), len(changes), observed_at, manifest_relative],
        )
        connection.executemany(
            "INSERT INTO sw_l2_year_quality VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [[snapshot_id, item.year, item.as_of, item.coverage_grade, item.industries, item.stock_rows, item.distinct_stocks, item.sealed] for item in quality],
        )
        connection.executemany(
            "INSERT INTO sw_l2_changes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [[snapshot_id, item["change_year"], item["instrument"], item["from_industry_code"], item["to_industry_code"], item["change_type"], item["effective_at"], item["available_at"]] for item in changes],
        )
        connection.execute(
            "UPDATE sw_l2_batches SET completed_at=?, status='COMPLETED', snapshot_id=? WHERE batch_id=?",
            [datetime.now(timezone.utc), snapshot_id, batch_id],
        )
        _refresh_sw_l2_views(connection, warehouse)
        connection.execute("COMMIT")
        transaction_started = False
    except Exception as exc:
        if transaction_started:
            connection.execute("ROLLBACK")
        connection.execute(
            "UPDATE sw_l2_batches SET completed_at=?, status='FAILED', error=? WHERE batch_id=?",
            [datetime.now(timezone.utc), str(exc), batch_id],
        )
        if created_manifest:
            manifest_path.unlink(missing_ok=True)
        if created_parquet and parquet_target is not None:
            parquet_target.unlink(missing_ok=True)
            try:
                parquet_folder.rmdir()
            except OSError:
                pass
        raise
    finally:
        connection.close()
        staged_json.unlink(missing_ok=True)
        staged_parquet.unlink(missing_ok=True)
        staging.rmdir()
    return SwL2IngestResult(
        "COMPLETED", snapshot_id, source_sha, len(raw), len(rows), len(changes), quality
    )


def ingest_sw_l2_file(
    warehouse_root: str | Path, source_file: str | Path
) -> SwL2IngestResult:
    path = Path(source_file).expanduser().resolve()
    if not path.is_file():
        raise QmtDataError(f"Shenwan L2 source does not exist: {path}")
    return ingest_sw_l2_bytes(
        warehouse_root,
        path.read_bytes(),
        source_kind="LOCAL_FILE",
        source_locator=str(path),
    )


def fetch_sw_l2_url(
    warehouse_root: str | Path,
    source_url: str,
    *,
    timeout_seconds: float = 30.0,
    max_bytes: int = 10_000_000,
) -> SwL2IngestResult | dict[str, object]:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise QmtDataError("Shenwan update URL must use http or https")
    warehouse = Path(warehouse_root).expanduser().resolve()
    initialize_sw_l2_warehouse(warehouse)
    locator_sha = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    state = connection.execute(
        "SELECT etag, last_modified, last_success_snapshot_id FROM sw_l2_remote_state "
        "WHERE source_locator_sha256=?",
        [locator_sha],
    ).fetchone()
    connection.close()
    headers = {"Accept": "application/json"}
    if state and state[0]:
        headers["If-None-Match"] = str(state[0])
    if state and state[1]:
        headers["If-Modified-Since"] = str(state[1])
    request = urllib.request.Request(source_url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "text/json", "text/plain", "application/octet-stream"}:
                raise QmtDataError(f"unexpected Shenwan update Content-Type: {content_type}")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise QmtDataError("invalid Shenwan update Content-Length") from exc
                if declared_size > max_bytes:
                    raise QmtDataError("Shenwan update exceeds configured byte limit")
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise QmtDataError("Shenwan update exceeds configured byte limit")
            etag = response.headers.get("ETag")
            last_modified = response.headers.get("Last-Modified")
    except urllib.error.HTTPError as exc:
        if exc.code != 304:
            raise QmtDataError(f"Shenwan update HTTP error: {exc.code}") from exc
        now = datetime.now(timezone.utc)
        connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
        connection.execute(
            "UPDATE sw_l2_remote_state SET last_checked_at=? WHERE source_locator_sha256=?",
            [now, locator_sha],
        )
        connection.close()
        return {"status": "NOT_MODIFIED", "snapshot_id": str(state[2]) if state else None}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise QmtDataError(f"Shenwan update transport error: {exc}") from exc
    result = ingest_sw_l2_bytes(
        warehouse, raw, source_kind="HTTP", source_locator=source_url
    )
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    connection.execute(
        "INSERT OR REPLACE INTO sw_l2_remote_state VALUES (?, ?, ?, ?, ?)",
        [locator_sha, etag, last_modified, datetime.now(timezone.utc), result.snapshot_id],
    )
    connection.close()
    return result


def verify_sw_l2_snapshot(warehouse_root: str | Path, snapshot_id: str) -> dict[str, object]:
    warehouse = Path(warehouse_root).expanduser().resolve()
    manifest_path = warehouse / "sw-l2-snapshots" / f"{snapshot_id}.json"
    if not manifest_path.is_file():
        raise QmtDataError(f"Shenwan L2 snapshot does not exist: {snapshot_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    stable = {key: value for key, value in manifest.items() if key not in {"snapshot_id", "parquet_relative_path", "parquet_sha256", "parquet_size_bytes"}}
    computed = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if computed != snapshot_id:
        failures.append("Shenwan manifest hash mismatch")
    source = (warehouse / "sw-l2-sources" / f"{manifest['source_sha256']}.json").resolve()
    if warehouse not in source.parents or not source.is_file() or _sha256(source) != manifest["source_sha256"]:
        failures.append("Shenwan source cache integrity mismatch")
    parquet = (warehouse / str(manifest["parquet_relative_path"])).resolve()
    if warehouse not in parquet.parents or not parquet.is_file() or parquet.stat().st_size != int(manifest["parquet_size_bytes"]) or _sha256(parquet) != manifest["parquet_sha256"]:
        failures.append("Shenwan Parquet integrity mismatch")
    rows = duplicates = timing = sealed_leaks = 0
    if parquet.is_file():
        connection = _duckdb().connect()
        try:
            rows, duplicates, timing, sealed_leaks = connection.execute(
                "SELECT count(*), count(*)-count(DISTINCT (snapshot_year, instrument)), "
                "count(*) FILTER (WHERE effective_at > available_at), "
                "count(*) FILTER (WHERE snapshot_year >= 2025 AND sealed=false) FROM read_parquet(?)",
                [str(parquet)],
            ).fetchone()
        finally:
            connection.close()
    if int(rows) != int(manifest.get("quality") and sum(int(item["stock_rows"]) for item in manifest["quality"])):
        failures.append("Shenwan row count mismatch")
    if duplicates:
        failures.append("duplicate Shenwan year/instrument keys")
    if timing:
        failures.append("Shenwan PIT timing violations")
    if sealed_leaks:
        failures.append("Shenwan sealed-year flag violations")
    return {
        "snapshot_id": snapshot_id,
        "passed": not failures,
        "failures": failures,
        "row_count": int(rows),
        "duplicate_keys": int(duplicates),
        "timing_violations": int(timing),
        "sealed_flag_violations": int(sealed_leaks),
        "research_tier": "PIT_LITE",
        "formal_research_eligible": False,
    }


def write_sw_l2_reports(result: SwL2IngestResult, output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    json_path = output / "result.json"
    zh_path = output / "result.zh.md"
    en_path = output / "result.en.md"
    _atomic_json(json_path, payload)
    rows_zh = [
        "# 申万二级行业 PIT-Lite 数据结果",
        "",
        f"- 状态：`{result.status}`",
        f"- 快照：`{result.snapshot_id}`",
        f"- 成分行：{result.row_count:,}",
        f"- 年际变化：{result.change_count:,}",
        "- 正式研究资格：否；该数据为年度截面 PIT-Lite，不替代完整事件级 #92 数据。",
        "",
        "| 年份 | 截止日 | 覆盖等级 | 行业 | 股票 | 封存 |",
        "|---:|---|---|---:|---:|---|",
        *[f"| {item.year} | {item.as_of} | {item.coverage_grade} | {item.industries} | {item.stock_rows} | {'是' if item.sealed else '否'} |" for item in result.year_quality],
    ]
    rows_en = [
        "# Shenwan Level-2 PIT-Lite data result",
        "",
        f"- Status: `{result.status}`",
        f"- Snapshot: `{result.snapshot_id}`",
        f"- Membership rows: {result.row_count:,}",
        f"- Annual changes: {result.change_count:,}",
        "- Formal research eligible: no. Annual PIT-Lite snapshots do not replace the event-level #92 dataset.",
        "",
        "| Year | As of | Coverage | Industries | Stocks | Sealed |",
        "|---:|---|---|---:|---:|---|",
        *[f"| {item.year} | {item.as_of} | {item.coverage_grade} | {item.industries} | {item.stock_rows} | {'yes' if item.sealed else 'no'} |" for item in result.year_quality],
    ]
    zh_path.write_text("\n".join(rows_zh) + "\n", encoding="utf-8")
    en_path.write_text("\n".join(rows_en) + "\n", encoding="utf-8")
    return {"json": str(json_path), "zh": str(zh_path), "en": str(en_path)}
