from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .csv_adapter import _decode, _normalize_header, _parse_date, _parse_number, _validate_bar
from .models import QmtDailyBar, QmtDataAudit, QmtDataError, QmtDataset

QD_ADAPTER_VERSION = "qd-daily-directory-1.3.0"
QD_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "trade_date": ("日期", "交易日期", "trade_date", "date"),
    "instrument": ("代码", "股票代码", "证券代码", "ts_code", "instrument"),
    "open": ("开盘价", "开盘", "open"),
    "high": ("最高价", "最高", "high"),
    "low": ("最低价", "最低", "low"),
    "close": ("收盘价", "收盘", "close"),
    "volume": ("成交量(手)", "成交量（手）", "vol"),
    "amount": ("成交额(千元)", "成交额（千元）", "amount"),
    "adjustment_factor": ("复权因子", "adj_factor", "adjustment_factor"),
}
QD_OPTIONAL_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("名称", "证券名称", "股票名称", "name"),
    "previous_close": ("昨日收盘价", "昨收", "pre_close", "previous_close"),
}
VOLUME_LOT_TO_SHARE = 100.0
AMOUNT_THOUSAND_CNY_TO_CNY = 1000.0
_DAILY_FILE = re.compile(r"^(\d{8})\.csv$", re.IGNORECASE)


def _iso_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QmtDataError(f"{field} must be an ISO date") from exc


def select_qd_daily_files(
    source: str | Path,
    *,
    start_date: str,
    end_date: str,
    include_next_after_end: bool = False,
) -> tuple[Path, ...]:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise QmtDataError(f"QD daily source is not a directory: {root}")
    start, end = _iso_date(start_date, "start_date"), _iso_date(end_date, "end_date")
    if start > end:
        raise QmtDataError("start_date must not be after end_date")

    dated: list[tuple[date, Path]] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        match = _DAILY_FILE.fullmatch(path.name)
        if match is None:
            continue
        try:
            day = date(int(match.group(1)[:4]), int(match.group(1)[4:6]), int(match.group(1)[6:]))
        except ValueError as exc:
            raise QmtDataError(f"invalid QD daily filename date: {path.name}") from exc
        dated.append((day, path))
    dated.sort()
    selected = [(day, path) for day, path in dated if start <= day <= end]
    if include_next_after_end:
        next_file = next(((day, path) for day, path in dated if day > end), None)
        if next_file is None:
            raise QmtDataError(f"QD daily source has no session after {end.isoformat()}")
        selected.append(next_file)
    if not selected:
        raise QmtDataError(
            f"QD daily source has no files from {start.isoformat()} to {end.isoformat()}"
        )
    return tuple(path for _, path in selected)


def _resolve_columns(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise QmtDataError("QD daily CSV has no header")
    normalized: dict[str, str] = {}
    for original in fieldnames:
        key = _normalize_header(original)
        if key in normalized:
            raise QmtDataError(f"duplicate normalized QD CSV header: {key}")
        normalized[key] = original
    mapping: dict[str, str] = {}
    for canonical, aliases in QD_COLUMN_ALIASES.items():
        matches = [normalized[_normalize_header(alias)] for alias in aliases if _normalize_header(alias) in normalized]
        if not matches:
            raise QmtDataError(f"missing required QD column: {canonical}")
        if len(matches) > 1:
            raise QmtDataError(f"ambiguous QD columns for {canonical}: {matches}")
        mapping[canonical] = matches[0]
    for canonical, aliases in QD_OPTIONAL_COLUMN_ALIASES.items():
        matches = [
            normalized[_normalize_header(alias)]
            for alias in aliases
            if _normalize_header(alias) in normalized
        ]
        if len(matches) > 1:
            raise QmtDataError(f"ambiguous QD columns for {canonical}: {matches}")
        if matches:
            mapping[canonical] = matches[0]
    return mapping


def _price_limit_rate(instrument: str, name: str, trade_date: str) -> Decimal | None:
    normalized_name = "".join(name.strip().upper().split())
    code, _, exchange = instrument.partition(".")
    if normalized_name.startswith(("N", "C")):
        return None
    if exchange == "BJ" or code.startswith(("4", "8")):
        return Decimal("0.30")
    if code.startswith(("300", "301", "688", "689")):
        return Decimal("0.20")
    main_board = (exchange == "SH" and code.startswith(("600", "601", "603", "605"))) or (
        exchange == "SZ" and code.startswith(("000", "001", "002", "003"))
    )
    if not main_board:
        raise QmtDataError(f"unsupported A-share price-limit board: {instrument}")
    if "ST" in normalized_name and trade_date < "2026-07-06":
        return Decimal("0.05")
    return Decimal("0.10")


def _open_tradability(
    instrument: str,
    name: str,
    trade_date: str,
    raw_open: float,
    previous_close: float,
) -> tuple[bool, bool, str]:
    if previous_close <= 0:
        raise QmtDataError("previous_close must be positive")
    tick = Decimal("0.01")
    prior = Decimal(str(previous_close))
    rate = _price_limit_rate(instrument, name, trade_date)
    if rate is None:
        return True, True, "no_price_limit"
    upper = (prior * (Decimal(1) + rate)).quantize(tick, rounding=ROUND_HALF_UP)
    lower = (prior * (Decimal(1) - rate)).quantize(tick, rounding=ROUND_HALF_UP)
    opening = Decimal(str(raw_open)).quantize(tick, rounding=ROUND_HALF_UP)
    if opening > upper or opening < lower:
        return True, True, "no_price_limit_inferred"
    if opening >= upper:
        return False, True, "open_at_upper_limit"
    if opening <= lower:
        return True, False, "open_at_lower_limit"
    return True, True, "normal"


def _required_cell(
    row: dict[str, str | None], column: str, field: str, *, row_number: int
) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise QmtDataError(f"row {row_number}: missing {field}")
    return value


def load_qd_daily_directory(
    source: str | Path,
    *,
    start_date: str,
    end_date: str,
    instruments: tuple[str, ...],
    adjustment: str = "none",
    include_next_after_end: bool = False,
) -> QmtDataset:
    """Load date-partitioned QD A-share daily files with explicit unit conversion."""

    declared_adjustment = adjustment.strip().lower()
    if declared_adjustment in {"raw", "unadjusted"}:
        declared_adjustment = "none"
    if declared_adjustment not in {"none", "back_ratio"}:
        raise QmtDataError("QD daily directory supports only none or back_ratio adjustment")
    wanted = {item.strip().upper() for item in instruments if item.strip()}
    if not wanted:
        raise QmtDataError("QD daily directory requires an explicit fixed instrument universe")
    root = Path(source).expanduser().resolve()
    files = select_qd_daily_files(
        root,
        start_date=start_date,
        end_date=end_date,
        include_next_after_end=include_next_after_end,
    )
    manifest = build_selected_files_snapshot_manifest(root, files)
    bars: list[QmtDailyBar] = []
    seen: set[tuple[str, str]] = set()
    encodings: set[str] = set()
    mapping_reference: dict[str, str] | None = None

    for path in files:
        text, encoding = _decode(path.read_bytes())
        encodings.add(encoding)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        mapping = _resolve_columns(reader.fieldnames)
        if mapping_reference is None:
            mapping_reference = mapping
        elif mapping != mapping_reference:
            raise QmtDataError(f"QD daily schema drift detected in {path.name}")
        expected_date = date(
            int(path.stem[:4]), int(path.stem[4:6]), int(path.stem[6:8])
        ).isoformat()
        for row_number, row in enumerate(reader, start=2):
            instrument = _required_cell(
                row, mapping["instrument"], "instrument", row_number=row_number
            ).strip().upper()
            if instrument not in wanted:
                continue
            trade_date = _parse_date(
                _required_cell(
                    row, mapping["trade_date"], "trade_date", row_number=row_number
                ),
                row_number=row_number,
            )
            if trade_date != expected_date:
                raise QmtDataError(
                    f"{path.name} row {row_number}: row date {trade_date} does not match filename"
                )
            key = (instrument, trade_date)
            if key in seen:
                raise QmtDataError(f"{path.name} row {row_number}: duplicate daily bar {key}")
            seen.add(key)
            adjustment_factor = _parse_number(
                _required_cell(
                    row,
                    mapping["adjustment_factor"],
                    "adjustment_factor",
                    row_number=row_number,
                ),
                "adjustment_factor",
                row_number=row_number,
            )
            if adjustment_factor <= 0:
                raise QmtDataError(f"row {row_number}: adjustment_factor must be positive")
            price_scale = adjustment_factor if declared_adjustment == "back_ratio" else 1.0
            raw_open = _parse_number(
                _required_cell(row, mapping["open"], "open", row_number=row_number),
                "open",
                row_number=row_number,
            )
            can_buy_open, can_sell_open, tradability_reason = True, True, "unavailable"
            if "name" in mapping and "previous_close" in mapping:
                name = _required_cell(
                    row, mapping["name"], "name", row_number=row_number
                )
                previous_close = _parse_number(
                    _required_cell(
                        row,
                        mapping["previous_close"],
                        "previous_close",
                        row_number=row_number,
                    ),
                    "previous_close",
                    row_number=row_number,
                )
                can_buy_open, can_sell_open, tradability_reason = _open_tradability(
                    instrument, name, trade_date, raw_open, previous_close
                )
            bar = QmtDailyBar(
                instrument=instrument,
                trade_date=trade_date,
                open=raw_open * price_scale,
                high=_parse_number(
                    _required_cell(row, mapping["high"], "high", row_number=row_number),
                    "high",
                    row_number=row_number,
                )
                * price_scale,
                low=_parse_number(
                    _required_cell(row, mapping["low"], "low", row_number=row_number),
                    "low",
                    row_number=row_number,
                )
                * price_scale,
                close=_parse_number(
                    _required_cell(row, mapping["close"], "close", row_number=row_number),
                    "close",
                    row_number=row_number,
                )
                * price_scale,
                volume=_parse_number(
                    _required_cell(row, mapping["volume"], "volume", row_number=row_number),
                    "volume",
                    row_number=row_number,
                )
                * VOLUME_LOT_TO_SHARE,
                amount=_parse_number(
                    _required_cell(row, mapping["amount"], "amount", row_number=row_number),
                    "amount",
                    row_number=row_number,
                )
                * AMOUNT_THOUSAND_CNY_TO_CNY,
                can_buy_open=can_buy_open,
                can_sell_open=can_sell_open,
                tradability_reason=tradability_reason,
            )
            _validate_bar(bar, row_number=row_number)
            bars.append(bar)
    if not bars:
        raise QmtDataError("QD daily selection contains no bars for the requested universe")
    found = {bar.instrument for bar in bars}
    missing = sorted(wanted - found)
    if missing:
        raise QmtDataError(f"QD daily source is missing requested instruments: {missing}")
    bars.sort(key=lambda item: (item.trade_date, item.instrument))
    dates = [date.fromisoformat(bar.trade_date) for bar in bars]
    zero_volume = sum(bar.volume == 0 or bar.amount == 0 for bar in bars)
    warnings = (
        "The fixed universe is user-supplied and may contain survivorship bias.",
        "QD daily partitions omit suspended sessions; strict-panel evaluation will reject gaps.",
        "Industry, valuation, adjusted-pre-close, and vendor technical factors are ignored.",
    )
    if mapping_reference is not None and not {
        "name",
        "previous_close",
    } <= set(mapping_reference):
        warnings += (
            "Open-limit tradability was unavailable because name or previous close was absent.",
        )
    if zero_volume:
        warnings += ("Zero-volume or zero-amount bars are retained.",)
    return QmtDataset(
        bars=tuple(bars),
        audit=QmtDataAudit(
            adapter_version=QD_ADAPTER_VERSION,
            source_path=str(root),
            source_sha256=manifest.snapshot_sha256,
            encoding=",".join(sorted(encodings)),
            adjustment=declared_adjustment,
            column_mapping=mapping_reference or {},
            rows=len(bars),
            instruments=len(found),
            start_date=min(dates).isoformat(),
            end_date=max(dates).isoformat(),
            zero_volume_bars=zero_volume,
            warnings=warnings,
            source_files=len(files),
            unit_conversions={
                "volume_lot_to_share": VOLUME_LOT_TO_SHARE,
                "amount_thousand_cny_to_cny": AMOUNT_THOUSAND_CNY_TO_CNY,
            },
            open_upper_limit_bars=sum(
                bar.tradability_reason == "open_at_upper_limit" for bar in bars
            ),
            open_lower_limit_bars=sum(
                bar.tradability_reason == "open_at_lower_limit" for bar in bars
            ),
            tradability_unavailable_bars=sum(
                bar.tradability_reason == "unavailable" for bar in bars
            ),
            no_price_limit_bars=sum(
                bar.tradability_reason.startswith("no_price_limit") for bar in bars
            ),
        ),
    )
