from __future__ import annotations

import hashlib
import json
import struct
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineConfig
from stephen_quant.cli import build_parser
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt import (
    DatExportConfig,
    QmtDatError,
    export_qmt_dat_daily_csv,
    load_qmt_daily_csv,
    parse_qmt_daily_dat,
    verify_qmt_dat_manifest,
)
from stephen_quant.workflows import QmtBacktestRunConfig, run_qmt_backtest_workflow

MARKET_TZ = timezone(timedelta(hours=8))


def _record(
    day: date,
    *,
    open_: float = 10.0,
    high: float = 10.5,
    low: float = 9.8,
    close: float = 10.2,
    volume_lots: int = 12_345,
    amount: int = 12_550_000,
    pre_close: float = 9.9,
) -> bytes:
    raw = bytearray(64)
    raw[0:8] = bytes.fromhex("00000000fb7f0000")
    timestamp = int(datetime.combine(day, datetime.min.time(), tzinfo=MARKET_TZ).timestamp())
    struct.pack_into("<I", raw, 8, timestamp)
    struct.pack_into(
        "<4I",
        raw,
        12,
        *(round(price * 1_000) for price in (open_, high, low, close)),
    )
    struct.pack_into("<I", raw, 32, volume_lots)
    struct.pack_into("<Q", raw, 40, amount)
    struct.pack_into("<I", raw, 48, 15)
    struct.pack_into("<I", raw, 60, round(pre_close * 1_000))
    return bytes(raw)


def _write_dat(
    root: Path,
    instrument: str,
    records: list[bytes],
    *,
    tail: bytes = bytes.fromhex("00000000fb7f0000"),
) -> Path:
    symbol, market = instrument.split(".")
    path = root / market / "86400" / f"{symbol}.DAT"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(records) + tail)
    return path


def test_parse_qmt_daily_dat_uses_locked_offsets_and_units(tmp_path: Path) -> None:
    path = _write_dat(
        tmp_path,
        "600000.SH",
        [_record(date(2025, 1, 2)), _record(date(2025, 1, 3), close=10.4)],
    )

    bars, audit = parse_qmt_daily_dat(path, instrument="600000.SH")

    assert [bar.trade_date for bar in bars] == ["2025-01-02", "2025-01-03"]
    assert bars[0].open == 10.0
    assert bars[0].volume == 1_234_500
    assert bars[0].amount == 12_550_000
    assert audit.records == 2
    assert audit.trailing_bytes == 8
    assert audit.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_record(date(2025, 1, 2)) + b"bad", "tail length"),
        (
            _record(date(2025, 1, 3)) + _record(date(2025, 1, 2)),
            "non-monotonic",
        ),
        (
            _record(date(2025, 1, 2), volume_lots=0, amount=1),
            "zero state differs",
        ),
        (
            _record(date(2025, 1, 2), amount=125_500),
            "scale is implausible",
        ),
    ],
)
def test_parser_fails_closed_on_corrupt_layout_or_semantics(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    path = tmp_path / "600000.DAT"
    path.write_bytes(payload)

    with pytest.raises(QmtDatError, match=message):
        parse_qmt_daily_dat(path, instrument="600000.SH")


def test_parser_rejects_non_equity_codes_and_non_midnight_timestamp(tmp_path: Path) -> None:
    path = tmp_path / "sample.DAT"
    path.write_bytes(_record(date(2025, 1, 2)))
    with pytest.raises(QmtDatError, match="restricted to A-share"):
        parse_qmt_daily_dat(path, instrument="510300.SH")

    shifted = bytearray(_record(date(2025, 1, 2)))
    timestamp = struct.unpack_from("<I", shifted, 8)[0]
    struct.pack_into("<I", shifted, 8, timestamp + 60)
    path.write_bytes(shifted)
    with pytest.raises(QmtDatError, match="midnight"):
        parse_qmt_daily_dat(path, instrument="600000.SH")


def test_export_writes_canonical_csv_and_deterministic_provenance(tmp_path: Path) -> None:
    datadir = tmp_path / "QMT" / "datadir"
    _write_dat(
        datadir,
        "600000.SH",
        [_record(date(2025, 1, 2)), _record(date(2025, 1, 3))],
    )
    _write_dat(
        datadir,
        "000001.SZ",
        [_record(date(2025, 1, 2), close=10.3), _record(date(2025, 1, 3), close=10.4)],
    )
    output = tmp_path / "export" / "daily.csv"

    result = export_qmt_dat_daily_csv(
        DatExportConfig(
            datadir=str(datadir.parent),
            output_csv=str(output),
            start_date="2025-01-02",
            end_date="2025-01-03",
            stocks=("600000.SH", "000001.SZ"),
        )
    )
    dataset = load_qmt_daily_csv(output, adjustment="none")
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))

    assert result.rows == 4
    assert dataset.audit.instruments == 2
    assert manifest["source_kind"] == "qmt_86400_dat_read_only"
    assert manifest["schema"]["volume"]["source_unit"] == "lot"
    assert manifest["schema"]["volume"]["output_unit"] == "share"
    assert manifest["schema"]["amount"]["unit"] == "CNY"
    assert [source["relative_path"] for source in manifest["sources"]] == [
        "SH/86400/600000.DAT",
        "SZ/86400/000001.DAT",
    ]
    assert "QMT" not in json.dumps(manifest)
    assert manifest["output"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    verified_path, verified_sha256 = verify_qmt_dat_manifest(output, adjustment="none")
    assert verified_path == Path(result.manifest_path)
    assert verified_sha256 == hashlib.sha256(verified_path.read_bytes()).hexdigest()

    output.write_text(output.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(QmtDatError, match="output SHA-256 mismatch"):
        verify_qmt_dat_manifest(output, adjustment="none")


def test_export_rejects_adjustment_empty_window_and_overwrite(tmp_path: Path) -> None:
    datadir = tmp_path / "datadir"
    _write_dat(datadir, "600000.SH", [_record(date(2025, 1, 2))])
    output = tmp_path / "daily.csv"
    base = {
        "datadir": str(datadir),
        "output_csv": str(output),
        "start_date": "2025-01-02",
        "end_date": "2025-01-03",
        "stocks": ("600000.SH",),
    }

    with pytest.raises(QmtDatError, match="adjustment='none'"):
        export_qmt_dat_daily_csv(DatExportConfig(**base, adjustment="front_ratio"))
    with pytest.raises(QmtDatError, match="no DAT bars"):
        export_qmt_dat_daily_csv(
            DatExportConfig(**{**base, "start_date": "2026-01-01", "end_date": "2026-01-02"})
        )

    export_qmt_dat_daily_csv(DatExportConfig(**base))
    with pytest.raises(QmtDatError, match="output already exists"):
        export_qmt_dat_daily_csv(DatExportConfig(**base))


def test_dat_provenance_is_verified_and_registered_by_backtest(tmp_path: Path) -> None:
    dates: list[date] = []
    current = date(2025, 1, 2)
    while len(dates) < 30:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    datadir = tmp_path / "datadir"
    for instrument, offset in (("600000.SH", 0.0), ("000001.SZ", 1.0)):
        _write_dat(
            datadir,
            instrument,
            [
                _record(
                    day,
                    open_=10 + offset + index / 100,
                    high=10.5 + offset + index / 100,
                    low=9.8 + offset + index / 100,
                    close=10.2 + offset + index / 100,
                    amount=12_550_000 + index * 10_000,
                )
                for index, day in enumerate(dates)
            ],
        )
    output = tmp_path / "daily.csv"
    export_qmt_dat_daily_csv(
        DatExportConfig(
            datadir=str(datadir),
            output_csv=str(output),
            start_date=dates[0].isoformat(),
            end_date=dates[-1].isoformat(),
            stocks=("600000.SH", "000001.SZ"),
        )
    )
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    registry.initialize()

    run = run_qmt_backtest_workflow(
        output,
        registry=registry,
        output_dir=tmp_path / "reports",
        code_version="test-commit",
        config=QmtBacktestRunConfig(
            factor_id="ret_5",
            factor_version="1.0.0",
            adjustment="none",
            train_start="2023-01-01",
            train_end="2023-12-31",
            validation_start="2024-01-01",
            validation_end="2024-12-31",
            test_start=dates[10].isoformat(),
            test_end=dates[-2].isoformat(),
            adv_lookback=5,
            portfolio=BaselineConfig(top_k=1, max_position_weight=1.0),
        ),
    )

    assert run.provenance_manifest_path == Path(f"{output}.manifest.json")
    assert run.provenance_manifest_sha256
    assert registry.artifact_count(run.trial_id) == 4


def test_qmt_dat_cli_contract(tmp_path: Path) -> None:
    stock_file = tmp_path / "stocks.txt"
    stock_file.write_text("600000.SH\n000001.SZ\n", encoding="utf-8")
    args = build_parser().parse_args(
        [
            "qmt-dat-export",
            "--datadir",
            str(tmp_path / "datadir"),
            "--output-csv",
            str(tmp_path / "daily.csv"),
            "--start",
            "2025-01-01",
            "--end",
            "2025-12-31",
            "--stock-file",
            str(stock_file),
        ]
    )

    assert args.command == "qmt-dat-export"
    assert args.adjustment == "none"
