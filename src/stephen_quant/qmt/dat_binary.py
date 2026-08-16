from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import struct
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .csv_adapter import load_qmt_daily_csv
from .models import QmtDailyBar, QmtDataError
from .xtquant_export import CANONICAL_HEADER, normalize_stocks

PARSER_VERSION = "qmt-daily-dat-1.0.0"
MANIFEST_VERSION = "qmt-dat-provenance-1.0.0"
RECORD_SIZE = 64
PRICE_SCALE = 1_000
STOCK_VOLUME_SCALE = 100
MARKET_TIMEZONE = timezone(timedelta(hours=8))
SUPPORTED_MARKETS = {"SH", "SZ", "BJ"}
_A_SHARE_PATTERNS = {
    "SH": re.compile(r"^(?:60[0135]|68[89])\d{3}$"),
    "SZ": re.compile(r"^(?:00[0123]|30[01])\d{3}$"),
    "BJ": re.compile(r"^[489]\d{5}$"),
}
_SCHEMA = {
    "record_size": RECORD_SIZE,
    "byte_order": "little",
    "timestamp": {"offset": 8, "type": "uint32", "unit": "unix_seconds"},
    "open": {"offset": 12, "type": "uint32", "scale": PRICE_SCALE},
    "high": {"offset": 16, "type": "uint32", "scale": PRICE_SCALE},
    "low": {"offset": 20, "type": "uint32", "scale": PRICE_SCALE},
    "close": {"offset": 24, "type": "uint32", "scale": PRICE_SCALE},
    "volume": {
        "offset": 32,
        "type": "uint32",
        "source_unit": "lot",
        "output_unit": "share",
        "scale": STOCK_VOLUME_SCALE,
    },
    "amount": {"offset": 40, "type": "uint64", "unit": "CNY"},
    "pre_close": {"offset": 60, "type": "uint32", "scale": PRICE_SCALE},
}
SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(_SCHEMA, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


@dataclass(frozen=True)
class DatExportConfig:
    datadir: str
    output_csv: str
    start_date: str
    end_date: str
    stocks: tuple[str, ...]
    adjustment: str = "none"
    overwrite: bool = False


@dataclass(frozen=True)
class DatSourceAudit:
    instrument: str
    relative_path: str
    sha256: str
    bytes: int
    records: int
    trailing_bytes: int
    first_date: str
    last_date: str


@dataclass(frozen=True)
class DatExportResult:
    parser_version: str
    schema_sha256: str
    output_csv: str
    manifest_path: str
    adjustment: str
    requested_instruments: int
    exported_instruments: int
    rows: int
    start_date: str
    end_date: str
    output_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class QmtDatError(QmtDataError):
    """Raised when a QMT binary cache cannot satisfy the locked daily schema."""


def _parse_iso_window(config: DatExportConfig) -> tuple[date, date]:
    try:
        start = date.fromisoformat(config.start_date)
        end = date.fromisoformat(config.end_date)
    except ValueError as exc:
        raise QmtDatError("start_date and end_date must be ISO dates") from exc
    if start > end:
        raise QmtDatError("start_date must not be after end_date")
    if config.adjustment != "none":
        raise QmtDatError("direct DAT parsing supports adjustment='none' only")
    return start, end


def _resolve_datadir(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if root.name.lower() != "datadir" and (root / "datadir").is_dir():
        root = root / "datadir"
    if not root.is_dir():
        raise QmtDatError(f"QMT datadir does not exist: {root}")
    return root


def _validate_equity_instrument(instrument: str) -> tuple[str, str]:
    symbol, separator, market = instrument.partition(".")
    if not separator or market not in SUPPORTED_MARKETS:
        raise QmtDatError(f"unsupported DAT instrument: {instrument}")
    if not _A_SHARE_PATTERNS[market].fullmatch(symbol):
        raise QmtDatError(
            f"direct DAT adapter is restricted to A-share equity codes: {instrument}"
        )
    return symbol, market


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_record(record: bytes, instrument: str, record_number: int) -> tuple[QmtDailyBar, float]:
    timestamp = struct.unpack_from("<I", record, 8)[0]
    moment = datetime.fromtimestamp(timestamp, tz=MARKET_TIMEZONE)
    if (moment.hour, moment.minute, moment.second) != (0, 0, 0):
        raise QmtDatError(
            f"{instrument} record {record_number}: timestamp is not Asia/Shanghai midnight"
        )
    raw_open, raw_high, raw_low, raw_close = struct.unpack_from("<4I", record, 12)
    raw_volume = struct.unpack_from("<I", record, 32)[0]
    raw_amount = struct.unpack_from("<Q", record, 40)[0]
    raw_pre_close = struct.unpack_from("<I", record, 60)[0]
    prices = tuple(value / PRICE_SCALE for value in (raw_open, raw_high, raw_low, raw_close))
    if any(value <= 0 for value in prices):
        raise QmtDatError(f"{instrument} record {record_number}: OHLC must be positive")
    open_, high, low, close = prices
    if high < max(open_, close) or low > min(open_, close) or high < low:
        raise QmtDatError(f"{instrument} record {record_number}: inconsistent OHLC")
    volume = raw_volume * STOCK_VOLUME_SCALE
    amount = float(raw_amount)
    if (volume == 0) != (amount == 0):
        raise QmtDatError(
            f"{instrument} record {record_number}: volume and amount zero state differs"
        )
    if volume:
        average_price = amount / volume
        if average_price < low * 0.5 or average_price > high * 2:
            raise QmtDatError(
                f"{instrument} record {record_number}: amount/volume scale is implausible"
            )
    pre_close = raw_pre_close / PRICE_SCALE
    if pre_close <= 0:
        raise QmtDatError(f"{instrument} record {record_number}: pre-close must be positive")
    return (
        QmtDailyBar(
            instrument=instrument,
            trade_date=moment.date().isoformat(),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=float(volume),
            amount=amount,
        ),
        pre_close,
    )


def parse_qmt_daily_dat(
    source: str | Path,
    *,
    instrument: str,
) -> tuple[tuple[QmtDailyBar, ...], DatSourceAudit]:
    """Read one QMT 86400 DAT file without modifying or memory-mapping it."""

    stock = normalize_stocks((instrument,))[0]
    _validate_equity_instrument(stock)
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise QmtDatError(f"QMT daily DAT does not exist: {path}")
    raw = path.read_bytes()
    trailing_bytes = len(raw) % RECORD_SIZE
    if trailing_bytes not in {0, 8}:
        raise QmtDatError(
            f"{stock}: unsupported DAT tail length {trailing_bytes}; expected 0 or 8"
        )
    record_count = len(raw) // RECORD_SIZE
    if record_count == 0:
        raise QmtDatError(f"{stock}: DAT contains no complete daily records")
    bars: list[QmtDailyBar] = []
    previous_date: str | None = None
    for index in range(record_count):
        offset = index * RECORD_SIZE
        bar, _ = _decode_record(raw[offset : offset + RECORD_SIZE], stock, index + 1)
        if previous_date is not None and bar.trade_date <= previous_date:
            raise QmtDatError(
                f"{stock} record {index + 1}: dates are duplicate or non-monotonic"
            )
        bars.append(bar)
        previous_date = bar.trade_date
    return (
        tuple(bars),
        DatSourceAudit(
            instrument=stock,
            relative_path="",
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            records=record_count,
            trailing_bytes=trailing_bytes,
            first_date=bars[0].trade_date,
            last_date=bars[-1].trade_date,
        ),
    )


def _manifest_path(destination: Path) -> Path:
    return destination.with_name(f"{destination.name}.manifest.json")


def verify_qmt_dat_manifest(
    source_csv: str | Path,
    *,
    adjustment: str,
) -> tuple[Path, str]:
    """Verify that an adjacent DAT provenance manifest still matches its CSV."""

    source = Path(source_csv).expanduser().resolve()
    manifest_path = _manifest_path(source)
    if not manifest_path.is_file():
        raise QmtDatError(f"QMT DAT provenance manifest does not exist: {manifest_path}")
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw)
        output = manifest["output"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise QmtDatError("invalid QMT DAT provenance manifest") from exc
    expected = {
        "manifest_version": MANIFEST_VERSION,
        "parser_version": PARSER_VERSION,
        "schema_sha256": SCHEMA_SHA256,
        "adjustment": adjustment,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise QmtDatError(f"QMT DAT provenance {field} mismatch")
    if output.get("filename") != source.name:
        raise QmtDatError("QMT DAT provenance output filename mismatch")
    if output.get("sha256") != _sha256(source):
        raise QmtDatError("QMT DAT provenance output SHA-256 mismatch")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise QmtDatError("QMT DAT provenance has no raw sources")
    for item in sources:
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256"))):
            raise QmtDatError("QMT DAT provenance contains an invalid source hash")
        relative_path = str(item.get("relative_path", ""))
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise QmtDatError("QMT DAT provenance contains an unsafe source path")
    return manifest_path, hashlib.sha256(raw).hexdigest()


def export_qmt_dat_daily_csv(config: DatExportConfig) -> DatExportResult:
    """Export selected unadjusted A-share daily DAT files to the canonical CSV contract."""

    start, end = _parse_iso_window(config)
    root = _resolve_datadir(config.datadir)
    stocks = normalize_stocks(config.stocks)
    destination = Path(config.output_csv).expanduser().resolve()
    manifest_path = _manifest_path(destination)
    existing = [path for path in (destination, manifest_path) if path.exists()]
    if existing and not config.overwrite:
        raise QmtDatError(f"output already exists: {existing[0]}")

    rows: list[QmtDailyBar] = []
    sources: list[DatSourceAudit] = []
    empty: list[str] = []
    for stock in stocks:
        symbol, market = _validate_equity_instrument(stock)
        source = root / market / "86400" / f"{symbol}.DAT"
        bars, audit = parse_qmt_daily_dat(source, instrument=stock)
        selected = [bar for bar in bars if start <= date.fromisoformat(bar.trade_date) <= end]
        if not selected:
            empty.append(stock)
        rows.extend(selected)
        sources.append(
            DatSourceAudit(
                **{
                    **asdict(audit),
                    "relative_path": source.relative_to(root).as_posix(),
                }
            )
        )
    if empty:
        raise QmtDatError(f"no DAT bars in requested window for: {empty[:10]}")
    rows.sort(key=lambda item: (item.trade_date, item.instrument))

    destination.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    temporary_csv = destination.with_name(f".{destination.name}.{token}.tmp")
    temporary_manifest = manifest_path.with_name(f".{manifest_path.name}.{token}.tmp")
    try:
        with temporary_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CANONICAL_HEADER)
            writer.writerows(
                (
                    bar.trade_date,
                    bar.instrument,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume,
                    bar.amount,
                )
                for bar in rows
            )
        dataset = load_qmt_daily_csv(temporary_csv, adjustment="none")
        output_sha256 = _sha256(temporary_csv)
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "parser_version": PARSER_VERSION,
            "schema_sha256": SCHEMA_SHA256,
            "schema": _SCHEMA,
            "source_kind": "qmt_86400_dat_read_only",
            "adjustment": "none",
            "requested_window": {"start": start.isoformat(), "end": end.isoformat()},
            "requested_instruments": list(stocks),
            "sources": [asdict(item) for item in sources],
            "output": {
                "filename": destination.name,
                "sha256": output_sha256,
                "rows": dataset.audit.rows,
                "start_date": dataset.audit.start_date,
                "end_date": dataset.audit.end_date,
            },
        }
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_csv, destination)
        os.replace(temporary_manifest, manifest_path)
    finally:
        temporary_csv.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)

    return DatExportResult(
        parser_version=PARSER_VERSION,
        schema_sha256=SCHEMA_SHA256,
        output_csv=str(destination),
        manifest_path=str(manifest_path),
        adjustment="none",
        requested_instruments=len(stocks),
        exported_instruments=dataset.audit.instruments,
        rows=dataset.audit.rows,
        start_date=dataset.audit.start_date,
        end_date=dataset.audit.end_date,
        output_sha256=output_sha256,
    )
