from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .models import QmtDailyBar, QmtDataAudit, QmtDataError, QmtDataset

ADAPTER_VERSION = "qmt-daily-csv-1.0.0"
REQUIRED_FIELDS = ("trade_date", "instrument", "open", "high", "low", "close", "volume", "amount")
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trade_date": ("trade_date", "date", "datetime", "time", "日期", "交易日期", "时间"),
    "instrument": ("instrument", "stock_code", "code", "symbol", "证券代码", "股票代码", "代码"),
    "open": ("open", "开盘", "开盘价"),
    "high": ("high", "最高", "最高价"),
    "low": ("low", "最低", "最低价"),
    "close": ("close", "收盘", "收盘价"),
    "volume": ("volume", "vol", "成交量"),
    "amount": ("amount", "turnover_value", "成交额", "成交金额"),
}


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise QmtDataError("QMT CSV must be encoded as UTF-8 or GB18030")


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _resolve_columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise QmtDataError("QMT CSV has no header")
    normalized: dict[str, str] = {}
    for original in fieldnames:
        key = _normalize_header(original)
        if key in normalized:
            raise QmtDataError(f"duplicate normalized CSV header: {key}")
        normalized[key] = original
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        matches = [normalized[alias] for alias in aliases if alias in normalized]
        if not matches:
            raise QmtDataError(f"missing required QMT column: {canonical}")
        if len(matches) > 1:
            raise QmtDataError(f"ambiguous columns for {canonical}: {matches}")
        mapping[canonical] = matches[0]
    return mapping


def _parse_date(value: str, *, row_number: int) -> str:
    raw = value.strip()
    try:
        if raw.isdigit() and len(raw) in {8, 14}:
            parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        elif raw.isdigit() and len(raw) in {10, 13}:
            seconds = int(raw) / (1000 if len(raw) == 13 else 1)
            market_timezone = timezone(timedelta(hours=8))
            parsed = datetime.fromtimestamp(seconds, tz=market_timezone).date()
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except (OverflowError, ValueError) as exc:
        raise QmtDataError(f"row {row_number}: invalid trade date {value!r}") from exc
    return parsed.isoformat()


def _parse_number(value: str, field: str, *, row_number: int) -> float:
    try:
        number = float(value.strip())
    except (AttributeError, ValueError) as exc:
        raise QmtDataError(f"row {row_number}: invalid {field}") from exc
    if not math.isfinite(number):
        raise QmtDataError(f"row {row_number}: non-finite {field}")
    return number


def _cell(row: dict[str, str | None], column: str, field: str, *, row_number: int) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise QmtDataError(f"row {row_number}: missing {field}")
    return value


def _validate_bar(bar: QmtDailyBar, *, row_number: int) -> None:
    prices = (bar.open, bar.high, bar.low, bar.close)
    if any(value <= 0 for value in prices):
        raise QmtDataError(f"row {row_number}: OHLC prices must be positive")
    if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
        raise QmtDataError(f"row {row_number}: inconsistent OHLC range")
    if bar.high < bar.low:
        raise QmtDataError(f"row {row_number}: high is below low")
    if bar.volume < 0 or bar.amount < 0:
        raise QmtDataError(f"row {row_number}: volume and amount cannot be negative")


def load_qmt_daily_csv(
    source: str | Path,
    *,
    adjustment: str,
) -> QmtDataset:
    """Load a long-form QMT daily-bar export using conservative validation."""

    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise QmtDataError(f"QMT CSV does not exist: {path}")
    if not adjustment.strip():
        raise QmtDataError("QMT price adjustment must be declared")
    raw = path.read_bytes()
    text, encoding = _decode(raw)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    mapping = _resolve_columns(reader.fieldnames)
    bars: list[QmtDailyBar] = []
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(reader, start=2):
        instrument = _cell(
            row, mapping["instrument"], "instrument", row_number=row_number
        ).strip().upper()
        trade_date = _parse_date(
            _cell(row, mapping["trade_date"], "trade_date", row_number=row_number),
            row_number=row_number,
        )
        key = (instrument, trade_date)
        if key in seen:
            raise QmtDataError(f"row {row_number}: duplicate daily bar {key}")
        seen.add(key)
        bar = QmtDailyBar(
            instrument=instrument,
            trade_date=trade_date,
            open=_parse_number(
                _cell(row, mapping["open"], "open", row_number=row_number),
                "open",
                row_number=row_number,
            ),
            high=_parse_number(
                _cell(row, mapping["high"], "high", row_number=row_number),
                "high",
                row_number=row_number,
            ),
            low=_parse_number(
                _cell(row, mapping["low"], "low", row_number=row_number),
                "low",
                row_number=row_number,
            ),
            close=_parse_number(
                _cell(row, mapping["close"], "close", row_number=row_number),
                "close",
                row_number=row_number,
            ),
            volume=_parse_number(
                _cell(row, mapping["volume"], "volume", row_number=row_number),
                "volume",
                row_number=row_number,
            ),
            amount=_parse_number(
                _cell(row, mapping["amount"], "amount", row_number=row_number),
                "amount",
                row_number=row_number,
            ),
        )
        _validate_bar(bar, row_number=row_number)
        bars.append(bar)
    if not bars:
        raise QmtDataError("QMT CSV contains no data rows")
    bars.sort(key=lambda item: (item.trade_date, item.instrument))
    instruments = {bar.instrument for bar in bars}
    dates = [date.fromisoformat(bar.trade_date) for bar in bars]
    zero_volume = sum(bar.volume == 0 or bar.amount == 0 for bar in bars)
    warnings = (
        "Input universe membership is treated as user-supplied and may contain survivorship bias.",
    )
    if zero_volume:
        warnings += (
            "Zero-volume or zero-amount bars are retained but may make a test window ineligible.",
        )
    return QmtDataset(
        bars=tuple(bars),
        audit=QmtDataAudit(
            adapter_version=ADAPTER_VERSION,
            source_path=str(path),
            source_sha256=hashlib.sha256(raw).hexdigest(),
            encoding=encoding,
            adjustment=adjustment.strip(),
            column_mapping=mapping,
            rows=len(bars),
            instruments=len(instruments),
            start_date=min(dates).isoformat(),
            end_date=max(dates).isoformat(),
            zero_volume_bars=zero_volume,
            warnings=warnings,
        ),
    )
