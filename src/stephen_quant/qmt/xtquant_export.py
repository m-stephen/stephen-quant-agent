from __future__ import annotations

import csv
import importlib
import math
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from .csv_adapter import load_qmt_daily_csv
from .models import QmtDataError

EXPORTER_VERSION = "xtquant-local-daily-export-1.0.0"
FIELDS = ("time", "open", "high", "low", "close", "volume", "amount")
CANONICAL_HEADER = ("trade_date", "instrument", "open", "high", "low", "close", "volume", "amount")
VALID_ADJUSTMENTS = {"none", "front", "back", "front_ratio", "back_ratio"}
_STOCK_PATTERN = re.compile(r"^[A-Z0-9]{1,12}\.[A-Z]{2,6}$")
_DLL_HANDLES: list[Any] = []


@dataclass(frozen=True)
class XtquantExportConfig:
    qmt_home: str
    output_csv: str
    start_time: str
    end_time: str
    adjustment: str
    stocks: tuple[str, ...] = ()
    sector: str | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class XtquantExportResult:
    exporter_version: str
    output_csv: str
    source_kind: str
    adjustment: str
    requested_instruments: int
    exported_instruments: int
    rows: int
    skipped_unavailable_bars: int
    start_date: str
    end_date: str
    source_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class XtquantExportError(QmtDataError):
    """Raised when the official QMT API cannot produce a safe canonical export."""


def find_xtquant_site_packages(qmt_home: str | Path) -> Path:
    home = Path(qmt_home).expanduser().resolve()
    if home.name.lower() == "datadir":
        home = home.parent
    candidates = (
        home / "bin.x64" / "Lib" / "site-packages",
        home / "Lib" / "site-packages",
    )
    for candidate in candidates:
        if (candidate / "xtquant" / "xtdata.py").is_file():
            return candidate
    raise XtquantExportError(f"xtquant was not found under QMT installation: {home}")


def load_xtdata(qmt_home: str | Path) -> ModuleType:
    home = Path(qmt_home).expanduser().resolve()
    if home.name.lower() == "datadir":
        home = home.parent
    site_packages = find_xtquant_site_packages(home)
    bin_dir = home / "bin.x64"
    if hasattr(os, "add_dll_directory") and bin_dir.is_dir():
        _DLL_HANDLES.append(os.add_dll_directory(str(bin_dir)))
    site_text = str(site_packages)
    if site_text not in sys.path:
        sys.path.insert(0, site_text)
    try:
        return importlib.import_module("xtquant.xtdata")
    except (ImportError, OSError) as exc:
        raise XtquantExportError(
            "xtquant exists but cannot load in this Python runtime; use a QMT-supported 64-bit Python version"
        ) from exc


def read_stock_file(path: str | Path) -> tuple[str, ...]:
    stock_path = Path(path).expanduser().resolve()
    if not stock_path.is_file():
        raise XtquantExportError(f"stock-list file does not exist: {stock_path}")
    stocks = [
        line.split("#", 1)[0].strip()
        for line in stock_path.read_text(encoding="utf-8-sig").splitlines()
    ]
    return normalize_stocks(stock for stock in stocks if stock)


def normalize_stocks(stocks: Any) -> tuple[str, ...]:
    if isinstance(stocks, str):
        raise XtquantExportError("stocks must be a sequence, not one comma-separated string")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in stocks:
        stock = str(raw).strip().upper()
        if not _STOCK_PATTERN.fullmatch(stock):
            raise XtquantExportError(f"invalid QMT instrument code: {stock!r}")
        if stock not in seen:
            normalized.append(stock)
            seen.add(stock)
    if not normalized:
        raise XtquantExportError("at least one QMT instrument is required")
    return tuple(normalized)


def _validate_config(config: XtquantExportConfig) -> None:
    try:
        start = date.fromisoformat(config.start_time)
        end = date.fromisoformat(config.end_time)
    except ValueError as exc:
        raise XtquantExportError("start_time and end_time must be ISO dates") from exc
    if start > end:
        raise XtquantExportError("start_time must not be after end_time")
    if config.adjustment not in VALID_ADJUSTMENTS:
        raise XtquantExportError(
            f"adjustment must be one of {sorted(VALID_ADJUSTMENTS)}"
        )
    if bool(config.stocks) == bool(config.sector):
        raise XtquantExportError("provide exactly one of stocks or sector")


def _market_date(value: Any) -> str:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, (str, bytes)):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = math.nan
        if math.isfinite(numeric):
            seconds = numeric / 1000 if abs(numeric) >= 100_000_000_000 else numeric
            market_tz = timezone(timedelta(hours=8))
            return datetime.fromtimestamp(seconds, tz=market_tz).date().isoformat()
    text = str(value).strip()
    if text.isdigit() and len(text) in {8, 14}:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8])).isoformat()
    if text.isdigit() and len(text) in {10, 13}:
        seconds = int(text) / (1000 if len(text) == 13 else 1)
        market_tz = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(seconds, tz=market_tz).date().isoformat()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise XtquantExportError(f"unsupported QMT time value: {value!r}") from exc


def _number(value: Any, field: str, stock: str, trade_date: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise XtquantExportError(
            f"invalid {field} for {stock} on {trade_date}"
        ) from exc
    if not math.isfinite(number):
        raise XtquantExportError(f"non-finite {field} for {stock} on {trade_date}")
    return number


def _frame_rows(frame: Any, stock: str) -> tuple[list[tuple[object, ...]], int]:
    try:
        records = frame.to_dict(orient="records")
        indexes = list(frame.index)
    except (AttributeError, TypeError) as exc:
        raise XtquantExportError(f"unexpected xtquant frame for {stock}") from exc
    rows: list[tuple[object, ...]] = []
    skipped = 0
    for index, record in zip(indexes, records, strict=True):
        trade_date = _market_date(record.get("time", index))
        raw_prices = [record.get(field) for field in ("open", "high", "low", "close")]
        raw_volume = record.get("volume")
        raw_amount = record.get("amount")
        numeric: list[float] = []
        for value in (*raw_prices, raw_volume, raw_amount):
            try:
                numeric.append(float(value))
            except (TypeError, ValueError):
                numeric.append(math.nan)
        unavailable = all(not math.isfinite(value) or value == 0 for value in numeric[:4])
        no_trade = all(
            not math.isfinite(value) or value == 0 for value in numeric[4:]
        )
        if unavailable and no_trade:
            skipped += 1
            continue
        values = [
            _number(record.get(field), field, stock, trade_date)
            for field in ("open", "high", "low", "close", "volume", "amount")
        ]
        rows.append((trade_date, stock, *values))
    return rows, skipped


def _resolve_stocks(config: XtquantExportConfig, xtdata: Any) -> tuple[str, ...]:
    if config.stocks:
        return normalize_stocks(config.stocks)
    try:
        sector_stocks = xtdata.get_stock_list_in_sector(config.sector)
    except Exception as exc:
        raise XtquantExportError(
            "cannot read the QMT sector; log in and start the QMT quote/Python service"
        ) from exc
    return normalize_stocks(sector_stocks or ())


def export_qmt_daily_csv(
    config: XtquantExportConfig,
    *,
    xtdata_module: Any | None = None,
) -> XtquantExportResult:
    """Export local-only QMT daily bars through the supported xtquant API."""

    _validate_config(config)
    destination = Path(config.output_csv).expanduser().resolve()
    if destination.exists() and not config.overwrite:
        raise XtquantExportError(f"output already exists: {destination}")
    xtdata = xtdata_module if xtdata_module is not None else load_xtdata(config.qmt_home)
    stocks = _resolve_stocks(config, xtdata)
    try:
        frames = xtdata.get_local_data(
            field_list=list(FIELDS),
            stock_list=list(stocks),
            period="1d",
            start_time=config.start_time.replace("-", ""),
            end_time=config.end_time.replace("-", ""),
            count=-1,
            dividend_type=config.adjustment,
            fill_data=False,
        )
    except Exception as exc:
        raise XtquantExportError(
            "cannot connect to the QMT quote service; log in to QMT and start its quote/Python service"
        ) from exc
    if not isinstance(frames, dict):
        raise XtquantExportError(
            "QMT returned no local data; confirm the quote service and downloaded daily history"
        )
    missing = [stock for stock in stocks if stock not in frames or frames[stock] is None]
    if missing:
        raise XtquantExportError(f"QMT returned no frame for instruments: {missing[:10]}")

    rows: list[tuple[object, ...]] = []
    skipped = 0
    empty: list[str] = []
    for stock in stocks:
        stock_rows, stock_skipped = _frame_rows(frames[stock], stock)
        if not stock_rows:
            empty.append(stock)
        rows.extend(stock_rows)
        skipped += stock_skipped
    if empty:
        raise XtquantExportError(f"QMT returned no usable bars for instruments: {empty[:10]}")
    rows.sort(key=lambda row: (str(row[0]), str(row[1])))

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(CANONICAL_HEADER)
            writer.writerows(rows)
        dataset = load_qmt_daily_csv(temporary, adjustment=config.adjustment)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return XtquantExportResult(
        exporter_version=EXPORTER_VERSION,
        output_csv=str(destination),
        source_kind="qmt_xtquant_local_only",
        adjustment=config.adjustment,
        requested_instruments=len(stocks),
        exported_instruments=dataset.audit.instruments,
        rows=dataset.audit.rows,
        skipped_unavailable_bars=skipped,
        start_date=dataset.audit.start_date,
        end_date=dataset.audit.end_date,
        source_sha256=dataset.audit.source_sha256,
    )
