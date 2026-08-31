from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

from .data_warehouse import _atomic_json, _duckdb, _sha256, initialize_warehouse
from .models import QmtDataError
from .qd_alternative import (
    COMMON_COLUMNS,
    DEFAULT_CLOCKS,
    SOURCE_FIELDS,
    AlternativeObservation,
    QdAlternativeAudit,
    QdAlternativeDataset,
    SourceKind,
)

MULTISOURCE_SCHEMA_VERSION = 1
_SHANGHAI = timezone(timedelta(hours=8))
_DATE_TOKEN = re.compile(r"(20\d{6})")


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    folder: str
    grain: str
    date_column: str | None
    entity_column: str | None
    name_column: str | None
    effective_clock: str
    available_clock: str
    unique_daily_entity: bool = False
    factor_source_kind: SourceKind | None = None
    allow_undated: bool = False
    formats: tuple[str, ...] = ("csv", "archive")


DATASET_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec("qd_index", "10大指数", "index_day", "日期", "代码", None, "15:00:00", "18:00:00", True),
    DatasetSpec("qd_sector_flow", "板块资金流向", "sector_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
    DatasetSpec("qd_chip", "筹码分布", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True, "chip"),
    DatasetSpec("qd_eastmoney_flow", "东财资金流向", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
    DatasetSpec("qd_minute", "分钟K线合集", "stock_minute", "日期", None, None, "09:30:00", "09:30:00", formats=("archive",)),
    DatasetSpec("qd_daily", "股票日K_按日期", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
    DatasetSpec("qd_fundamental", "基本面指标", "stock_day_vendor_snapshot", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
    DatasetSpec("qd_auction", "集合竞价", "stock_auction_day", "日期", "代码", "名称", "09:25:00", "09:26:00", True, "auction"),
    DatasetSpec("qd_technical", "技术面因子", "stock_day_wide", "trade_date", "ts_code", None, "15:00:00", "18:00:00", True),
    DatasetSpec("qd_limit_event", "开盘啦榜单", "stock_event_day", "日期", "代码", "名称", "15:00:00", "18:00:00", False, "limit_event"),
    DatasetSpec("qd_lhb", "龙虎榜", "stock_reason_day", "日期", "代码", "名称", "15:00:00", "18:00:00"),
    DatasetSpec("qd_lhb_seat", "龙虎榜席位", "stock_seat_reason_day", "日期", "代码", "股票名称", "15:00:00", "18:00:00"),
    DatasetSpec("qd_margin", "融资融券明细", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True, "margin"),
    DatasetSpec("qd_industry", "申万行业_按日期", "industry_index_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True, "industry"),
    DatasetSpec("qd_concept", "同花顺概念板块", "heterogeneous_concept_snapshot", None, None, None, "15:00:00", "18:00:00", False, None, True, formats=("csv", "archive", "xlsx", "text")),
    DatasetSpec("qd_hot_rank", "同花顺热榜", "stock_rank_snapshot", "日期", "代码", "名称", "00:00:00", "00:05:00"),
    DatasetSpec("qd_ths_flow", "同花顺资金流向", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
    DatasetSpec("qd_fund_flow", "资金流向", "stock_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True, "fund_flow"),
    DatasetSpec("qd_etf", "ETF_按日期", "etf_day", "日期", "代码", "名称", "15:00:00", "18:00:00", True),
)

_SPEC_BY_DATASET = {item.dataset: item for item in DATASET_SPECS}
_SPEC_BY_FOLDER = {item.folder: item for item in DATASET_SPECS}


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _canonical_iso_timestamp(value: object) -> str:
    text = str(value).replace(" ", "T")
    if re.search(r"[+-]\d{2}$", text):
        text += ":00"
    return text


def _normalized_date(expression: str) -> str:
    digits = f"regexp_replace(CAST({expression} AS VARCHAR), '[^0-9]', '', 'g')"
    return f"try_strptime({digits}, '%Y%m%d')::DATE"


def _filename_date() -> str:
    return "try_strptime(regexp_extract(filename, '(20[0-9]{6})', 1), '%Y%m%d')::DATE"


def _clock_timestamp(day_expression: str, clock: str) -> str:
    return (
        f"timezone('Asia/Shanghai', CAST(CAST(CAST({day_expression} AS DATE) AS VARCHAR) "
        f"|| ' {clock}' AS TIMESTAMP))"
    )


def _schema_fingerprint(columns: tuple[str, ...]) -> str:
    return hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()


def _decode_header(raw: bytes) -> tuple[str, ...]:
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            line = raw.decode(encoding).splitlines()[0]
            return tuple(item.strip() for item in next(csv.reader([line])))
        except (UnicodeError, IndexError, csv.Error):
            continue
    raise QmtDataError("unsupported tabular header encoding")


def initialize_multisource_warehouse(root: str | Path) -> None:
    warehouse = Path(root).expanduser().resolve()
    initialize_warehouse(warehouse)
    (warehouse / "multisource-snapshots").mkdir(exist_ok=True)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_batches (batch_id VARCHAR PRIMARY KEY, "
            "started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, status VARCHAR, snapshot_id VARCHAR, "
            "objects BIGINT, partitions BIGINT, rows BIGINT, error VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_objects (dataset VARCHAR, relative_path VARCHAR, "
            "sha256 VARCHAR, size_bytes BIGINT, format VARCHAR, first_batch_id VARCHAR, "
            "PRIMARY KEY(dataset, relative_path, sha256))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_partitions (dataset VARCHAR, object_sha256 VARCHAR, "
            "parquet_relative_path VARCHAR PRIMARY KEY, sha256 VARCHAR, size_bytes BIGINT, "
            "row_count BIGINT, min_date DATE, max_date DATE, schema_set_sha256 VARCHAR, "
            "active BOOLEAN, batch_id VARCHAR)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_schema_variants (dataset VARCHAR, fingerprint VARCHAR, "
            "columns_json VARCHAR, observed_files BIGINT, first_batch_id VARCHAR, "
            "PRIMARY KEY(dataset, fingerprint))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_documents (dataset VARCHAR, relative_path VARCHAR, "
            "sha256 VARCHAR, size_bytes BIGINT, media_type VARCHAR, first_batch_id VARCHAR, "
            "PRIMARY KEY(dataset, relative_path, sha256))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS multisource_snapshots (snapshot_id VARCHAR PRIMARY KEY, "
            "manifest_sha256 VARCHAR, created_at TIMESTAMPTZ, manifest_relative_path VARCHAR)"
        )
    finally:
        connection.close()


def _extract_archive(archive: Path, destination: Path, seven_zip: Path) -> tuple[Path, ...]:
    try:
        subprocess.run(
            [str(seven_zip), "x", "-y", "-sccUTF-8", f"-o{destination}", str(archive)],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise QmtDataError(f"cannot extract archive: {archive.name}") from exc
    return tuple(sorted(path for path in destination.rglob("*.csv") if path.is_file()))


def _headers(files: tuple[Path, ...]) -> dict[tuple[str, ...], int]:
    variants: dict[tuple[str, ...], int] = {}
    for path in files:
        with path.open("rb") as handle:
            columns = _decode_header(handle.readline())
        variants[columns] = variants.get(columns, 0) + 1
    return variants


def _write_csv_partition(
    connection,
    *,
    spec: DatasetSpec,
    files: tuple[Path, ...],
    container_relative: str,
    container_sha: str,
    target: Path,
    ingested_at: datetime,
) -> tuple[int, str | None, str | None, dict[tuple[str, ...], int]]:
    if not files:
        raise QmtDataError(f"{container_relative}: no CSV members")
    variants = _headers(files)
    filenames = [str(path) for path in files]
    date_expression = (
        _normalized_date(_quote(spec.date_column)) if spec.date_column else _filename_date()
    )
    entity_expression = (
        f"upper(trim(CAST({_quote(spec.entity_column)} AS VARCHAR)))"
        if spec.entity_column
        else "NULL::VARCHAR"
    )
    name_expression = (
        f"trim(CAST({_quote(spec.name_column)} AS VARCHAR))"
        if spec.name_column
        else "NULL::VARCHAR"
    )
    effective = _clock_timestamp(date_expression, spec.effective_clock)
    available = _clock_timestamp(date_expression, spec.available_clock)
    escaped_dataset = spec.dataset.replace("'", "''")
    escaped_container = container_relative.replace("'", "''")
    escaped_sha = container_sha.replace("'", "''")
    escaped_ingested = ingested_at.isoformat().replace("'", "''")
    query = (
        "SELECT * EXCLUDE(filename), "
        f"'{escaped_dataset}' _dataset, '{escaped_container}' _source_container, "
        f"'{escaped_sha}' _source_container_sha256, filename _source_file, "
        f"{date_expression} _trade_date, {entity_expression} _entity_id, "
        f"{name_expression} _entity_name, {effective} _effective_at, {available} _available_at, "
        f"TIMESTAMPTZ '{escaped_ingested}' _ingested_at "
        "FROM read_csv(?, header=true, auto_detect=true, all_varchar=true, union_by_name=true, "
        "filename=true, null_padding=true, sample_size=-1)"
    )
    if spec.unique_daily_entity:
        query += (
            " QUALIFY row_number() OVER (PARTITION BY _trade_date, _entity_id "
            "ORDER BY filename)=1"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    connection.execute(
        f"COPY ({query}) TO {_literal(target)} (FORMAT PARQUET, COMPRESSION ZSTD)",
        [filenames],
    )
    stats = connection.execute(
        "SELECT count(*), CAST(min(_trade_date) AS VARCHAR), CAST(max(_trade_date) AS VARCHAR), "
        "count(*) FILTER (WHERE _trade_date IS NULL) FROM read_parquet(?)",
        [str(target)],
    ).fetchone()
    if int(stats[0]) <= 0:
        raise QmtDataError(f"{container_relative}: tabular object produced no rows")
    if int(stats[3]) > 0 and not spec.allow_undated:
        raise QmtDataError(
            f"{container_relative}: {stats[3]} rows have no parseable observation date"
        )
    if spec.unique_daily_entity:
        duplicate = connection.execute(
            "SELECT count(*) FROM (SELECT _trade_date, _entity_id, count(*) n FROM read_parquet(?) "
            "GROUP BY 1,2 HAVING n > 1)",
            [str(target)],
        ).fetchone()[0]
        if int(duplicate) > 0:
            raise QmtDataError(f"{container_relative}: duplicate daily entity keys: {duplicate}")
    return int(stats[0]), stats[1], stats[2], variants


def _write_xlsx_partition(
    connection,
    *,
    spec: DatasetSpec,
    files: tuple[Path, ...],
    container_relative: str,
    container_sha: str,
    target: Path,
    ingested_at: datetime,
) -> tuple[int, str | None, str | None, dict[tuple[str, ...], int]]:
    def xlsx_rows(path: Path):
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        with zipfile.ZipFile(path) as workbook:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                for item in root.findall(f"{namespace}si"):
                    shared.append("".join(node.text or "" for node in item.iter(f"{namespace}t")))
            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in workbook.namelist():
                candidates = sorted(
                    name
                    for name in workbook.namelist()
                    if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                )
                if not candidates:
                    raise QmtDataError(f"XLSX has no worksheet: {path.name}")
                sheet_name = candidates[0]
            root = ElementTree.fromstring(workbook.read(sheet_name))
            for row in root.iter(f"{namespace}row"):
                values: dict[int, object] = {}
                maximum = -1
                for cell in row.findall(f"{namespace}c"):
                    reference = cell.attrib.get("r", "A1")
                    letters = "".join(character for character in reference if character.isalpha())
                    index = 0
                    for character in letters.upper():
                        index = index * 26 + ord(character) - 64
                    index -= 1
                    maximum = max(maximum, index)
                    kind = cell.attrib.get("t")
                    value_node = cell.find(f"{namespace}v")
                    if kind == "inlineStr":
                        values[index] = "".join(
                            node.text or "" for node in cell.iter(f"{namespace}t")
                        )
                    elif value_node is None:
                        values[index] = None
                    elif kind == "s":
                        values[index] = shared[int(value_node.text or "0")]
                    elif kind in {"str", "e"}:
                        values[index] = value_node.text
                    else:
                        text = value_node.text or ""
                        try:
                            number = float(text)
                            values[index] = int(number) if number.is_integer() else number
                        except ValueError:
                            values[index] = text
                yield tuple(values.get(index) for index in range(maximum + 1))

    variants: dict[tuple[str, ...], int] = {}
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", encoding="utf-8", delete=False) as out:
        staging = Path(out.name)
        for path in files:
            rows = iter(xlsx_rows(path))
            columns = tuple(str(value or "").strip() for value in next(rows))
            variants[columns] = variants.get(columns, 0) + 1
            match = _DATE_TOKEN.search(path.stem)
            if not match:
                raise QmtDataError(f"XLSX filename has no observation date: {path.name}")
            day = date.fromisoformat(
                f"{match.group(1)[:4]}-{match.group(1)[4:6]}-{match.group(1)[6:]}"
            )
            for values in rows:
                if not any(value is not None for value in values):
                    continue
                payload = {
                    columns[i]: values[i]
                    for i in range(min(len(columns), len(values)))
                }
                payload.update(
                    {
                        "_dataset": spec.dataset,
                        "_source_container": container_relative,
                        "_source_container_sha256": container_sha,
                        "_source_file": path.as_posix(),
                        "_trade_date": day.isoformat(),
                        "_entity_id": None,
                        "_entity_name": None,
                        "_effective_at": datetime.combine(
                            day,
                            time.fromisoformat(spec.effective_clock),
                            _SHANGHAI,
                        ).isoformat(),
                        "_available_at": datetime.combine(
                            day,
                            time.fromisoformat(spec.available_clock),
                            _SHANGHAI,
                        ).isoformat(),
                        "_ingested_at": ingested_at.isoformat(),
                    }
                )
                out.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection.execute(
            "COPY (SELECT * FROM read_json_auto(?, union_by_name=true, "
            f"maximum_object_size=16777216)) TO {_literal(target)} "
            "(FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(staging)],
        )
        stats = connection.execute(
            "SELECT count(*), CAST(min(_trade_date) AS VARCHAR), CAST(max(_trade_date) AS VARCHAR) "
            "FROM read_parquet(?)",
            [str(target)],
        ).fetchone()
    finally:
        staging.unlink(missing_ok=True)
    return int(stats[0]), stats[1], stats[2], variants


def _xlsx_has_worksheet(path: Path) -> bool:
    """Return whether an OOXML workbook contains a readable worksheet part.

    Some vendor downloads use an ``.xlsx`` suffix for empty/report-wrapper
    artifacts.  They remain provenance documents, but must not be fabricated
    into observation rows or abort ingestion of unrelated source objects.
    """
    try:
        with zipfile.ZipFile(path) as workbook:
            return any(
                name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                for name in workbook.namelist()
            )
    except (OSError, zipfile.BadZipFile):
        return False


def _snapshot(connection, warehouse: Path) -> str:
    objects = [
        {"dataset": str(row[0]), "relative_path": str(row[1]), "sha256": str(row[2]), "size_bytes": int(row[3]), "format": str(row[4])}
        for row in connection.execute(
            "SELECT dataset, relative_path, sha256, size_bytes, format FROM multisource_objects ORDER BY 1,2,3"
        ).fetchall()
    ]
    partitions = [
        {"dataset": str(row[0]), "object_sha256": str(row[1]), "path": str(row[2]), "sha256": str(row[3]), "size_bytes": int(row[4]), "rows": int(row[5]), "min_date": str(row[6]), "max_date": str(row[7]), "schema_set_sha256": str(row[8])}
        for row in connection.execute(
            "SELECT dataset, object_sha256, parquet_relative_path, sha256, size_bytes, row_count, "
            "min_date, max_date, schema_set_sha256 FROM multisource_partitions WHERE active ORDER BY 1,2,3"
        ).fetchall()
    ]
    schemas = [
        {"dataset": str(row[0]), "fingerprint": str(row[1]), "columns": json.loads(row[2]), "observed_files": int(row[3])}
        for row in connection.execute(
            "SELECT dataset, fingerprint, columns_json, observed_files FROM multisource_schema_variants ORDER BY 1,2"
        ).fetchall()
    ]
    stable = {"schema_version": MULTISOURCE_SCHEMA_VERSION, "dataset_specs": [asdict(item) for item in DATASET_SPECS], "objects": objects, "partitions": partitions, "schemas": schemas}
    snapshot_id = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload = {**stable, "snapshot_id": snapshot_id, "created_at": datetime.now(timezone.utc).isoformat()}
    path = warehouse / "multisource-snapshots" / f"{snapshot_id}.json"
    if not path.exists():
        _atomic_json(path, payload)
    connection.execute(
        "INSERT OR IGNORE INTO multisource_snapshots VALUES (?, ?, ?, ?)",
        [snapshot_id, snapshot_id, datetime.now(timezone.utc), path.relative_to(warehouse).as_posix()],
    )
    return snapshot_id


def ingest_multisource_assets(
    source_root: str | Path,
    warehouse_root: str | Path,
    *,
    seven_zip_executable: str | Path,
    datasets: tuple[str, ...] | None = None,
) -> dict[str, object]:
    source = Path(source_root).expanduser().resolve()
    warehouse = Path(warehouse_root).expanduser().resolve()
    seven_zip = Path(seven_zip_executable).expanduser().resolve()
    if not source.is_dir() or not seven_zip.is_file():
        raise QmtDataError("multisource ingestion requires a valid source root and 7-Zip executable")
    selected_specs = tuple(
        item for item in DATASET_SPECS
        if item.dataset not in {"qd_daily", "qd_minute"} and (datasets is None or item.dataset in datasets)
    )
    if datasets is not None and set(datasets) != {item.dataset for item in selected_specs}:
        raise QmtDataError("unknown or separately-managed multisource dataset requested")
    initialize_multisource_warehouse(warehouse)
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    batch_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    connection.execute(
        "UPDATE multisource_batches SET completed_at=?, status='INTERRUPTED', error='recovered after interrupted process' WHERE status='RUNNING'",
        [started],
    )
    connection.execute(
        "INSERT INTO multisource_batches VALUES (?, ?, NULL, 'RUNNING', NULL, 0, 0, 0, NULL)",
        [batch_id, started],
    )
    known = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in connection.execute(
            "SELECT dataset, relative_path, sha256 FROM multisource_objects"
        ).fetchall()
    }
    objects = partitions = total_rows = 0
    try:
        for spec in selected_specs:
            folder = source / spec.folder
            if not folder.is_dir():
                raise QmtDataError(f"declared dataset folder is missing: {spec.folder}")
            text_documents = tuple(
                sorted(path for path in folder.rglob("*.txt") if path.is_file())
            )
            all_xlsx = tuple(
                sorted(path for path in folder.rglob("*.xlsx") if path.is_file())
            )
            direct_xlsx = tuple(
                path
                for path in all_xlsx
                if _DATE_TOKEN.search(path.stem) and _xlsx_has_worksheet(path)
            )
            binary_documents = tuple(path for path in all_xlsx if path not in direct_xlsx)
            for path in (*text_documents, *binary_documents):
                relative = path.relative_to(source).as_posix()
                digest = _sha256(path)
                connection.execute(
                    "INSERT OR IGNORE INTO multisource_documents VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        spec.dataset,
                        relative,
                        digest,
                        path.stat().st_size,
                        (
                            "text/plain"
                            if path.suffix.lower() == ".txt"
                            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        ),
                        batch_id,
                    ],
                )
            archives = tuple(sorted(path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in {".zip", ".7z", ".rar"}))
            direct_csv = tuple(sorted(path for path in folder.rglob("*.csv") if "历史数据压缩包" not in path.parts))
            direct_hashes = {_sha256(path) for path in (*direct_csv, *direct_xlsx)}
            groups: list[tuple[str, tuple[Path, ...], Path | None, str, int, str]] = []
            if direct_csv:
                identity = "__direct_csv__"
                digest = hashlib.sha256("".join(f"{p.relative_to(source).as_posix()}:{_sha256(p)}" for p in direct_csv).encode()).hexdigest()
                groups.append((identity, direct_csv, None, digest, sum(p.stat().st_size for p in direct_csv), "csv-set"))
            if direct_xlsx:
                identity = "__direct_xlsx__"
                digest = hashlib.sha256("".join(f"{p.relative_to(source).as_posix()}:{_sha256(p)}" for p in direct_xlsx).encode()).hexdigest()
                groups.append((identity, direct_xlsx, None, digest, sum(p.stat().st_size for p in direct_xlsx), "xlsx-set"))
            for archive in archives:
                groups.append((archive.relative_to(source).as_posix(), (), archive, _sha256(archive), archive.stat().st_size, "archive"))
            for relative, files, archive, digest, size_bytes, object_format in groups:
                if (spec.dataset, relative, digest) in known:
                    continue
                with tempfile.TemporaryDirectory(prefix=f"stephen-quant-{spec.dataset}-") as temporary:
                    if archive is not None:
                        files = _extract_archive(archive, Path(temporary), seven_zip)
                        files = tuple(path for path in files if _sha256(path) not in direct_hashes)
                    if not files:
                        connection.execute(
                            "UPDATE multisource_partitions SET active=false WHERE dataset=? AND "
                            "object_sha256 IN (SELECT sha256 FROM multisource_objects "
                            "WHERE dataset=? AND relative_path=?)",
                            [spec.dataset, spec.dataset, relative],
                        )
                        connection.execute(
                            "INSERT INTO multisource_objects VALUES (?, ?, ?, ?, ?, ?)",
                            [spec.dataset, relative, digest, size_bytes, object_format, batch_id],
                        )
                        objects += 1
                        continue
                    pending = warehouse / "staging" / f"{spec.dataset}-{batch_id}-{uuid.uuid4().hex}.parquet"
                    if object_format == "xlsx-set":
                        row_count, min_date, max_date, variants = _write_xlsx_partition(
                            connection, spec=spec, files=files, container_relative=relative,
                            container_sha=digest, target=pending, ingested_at=started,
                        )
                    else:
                        row_count, min_date, max_date, variants = _write_csv_partition(
                            connection, spec=spec, files=files, container_relative=relative,
                            container_sha=digest, target=pending, ingested_at=started,
                        )
                    parquet_sha = _sha256(pending)
                    target = warehouse / "parquet" / "multisource" / spec.dataset / f"{parquet_sha}.parquet"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        pending.unlink()
                    else:
                        pending.replace(target)
                    schema_set_sha = hashlib.sha256("".join(sorted(_schema_fingerprint(columns) for columns in variants)).encode()).hexdigest()
                    connection.execute("BEGIN TRANSACTION")
                    connection.execute(
                        "UPDATE multisource_partitions SET active=false WHERE dataset=? AND "
                        "object_sha256 IN (SELECT sha256 FROM multisource_objects "
                        "WHERE dataset=? AND relative_path=?)",
                        [spec.dataset, spec.dataset, relative],
                    )
                    connection.execute(
                        "INSERT INTO multisource_objects VALUES (?, ?, ?, ?, ?, ?)",
                        [spec.dataset, relative, digest, size_bytes, object_format, batch_id],
                    )
                    connection.execute(
                        "INSERT INTO multisource_partitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, true, ?)",
                        [spec.dataset, digest, target.relative_to(warehouse).as_posix(), parquet_sha, target.stat().st_size, row_count, min_date, max_date, schema_set_sha, batch_id],
                    )
                    for columns, observed in variants.items():
                        fingerprint = _schema_fingerprint(columns)
                        connection.execute(
                            "INSERT INTO multisource_schema_variants VALUES (?, ?, ?, ?, ?) "
                            "ON CONFLICT(dataset, fingerprint) DO UPDATE SET observed_files=multisource_schema_variants.observed_files+excluded.observed_files",
                            [spec.dataset, fingerprint, json.dumps(columns, ensure_ascii=False), observed, batch_id],
                        )
                    connection.execute("COMMIT")
                    objects += 1
                    partitions += 1
                    total_rows += row_count
        snapshot_id = _snapshot(connection, warehouse)
        connection.execute(
            "UPDATE multisource_batches SET completed_at=?, status='COMPLETED', snapshot_id=?, objects=?, partitions=?, rows=? WHERE batch_id=?",
            [datetime.now(timezone.utc), snapshot_id, objects, partitions, total_rows, batch_id],
        )
        return {"batch_id": batch_id, "status": "COMPLETED", "objects": objects, "partitions": partitions, "rows": total_rows, "snapshot_id": snapshot_id}
    except Exception as exc:
        connection.execute(
            "UPDATE multisource_batches SET completed_at=?, status='FAILED', error=? WHERE batch_id=?",
            [datetime.now(timezone.utc), str(exc), batch_id],
        )
        raise
    finally:
        connection.close()


def verify_multisource_snapshot(warehouse_root: str | Path, snapshot_id: str) -> dict[str, object]:
    warehouse = Path(warehouse_root).expanduser().resolve()
    manifest = warehouse / "multisource-snapshots" / f"{snapshot_id}.json"
    failures: list[str] = []
    if not manifest.is_file():
        return {"snapshot_id": snapshot_id, "passed": False, "failures": ["snapshot manifest missing"]}
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    stable = {key: payload[key] for key in ("schema_version", "dataset_specs", "objects", "partitions", "schemas")}
    actual = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if actual != snapshot_id:
        failures.append("snapshot manifest hash mismatch")
    rows = 0
    for item in payload["partitions"]:
        path = warehouse / item["path"]
        if not path.is_file() or path.stat().st_size != int(item["size_bytes"]):
            failures.append(f"partition missing or size mismatch: {item['path']}")
            continue
        if _sha256(path) != item["sha256"]:
            failures.append(f"partition hash mismatch: {item['path']}")
        rows += int(item["rows"])
    declared = {item["dataset"] for item in payload["dataset_specs"]}
    observed = {item["dataset"] for item in payload["partitions"]}
    connection = _duckdb().connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        if connection.execute(
            "SELECT count(*) FROM partitions WHERE dataset='qd_daily' AND active"
        ).fetchone()[0]:
            observed.add("qd_daily")
        minute_table = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='minute_partitions'"
        ).fetchone()[0]
        if minute_table and connection.execute(
            "SELECT count(*) FROM minute_partitions"
        ).fetchone()[0]:
            observed.add("qd_minute")
    finally:
        connection.close()
    missing = sorted(declared - observed)
    return {
        "snapshot_id": snapshot_id,
        "passed": not failures,
        "failures": failures,
        "datasets": len(observed),
        "coverage_complete": not missing,
        "missing_datasets": missing,
        "partitions": len(payload["partitions"]),
        "rows": rows,
    }


def latest_multisource_snapshot(warehouse_root: str | Path) -> str:
    warehouse = Path(warehouse_root).expanduser().resolve()
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        row = connection.execute(
            "SELECT snapshot_id FROM multisource_snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise QmtDataError("warehouse has no multisource snapshot")
    snapshot = str(row[0])
    verification = verify_multisource_snapshot(warehouse, snapshot)
    if not verification["passed"]:
        raise QmtDataError("multisource snapshot verification failed: " + "; ".join(verification["failures"]))
    return snapshot


def load_warehouse_alternative(
    warehouse_root: str | Path,
    *,
    source_kind: SourceKind,
    start_date: str,
    end_date: str,
    instruments: tuple[str, ...] = (),
    verified_snapshot_id: str | None = None,
) -> QdAlternativeDataset:
    warehouse = Path(warehouse_root).expanduser().resolve()
    snapshot = verified_snapshot_id or latest_multisource_snapshot(warehouse)
    if verified_snapshot_id is not None and verify_multisource_snapshot(warehouse, snapshot)["passed"] is not True:
        raise QmtDataError("declared multisource snapshot failed verification")
    spec = next((item for item in DATASET_SPECS if item.factor_source_kind == source_kind), None)
    if spec is None:
        raise QmtDataError(f"warehouse has no factor mapping for {source_kind}")
    connection = _duckdb().connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        paths = [
            str(warehouse / row[0])
            for row in connection.execute(
                "SELECT parquet_relative_path FROM multisource_partitions WHERE dataset=? AND active ORDER BY parquet_relative_path",
                [spec.dataset],
            ).fetchall()
        ]
        if not paths:
            raise QmtDataError(f"warehouse has no active partitions for {source_kind}")
        wanted = sorted({item.upper() for item in instruments})
        where = "_trade_date BETWEEN ? AND ?"
        params: list[object] = [paths, start_date, end_date]
        if wanted:
            where += " AND upper(_entity_id) IN (SELECT * FROM unnest(?))"
            params.append(wanted)
        fields = SOURCE_FIELDS[source_kind]
        projections = []
        for canonical, field in fields.items():
            if source_kind == "limit_event" and field.column.startswith("<derived"):
                projections.append(f"1.0::{ 'DOUBLE' } AS {_quote(canonical)}")
            else:
                projections.append(
                    f"try_cast({_quote(field.column)} AS DOUBLE) * {field.scale!r} AS {_quote(canonical)}"
                )
        query = (
            "SELECT CAST(_trade_date AS VARCHAR), upper(_entity_id), coalesce(_entity_name,''), "
            "CAST(_effective_at AS VARCHAR), CAST(_available_at AS VARCHAR), CAST(_ingested_at AS VARCHAR), "
            + ", ".join(projections)
            + f" FROM read_parquet(?, union_by_name=true) WHERE {where} ORDER BY 1,2"
        )
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()
    if not rows:
        raise QmtDataError("warehouse alternative selection contains no observations")
    observations = tuple(
        AlternativeObservation(
            source_kind=source_kind,
            trade_date=str(row[0]),
            instrument=str(row[1]),
            name=str(row[2]),
            effective_at=_canonical_iso_timestamp(row[3]),
            available_at=_canonical_iso_timestamp(row[4]),
            ingested_at=_canonical_iso_timestamp(row[5]),
            values=tuple((canonical, None if row[index + 6] is None else float(row[index + 6])) for index, canonical in enumerate(fields)),
        )
        for row in rows
    )
    missing_values = {
        canonical: sum(item.value(canonical) is None for item in observations)
        for canonical in fields
    }
    return QdAlternativeDataset(
        observations=observations,
        audit=QdAlternativeAudit(
            adapter_version="qd-multisource-warehouse-adapter-1.0.0",
            source_kind=source_kind,
            source_sha256=snapshot,
            source_files=len(paths),
            rows=len(observations),
            instruments=len({row.instrument for row in observations}),
            start_date=min(row.trade_date for row in observations),
            end_date=max(row.trade_date for row in observations),
            column_mapping={**COMMON_COLUMNS, **{key: value.column for key, value in fields.items()}},
            unit_scales={key: value.scale for key, value in fields.items()},
            missing_values={key: value for key, value in missing_values.items() if value},
            missing_names=sum(not row.name for row in observations),
            availability_policy=f"schema-fixed effective={DEFAULT_CLOCKS[source_kind][0]}, available={DEFAULT_CLOCKS[source_kind][1]}, timezone=+08:00",
            warnings=("Source rows are read from a verified immutable warehouse snapshot.",),
        ),
    )
