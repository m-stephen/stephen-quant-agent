from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from stephen_quant.integrity.snapshot import build_selected_files_snapshot_manifest

from .csv_adapter import _decode, _parse_date, _parse_number
from .models import QmtDataError

QD_ALTERNATIVE_ADAPTER_VERSION = "qd-alternative-daily-1.0.0"
SourceKind = Literal[
    "fund_flow", "auction", "margin", "industry", "chip", "limit_event"
]


@dataclass(frozen=True)
class AlternativeField:
    column: str
    scale: float = 1.0


COMMON_COLUMNS = {"trade_date": "日期", "instrument": "代码", "name": "名称"}
SOURCE_FIELDS: dict[SourceKind, dict[str, AlternativeField]] = {
    "fund_flow": {
        "small_buy_volume": AlternativeField("小单买入量(手)", 100.0),
        "small_buy_amount": AlternativeField("小单买入金额(万元)", 10_000.0),
        "small_sell_volume": AlternativeField("小单卖出量(手)", 100.0),
        "small_sell_amount": AlternativeField("小单卖出金额(万元)", 10_000.0),
        "medium_buy_volume": AlternativeField("中单买入量(手)", 100.0),
        "medium_buy_amount": AlternativeField("中单买入金额(万元)", 10_000.0),
        "medium_sell_volume": AlternativeField("中单卖出量(手)", 100.0),
        "medium_sell_amount": AlternativeField("中单卖出金额(万元)", 10_000.0),
        "large_buy_volume": AlternativeField("大单买入量(手)", 100.0),
        "large_buy_amount": AlternativeField("大单买入金额(万元)", 10_000.0),
        "large_sell_volume": AlternativeField("大单卖出量(手)", 100.0),
        "large_sell_amount": AlternativeField("大单卖出金额(万元)", 10_000.0),
        "extra_large_buy_volume": AlternativeField("特大单买入量(手)", 100.0),
        "extra_large_buy_amount": AlternativeField("特大单买入金额(万元)", 10_000.0),
        "extra_large_sell_volume": AlternativeField("特大单卖出量(手)", 100.0),
        "extra_large_sell_amount": AlternativeField("特大单卖出金额(万元)", 10_000.0),
        "net_inflow_volume": AlternativeField("净流入量(手)", 100.0),
        "net_inflow_amount": AlternativeField("净流入额(万元)", 10_000.0),
    },
    "auction": {
        "auction_return": AlternativeField("集合竞价涨幅%", 0.01),
        "auction_price": AlternativeField("集合竞价成交价"),
        "auction_volume": AlternativeField("集合竞价成交量(股)"),
        "auction_amount": AlternativeField("集合竞价成交额(元)"),
        "auction_turnover_1": AlternativeField("集合竞价换手率1", 0.01),
        "auction_turnover_2": AlternativeField("集合竞价换手率2", 0.01),
        "auction_volume_ratio_1": AlternativeField("集合竞价量比1"),
        "auction_volume_ratio_2": AlternativeField("集合竞价量比2"),
        "auction_volume_ratio_3": AlternativeField("集合竞价量比3"),
    },
    "margin": {
        "margin_total_balance": AlternativeField("两融余额(元)"),
        "margin_financing_balance": AlternativeField("融资余额(元)"),
        "margin_financing_buy": AlternativeField("融资买入额(元)"),
        "margin_financing_repay": AlternativeField("融资偿还额(元)"),
        "securities_lending_balance": AlternativeField("融券余额(元)"),
        "securities_lending_quantity": AlternativeField("融券余量(股)"),
        "securities_lending_sell": AlternativeField("融券卖出量(股)"),
        "securities_lending_repay": AlternativeField("融券偿还量(股)"),
    },
    "industry": {
        "industry_open": AlternativeField("开盘点位"),
        "industry_high": AlternativeField("最高点位"),
        "industry_low": AlternativeField("最低点位"),
        "industry_close": AlternativeField("收盘点位"),
        "industry_change": AlternativeField("涨跌点位"),
        "industry_return": AlternativeField("涨幅%", 0.01),
        "industry_volume": AlternativeField("成交量(万股)", 10_000.0),
        "industry_amount": AlternativeField("成交额(万元)", 10_000.0),
        "industry_pe": AlternativeField("市盈率"),
        "industry_pb": AlternativeField("市净率"),
        "industry_float_market_cap": AlternativeField("流通市值(万元)", 10_000.0),
        "industry_total_market_cap": AlternativeField("总市值(万元)", 10_000.0),
    },
    "chip": {
        "chip_cost_5": AlternativeField("5分位成本"),
        "chip_cost_15": AlternativeField("15分位成本"),
        "chip_cost_50": AlternativeField("50分位成本"),
        "chip_cost_85": AlternativeField("85分位成本"),
        "chip_cost_95": AlternativeField("95分位成本"),
        "chip_weighted_cost": AlternativeField("加权平均成本"),
        "chip_win_rate": AlternativeField("胜率", 0.01),
    },
    "limit_event": {
        "kpl_limit_up_flag": AlternativeField("<derived_limit_up_presence>"),
        "kpl_main_net_amount": AlternativeField("主力净额(元)"),
        "kpl_close_seal_amount": AlternativeField("收盘封单额"),
        "kpl_turnover_amount": AlternativeField("成交额"),
        "kpl_float_market_cap": AlternativeField("实际流通市值"),
        "kpl_max_seal_amount": AlternativeField("日内最大封单额"),
    },
}

DEFAULT_CLOCKS: dict[SourceKind, tuple[str, str]] = {
    "fund_flow": ("15:00:00", "18:00:00"),
    "auction": ("09:25:00", "09:26:00"),
    "margin": ("15:00:00", "18:00:00"),
    "industry": ("15:00:00", "18:00:00"),
    "chip": ("15:00:00", "18:00:00"),
    "limit_event": ("15:00:00", "18:00:00"),
}


@dataclass(frozen=True)
class QdAlternativeConfig:
    source_kind: SourceKind
    start_date: str
    end_date: str
    ingested_at: str
    availability_lag_days: int = 0
    timezone_offset: str = "+08:00"
    effective_clock: str | None = None
    available_clock: str | None = None
    instruments: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.source_kind not in SOURCE_FIELDS:
            raise QmtDataError(f"unsupported QD alternative source: {self.source_kind}")
        try:
            start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
            ingested = datetime.fromisoformat(self.ingested_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QmtDataError("alternative-data dates must be valid ISO values") from exc
        if start > end:
            raise QmtDataError("alternative-data start_date must not exceed end_date")
        if ingested.tzinfo is None:
            raise QmtDataError("alternative-data ingested_at must include a timezone")
        if self.availability_lag_days < 0:
            raise QmtDataError("availability_lag_days cannot be negative")
        if not self.timezone_offset.startswith(("+", "-")) or len(self.timezone_offset) != 6:
            raise QmtDataError("timezone_offset must use ±HH:MM")


@dataclass(frozen=True)
class AlternativeObservation:
    source_kind: SourceKind
    instrument: str
    name: str
    trade_date: str
    effective_at: str
    available_at: str
    ingested_at: str
    values: tuple[tuple[str, float | None], ...]

    def value(self, field: str) -> float | None:
        try:
            return dict(self.values)[field]
        except KeyError as exc:
            raise KeyError(f"unknown alternative-data field: {field}") from exc


@dataclass(frozen=True)
class QdAlternativeAudit:
    adapter_version: str
    source_kind: SourceKind
    source_sha256: str
    source_files: int
    rows: int
    instruments: int
    start_date: str
    end_date: str
    column_mapping: dict[str, str]
    unit_scales: dict[str, float]
    missing_values: dict[str, int]
    missing_names: int
    availability_policy: str
    warnings: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class QdAlternativeDataset:
    observations: tuple[AlternativeObservation, ...]
    audit: QdAlternativeAudit


def _selected_files(root: Path, start: date, end: date) -> tuple[Path, ...]:
    selected: list[tuple[date, Path]] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv" or len(path.stem) != 8:
            continue
        try:
            day = date(int(path.stem[:4]), int(path.stem[4:6]), int(path.stem[6:8]))
        except ValueError as exc:
            raise QmtDataError(f"invalid alternative-data partition: {path.name}") from exc
        if start <= day <= end:
            selected.append((day, path))
    selected.sort()
    if not selected:
        raise QmtDataError("alternative-data source has no selected daily CSV files")
    return tuple(path for _, path in selected)


def _required(row: dict[str, str | None], column: str, row_number: int) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise QmtDataError(f"row {row_number}: missing alternative-data column {column}")
    return value.strip()


def _optional_number(
    row: dict[str, str | None], column: str, field: str, row_number: int
) -> float | None:
    value = row.get(column)
    if value is None or not value.strip():
        return None
    return _parse_number(value, field, row_number=row_number)


def _load_limit_event_directory(
    root: Path,
    config: QdAlternativeConfig,
    files: tuple[Path, ...],
) -> QdAlternativeDataset:
    """Densify the 开盘啦 limit-up event table over the declared stock universe."""

    wanted = tuple(sorted({instrument.upper() for instrument in config.instruments}))
    if not wanted:
        raise QmtDataError("limit-event source requires an explicit instrument universe")
    manifest = build_selected_files_snapshot_manifest(root, files)
    effective_clock, available_clock = DEFAULT_CLOCKS["limit_event"]
    effective_clock = config.effective_clock or effective_clock
    available_clock = config.available_clock or available_clock
    numeric_columns = {
        "kpl_main_net_amount": "主力净额(元)",
        "kpl_close_seal_amount": "收盘封单额",
        "kpl_turnover_amount": "成交额",
        "kpl_float_market_cap": "实际流通市值",
        "kpl_max_seal_amount": "日内最大封单额",
    }
    expected_headers = {*COMMON_COLUMNS.values(), "标签", *numeric_columns.values()}
    observations: list[AlternativeObservation] = []
    encodings: set[str] = set()
    missing_values = {field: 0 for field in numeric_columns}
    missing_names = 0
    duplicate_rows = 0
    for path in files:
        text, encoding = _decode(path.read_bytes())
        encodings.add(encoding)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or ())
        missing = sorted(expected_headers - headers)
        if missing:
            raise QmtDataError(f"{path.name}: missing limit-event columns: {missing}")
        file_date = date(int(path.stem[:4]), int(path.stem[4:6]), int(path.stem[6:8]))
        present: dict[str, tuple[str, dict[str, float | None]]] = {}
        for row_number, row in enumerate(reader, start=2):
            label = (row.get("标签") or "").strip()
            if "涨停" not in label:
                continue
            trade_date = _parse_date(
                _required(row, COMMON_COLUMNS["trade_date"], row_number),
                row_number=row_number,
            )
            if trade_date != file_date.isoformat():
                raise QmtDataError(f"{path.name} row {row_number}: date differs from partition")
            instrument = _required(row, COMMON_COLUMNS["instrument"], row_number).upper()
            if instrument not in wanted:
                continue
            name = (row.get(COMMON_COLUMNS["name"]) or "").strip()
            if not name:
                missing_names += 1
            values = {
                field: _optional_number(row, column, field, row_number)
                for field, column in numeric_columns.items()
            }
            for field, value in values.items():
                if value is None:
                    missing_values[field] += 1
            if instrument in present:
                duplicate_rows += 1
                prior_name, prior = present[instrument]
                combined: dict[str, float | None] = {}
                for field in numeric_columns:
                    options = [value for value in (prior[field], values[field]) if value is not None]
                    if not options:
                        combined[field] = None
                    elif field == "kpl_main_net_amount":
                        combined[field] = max(options, key=lambda value: (abs(value), value))
                    else:
                        combined[field] = max(options)
                present[instrument] = (prior_name or name, combined)
            else:
                present[instrument] = (name, values)
        available_day = file_date + timedelta(days=config.availability_lag_days)
        effective_at = f"{file_date.isoformat()}T{effective_clock}{config.timezone_offset}"
        available_at = f"{available_day.isoformat()}T{available_clock}{config.timezone_offset}"
        if datetime.fromisoformat(available_at) < datetime.fromisoformat(effective_at):
            raise QmtDataError("limit-event availability precedes effective time")
        for instrument in wanted:
            if instrument in present:
                name, values = present[instrument]
                payload = {"kpl_limit_up_flag": 1.0, **values}
            else:
                name = ""
                payload = {field: 0.0 for field in SOURCE_FIELDS["limit_event"]}
            observations.append(
                AlternativeObservation(
                    source_kind="limit_event",
                    instrument=instrument,
                    name=name,
                    trade_date=file_date.isoformat(),
                    effective_at=effective_at,
                    available_at=available_at,
                    ingested_at=config.ingested_at,
                    values=tuple(sorted(payload.items())),
                )
            )
    return QdAlternativeDataset(
        observations=tuple(observations),
        audit=QdAlternativeAudit(
            adapter_version=QD_ALTERNATIVE_ADAPTER_VERSION,
            source_kind="limit_event",
            source_sha256=manifest.snapshot_sha256,
            source_files=len(files),
            rows=len(observations),
            instruments=len(wanted),
            start_date=date(
                int(files[0].stem[:4]), int(files[0].stem[4:6]), int(files[0].stem[6:8])
            ).isoformat(),
            end_date=date(
                int(files[-1].stem[:4]), int(files[-1].stem[4:6]), int(files[-1].stem[6:8])
            ).isoformat(),
            column_mapping={
                **COMMON_COLUMNS,
                "event_filter": "标签 contains 涨停",
                "kpl_limit_up_flag": "derived: present after event filter",
                **numeric_columns,
            },
            unit_scales={field: 1.0 for field in SOURCE_FIELDS["limit_event"]},
            missing_values={key: value for key, value in missing_values.items() if value},
            missing_names=missing_names,
            availability_policy=(
                f"user-declared effective={effective_clock}, available={available_clock}, "
                f"lag_days={config.availability_lag_days}, timezone={config.timezone_offset}"
            ),
            warnings=(
                "Non-events are deterministically densified to zero over the declared universe.",
                "Present events with missing measurements retain nulls and fail closed per factor.",
                f"Duplicate event rows aggregated deterministically: {duplicate_rows}.",
                f"Decoded encodings: {','.join(sorted(encodings))}.",
            ),
        ),
    )


def load_qd_alternative_directory(
    source: str | Path, config: QdAlternativeConfig
) -> QdAlternativeDataset:
    """Load one date-partitioned alternative source without mutating vendor files."""

    config.validate()
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise QmtDataError(f"QD alternative source is not a directory: {root}")
    start, end = date.fromisoformat(config.start_date), date.fromisoformat(config.end_date)
    files = _selected_files(root, start, end)
    if config.source_kind == "limit_event":
        return _load_limit_event_directory(root, config, files)
    manifest = build_selected_files_snapshot_manifest(root, files)
    fields = SOURCE_FIELDS[config.source_kind]
    wanted = {instrument.upper() for instrument in config.instruments}
    effective_clock, available_clock = DEFAULT_CLOCKS[config.source_kind]
    effective_clock = config.effective_clock or effective_clock
    available_clock = config.available_clock or available_clock
    observations: list[AlternativeObservation] = []
    seen: set[tuple[str, str]] = set()
    encodings: set[str] = set()
    expected_headers = {*COMMON_COLUMNS.values(), *(field.column for field in fields.values())}
    missing_values = {field: 0 for field in fields}
    missing_names = 0
    for path in files:
        text, encoding = _decode(path.read_bytes())
        encodings.add(encoding)
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or ())
        missing = sorted(expected_headers - headers)
        if missing:
            raise QmtDataError(f"{path.name}: missing alternative-data columns: {missing}")
        file_date = date(int(path.stem[:4]), int(path.stem[4:6]), int(path.stem[6:8]))
        for row_number, row in enumerate(reader, start=2):
            trade_date = _parse_date(
                _required(row, COMMON_COLUMNS["trade_date"], row_number),
                row_number=row_number,
            )
            if trade_date != file_date.isoformat():
                raise QmtDataError(f"{path.name} row {row_number}: date differs from partition")
            instrument = _required(
                row, COMMON_COLUMNS["instrument"], row_number
            ).upper()
            if wanted and instrument not in wanted:
                continue
            key = (trade_date, instrument)
            if key in seen:
                raise QmtDataError(f"duplicate alternative-data observation: {key}")
            seen.add(key)
            available_day = file_date + timedelta(days=config.availability_lag_days)
            effective_at = f"{trade_date}T{effective_clock}{config.timezone_offset}"
            available_at = f"{available_day.isoformat()}T{available_clock}{config.timezone_offset}"
            if datetime.fromisoformat(available_at) < datetime.fromisoformat(effective_at):
                raise QmtDataError("alternative-data availability precedes effective time")
            parsed_values: list[tuple[str, float | None]] = []
            for canonical, field in sorted(fields.items()):
                value = _optional_number(row, field.column, canonical, row_number)
                if value is None:
                    missing_values[canonical] += 1
                parsed_values.append(
                    (canonical, None if value is None else value * field.scale)
                )
            values = tuple(parsed_values)
            name = (row.get(COMMON_COLUMNS["name"]) or "").strip()
            if not name:
                missing_names += 1
            observations.append(
                AlternativeObservation(
                    source_kind=config.source_kind,
                    instrument=instrument,
                    name=name,
                    trade_date=trade_date,
                    effective_at=effective_at,
                    available_at=available_at,
                    ingested_at=config.ingested_at,
                    values=values,
                )
            )
    if not observations:
        raise QmtDataError("alternative-data selection contains no matching observations")
    observations.sort(key=lambda row: (row.trade_date, row.instrument))
    actual_dates = [row.trade_date for row in observations]
    column_mapping = {**COMMON_COLUMNS, **{key: value.column for key, value in fields.items()}}
    return QdAlternativeDataset(
        observations=tuple(observations),
        audit=QdAlternativeAudit(
            adapter_version=QD_ALTERNATIVE_ADAPTER_VERSION,
            source_kind=config.source_kind,
            source_sha256=manifest.snapshot_sha256,
            source_files=len(files),
            rows=len(observations),
            instruments=len({row.instrument for row in observations}),
            start_date=min(actual_dates),
            end_date=max(actual_dates),
            column_mapping=column_mapping,
            unit_scales={key: value.scale for key, value in fields.items()},
            missing_values={key: value for key, value in missing_values.items() if value},
            missing_names=missing_names,
            availability_policy=(
                f"user-declared effective={effective_clock}, available={available_clock}, "
                f"lag_days={config.availability_lag_days}, timezone={config.timezone_offset}"
            ),
            warnings=(
                "Availability is a conservative user-declared policy, not vendor event metadata.",
                "Calendar-day lag does not imply exchange-session normalization.",
                "Missing numeric cells are retained as null and must fail closed per factor.",
                f"Decoded encodings: {','.join(sorted(encodings))}.",
            ),
        ),
    )
