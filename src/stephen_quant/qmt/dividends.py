from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import QmtDailyBar, QmtDataError

DIVIDEND_PARSER_VERSION = "qmt-dividend-leveldb-1.0.0"
MARKET_TIMEZONE = timezone(timedelta(hours=8))
VALUE_SIZE = 96
_VALUE_STRUCT = struct.Struct("<qq8dIIII")
_SCHEMA = {
    "key": "MARKET|SYMBOL|4000|timestamp_ms",
    "value_size_min": VALUE_SIZE,
    "byte_order": "little",
    "timestamp_raw": {"offset": 8, "type": "int64", "unit": "unix_ms"},
    "interest": {"offset": 16, "type": "float64"},
    "stock_bonus": {"offset": 24, "type": "float64"},
    "stock_gift": {"offset": 32, "type": "float64"},
    "allot_num": {"offset": 40, "type": "float64"},
    "allot_price": {"offset": 48, "type": "float64"},
    "gugai": {"offset": 56, "type": "float64"},
    "unknown64_raw": {"offset": 64, "type": "float64"},
    "dr": {"offset": 72, "type": "float64"},
    "record_date": {"offset": 80, "type": "uint32", "format": "YYYYMMDD"},
    "ex_dividend_date": {"offset": 88, "type": "uint32", "format": "YYYYMMDD"},
}
DIVIDEND_SCHEMA_SHA256 = hashlib.sha256(
    json.dumps(_SCHEMA, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()


class QmtDividendError(QmtDataError):
    """Raised when QMT corporate actions cannot be read or validated safely."""


@dataclass(frozen=True)
class QmtDividendRecord:
    instrument: str
    ex_dividend_date: str
    record_date: str | None
    interest: float
    stock_bonus: float
    stock_gift: float
    allot_num: float
    allot_price: float
    gugai: float
    unknown64_raw: float
    dr: float
    timestamp_raw: int


@dataclass(frozen=True)
class DividendSourceFile:
    filename: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class QmtDividendAudit:
    parser_version: str
    schema_sha256: str
    snapshot_sha256: str
    source_files: tuple[DividendSourceFile, ...]
    requested_instruments: int
    selected_records: int
    first_ex_dividend_date: str | None
    last_ex_dividend_date: str | None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["source_files"] = [asdict(item) for item in self.source_files]
        return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_snapshot(root: Path) -> tuple[tuple[DividendSourceFile, ...], str]:
    if not root.is_dir():
        raise QmtDividendError(f"QMT DividData directory does not exist: {root}")
    paths = sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file()
            and (
                path.name == "CURRENT"
                or path.name.startswith("MANIFEST-")
                or path.suffix.lower() in {".ldb", ".log"}
            )
        ),
        key=lambda path: path.name,
    )
    if not paths or not any(path.suffix.lower() == ".ldb" for path in paths):
        raise QmtDividendError("QMT DividData has no readable LevelDB tables")
    files = tuple(
        DividendSourceFile(filename=path.name, sha256=_sha256(path), bytes=path.stat().st_size)
        for path in paths
    )
    snapshot = hashlib.sha256(
        json.dumps(
            [asdict(item) for item in files], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return files, snapshot


def _yyyymmdd(raw: int) -> str | None:
    if raw == 0:
        return None
    text = str(raw)
    if len(text) != 8:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])).isoformat()
    except ValueError:
        return None


def parse_qmt_dividend_value(
    key: bytes,
    value: bytes,
) -> QmtDividendRecord | None:
    """Decode one observed QMT corporate-action key/value pair."""

    try:
        key_text = key.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise QmtDividendError("QMT dividend key is not UTF-8") from exc
    parts = key_text.split("|")
    if len(parts) != 4:
        raise QmtDividendError(f"invalid QMT dividend key: {key_text!r}")
    market, symbol, event_type, key_timestamp = parts
    if event_type != "4000":
        return None
    try:
        timestamp_from_key = int(key_timestamp)
    except ValueError as exc:
        raise QmtDividendError(f"invalid QMT dividend timestamp: {key_timestamp!r}") from exc
    if timestamp_from_key in {0, 999_999_999_999} or not value:
        return None
    if len(value) < VALUE_SIZE:
        raise QmtDividendError(
            f"QMT dividend value is too short: expected {VALUE_SIZE}, got {len(value)}"
        )
    unpacked = _VALUE_STRUCT.unpack_from(value)
    timestamp_raw = unpacked[1]
    if timestamp_raw != timestamp_from_key or timestamp_raw <= 0:
        raise QmtDividendError("QMT dividend key/value timestamps disagree")
    numeric = unpacked[2:10]
    if not all(math.isfinite(item) for item in numeric):
        raise QmtDividendError("QMT dividend value contains a non-finite field")
    interest, stock_bonus, stock_gift, allot_num, allot_price, gugai, unknown, dr = numeric
    if min(interest, stock_bonus, stock_gift, allot_num, allot_price) < 0:
        raise QmtDividendError("QMT dividend value contains a negative distribution field")
    if dr <= 0 or dr > 100:
        raise QmtDividendError(f"implausible QMT dividend adjustment factor: {dr}")
    record_date = _yyyymmdd(unpacked[10])
    ex_dividend_date = _yyyymmdd(unpacked[12])
    if ex_dividend_date is None:
        ex_dividend_date = datetime.fromtimestamp(
            timestamp_raw / 1000, tz=MARKET_TIMEZONE
        ).date().isoformat()
    return QmtDividendRecord(
        instrument=f"{symbol}.{market}",
        ex_dividend_date=ex_dividend_date,
        record_date=record_date,
        interest=interest,
        stock_bonus=stock_bonus,
        stock_gift=stock_gift,
        allot_num=allot_num,
        allot_price=allot_price,
        gugai=gugai,
        unknown64_raw=unknown,
        dr=dr,
        timestamp_raw=timestamp_raw,
    )


def _import_rleveldb() -> tuple[Any, Any]:
    try:
        from rleveldb import KeyState, RawLevelDb
    except ImportError as exc:
        raise QmtDividendError(
            "reading DividData requires the optional qmt-dat dependency; "
            "install with: pip install -e '.[qmt-dat]'"
        ) from exc
    return RawLevelDb, KeyState


def load_qmt_dividend_records(
    divid_data: str | Path,
    *,
    instruments: Iterable[str],
) -> tuple[dict[str, tuple[QmtDividendRecord, ...]], QmtDividendAudit]:
    """Read selected corporate actions without modifying or locking the QMT database."""

    requested = tuple(dict.fromkeys(str(item).strip().upper() for item in instruments))
    if not requested:
        raise QmtDividendError("at least one instrument is required for dividend loading")
    prefixes: dict[bytes, str] = {}
    for instrument in requested:
        symbol, separator, market = instrument.partition(".")
        if not separator or not symbol or not market:
            raise QmtDividendError(f"invalid QMT instrument: {instrument!r}")
        prefixes[f"{market}|{symbol}|".encode()] = instrument

    root = Path(divid_data).expanduser().resolve()
    before_files, before_snapshot = _source_snapshot(root)
    RawLevelDb, KeyState = _import_rleveldb()
    latest: dict[bytes, Any] = {}
    database = RawLevelDb(str(root))
    try:
        for raw_record in database.iterate_records_raw():
            if not raw_record.user_key.startswith(tuple(prefixes)):
                continue
            previous = latest.get(raw_record.user_key)
            if previous is None or raw_record.seq > previous.seq:
                latest[raw_record.user_key] = raw_record
    except Exception as exc:
        raise QmtDividendError(f"cannot read QMT DividData: {exc}") from exc
    finally:
        database.close()
    after_files, after_snapshot = _source_snapshot(root)
    if before_snapshot != after_snapshot or before_files != after_files:
        raise QmtDividendError("QMT DividData changed during the read; retry from a stable copy")

    grouped: dict[str, list[QmtDividendRecord]] = {item: [] for item in requested}
    for raw_record in latest.values():
        if raw_record.state != KeyState.Live:
            continue
        parsed = parse_qmt_dividend_value(raw_record.user_key, raw_record.value)
        if parsed is not None and parsed.instrument in grouped:
            grouped[parsed.instrument].append(parsed)
    result = {
        instrument: tuple(
            sorted(records, key=lambda item: (item.ex_dividend_date, item.timestamp_raw))
        )
        for instrument, records in grouped.items()
    }
    selected = [record for records in result.values() for record in records]
    dates = sorted(record.ex_dividend_date for record in selected)
    return result, QmtDividendAudit(
        parser_version=DIVIDEND_PARSER_VERSION,
        schema_sha256=DIVIDEND_SCHEMA_SHA256,
        snapshot_sha256=before_snapshot,
        source_files=before_files,
        requested_instruments=len(requested),
        selected_records=len(selected),
        first_ex_dividend_date=dates[0] if dates else None,
        last_ex_dividend_date=dates[-1] if dates else None,
    )


def apply_back_ratio_adjustment(
    bars: Iterable[QmtDailyBar],
    actions: dict[str, tuple[QmtDividendRecord, ...]],
) -> tuple[QmtDailyBar, ...]:
    """Apply QMT `dr` only from each ex-dividend date onward (point-in-time safe)."""

    factors: dict[str, float] = {}
    positions: dict[str, int] = {}
    output: list[QmtDailyBar] = []
    for bar in sorted(bars, key=lambda item: (item.instrument, item.trade_date)):
        instrument_actions = actions.get(bar.instrument, ())
        position = positions.get(bar.instrument, 0)
        factor = factors.get(bar.instrument, 1.0)
        while (
            position < len(instrument_actions)
            and instrument_actions[position].ex_dividend_date <= bar.trade_date
        ):
            factor *= instrument_actions[position].dr
            position += 1
        if not math.isfinite(factor) or factor <= 0:
            raise QmtDividendError(f"invalid cumulative adjustment for {bar.instrument}")
        positions[bar.instrument] = position
        factors[bar.instrument] = factor
        output.append(
            QmtDailyBar(
                instrument=bar.instrument,
                trade_date=bar.trade_date,
                open=bar.open * factor,
                high=bar.high * factor,
                low=bar.low * factor,
                close=bar.close * factor,
                volume=bar.volume,
                amount=bar.amount,
            )
        )
    return tuple(sorted(output, key=lambda item: (item.trade_date, item.instrument)))
