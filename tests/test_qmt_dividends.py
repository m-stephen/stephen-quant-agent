from __future__ import annotations

import csv
import json
import struct
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from stephen_quant.qmt import (
    DIVIDEND_PARSER_VERSION,
    DIVIDEND_SCHEMA_SHA256,
    DatExportConfig,
    DividendSourceFile,
    QmtDailyBar,
    QmtDividendAudit,
    QmtDividendError,
    QmtDividendRecord,
    apply_back_ratio_adjustment,
    export_qmt_dat_daily_csv,
    parse_qmt_dividend_value,
    verify_qmt_dat_manifest,
)
from stephen_quant.cli import build_parser

MARKET_TZ = timezone(timedelta(hours=8))


def _action(
    ex_date: date,
    *,
    instrument: str = "600000.SH",
    dr: float = 1.1,
) -> QmtDividendRecord:
    timestamp = int(datetime.combine(ex_date, datetime.min.time(), tzinfo=MARKET_TZ).timestamp() * 1000)
    return QmtDividendRecord(
        instrument=instrument,
        ex_dividend_date=ex_date.isoformat(),
        record_date=None,
        interest=0.4,
        stock_bonus=0.0,
        stock_gift=0.0,
        allot_num=0.0,
        allot_price=0.0,
        gugai=0.0,
        unknown64_raw=0.0,
        dr=dr,
        timestamp_raw=timestamp,
    )


def _dividend_value(ex_date: date, *, dr: float = 1.1) -> tuple[bytes, bytes]:
    timestamp = int(datetime.combine(ex_date, datetime.min.time(), tzinfo=MARKET_TZ).timestamp() * 1000)
    raw_date = int(ex_date.strftime("%Y%m%d"))
    key = f"SH|600000|4000|{timestamp}".encode()
    value = struct.pack(
        "<qq8dIIII",
        0,
        timestamp,
        0.4,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        dr,
        raw_date - 1,
        0,
        raw_date,
        0,
    )
    return key, value


def _daily_record(day: date, price: float) -> bytes:
    raw = bytearray(64)
    timestamp = int(datetime.combine(day, datetime.min.time(), tzinfo=MARKET_TZ).timestamp())
    struct.pack_into("<I", raw, 8, timestamp)
    struct.pack_into("<4I", raw, 12, *(round(value * 1000) for value in (price, price, price, price)))
    struct.pack_into("<I", raw, 32, 10_000)
    struct.pack_into("<Q", raw, 40, round(price * 1_000_000))
    struct.pack_into("<I", raw, 60, round(price * 1000))
    return bytes(raw)


def test_dividend_value_decodes_locked_offsets() -> None:
    key, value = _dividend_value(date(2025, 7, 16), dr=1.030325)

    record = parse_qmt_dividend_value(key, value)

    assert record is not None
    assert record.instrument == "600000.SH"
    assert record.ex_dividend_date == "2025-07-16"
    assert record.record_date == "2025-07-15"
    assert record.interest == 0.4
    assert record.dr == pytest.approx(1.030325)


def test_dividend_value_fails_closed_on_mismatch_and_bad_factor() -> None:
    key, value = _dividend_value(date(2025, 7, 16))
    damaged = bytearray(value)
    struct.pack_into("<q", damaged, 8, 1)
    with pytest.raises(QmtDividendError, match="timestamps disagree"):
        parse_qmt_dividend_value(key, bytes(damaged))

    _, damaged_factor = _dividend_value(date(2025, 7, 16), dr=0.0)
    with pytest.raises(QmtDividendError, match="adjustment factor"):
        parse_qmt_dividend_value(key, damaged_factor)


def test_back_ratio_uses_actions_only_on_and_after_ex_date() -> None:
    bars = tuple(
        QmtDailyBar(
            instrument="600000.SH",
            trade_date=day.isoformat(),
            open=10.0,
            high=10.0,
            low=10.0,
            close=10.0,
            volume=1_000_000,
            amount=10_000_000,
        )
        for day in (date(2025, 7, 15), date(2025, 7, 16), date(2025, 7, 17))
    )

    adjusted = apply_back_ratio_adjustment(
        bars, {"600000.SH": (_action(date(2025, 7, 16), dr=1.1),)}
    )

    assert [bar.close for bar in adjusted] == pytest.approx([10.0, 11.0, 11.0])
    assert [bar.volume for bar in adjusted] == [1_000_000, 1_000_000, 1_000_000]


def test_dat_export_can_hash_link_back_ratio_corporate_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datadir = tmp_path / "datadir"
    source = datadir / "SH" / "86400" / "600000.DAT"
    source.parent.mkdir(parents=True)
    source.write_bytes(
        _daily_record(date(2025, 7, 15), 10.0)
        + _daily_record(date(2025, 7, 16), 9.0)
    )
    action = _action(date(2025, 7, 16), dr=1.1)
    audit = QmtDividendAudit(
        parser_version=DIVIDEND_PARSER_VERSION,
        schema_sha256=DIVIDEND_SCHEMA_SHA256,
        snapshot_sha256="a" * 64,
        source_files=(DividendSourceFile("000001.ldb", "b" * 64, 96),),
        requested_instruments=1,
        selected_records=1,
        first_ex_dividend_date="2025-07-16",
        last_ex_dividend_date="2025-07-16",
    )
    monkeypatch.setattr(
        "stephen_quant.qmt.dat_binary.load_qmt_dividend_records",
        lambda *_args, **_kwargs: ({"600000.SH": (action,)}, audit),
    )
    output = tmp_path / "daily.csv"

    result = export_qmt_dat_daily_csv(
        DatExportConfig(
            datadir=str(datadir),
            output_csv=str(output),
            start_date="2025-07-15",
            end_date="2025-07-16",
            stocks=("600000.SH",),
            adjustment="back_ratio",
        )
    )

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert float(rows[0]["close"]) == pytest.approx(10.0)
    assert float(rows[1]["close"]) == pytest.approx(9.9)
    assert result.adjustment == "back_ratio"
    assert manifest["corporate_actions"]["snapshot_sha256"] == "a" * 64
    verify_qmt_dat_manifest(output, adjustment="back_ratio")


def test_validation_cli_accepts_explicit_back_ratio() -> None:
    args = build_parser().parse_args(
        [
            "qmt-dat-validate",
            "--datadir",
            "QMT/datadir",
            "--data-start",
            "2025-01-01",
            "--data-end",
            "2025-12-31",
            "--adjustment",
            "back_ratio",
            "--stocks",
            "600000.SH",
            "--train-start",
            "2022-01-01",
            "--train-end",
            "2022-12-31",
            "--validation-start",
            "2023-01-01",
            "--validation-end",
            "2023-12-31",
            "--test-start",
            "2024-01-01",
            "--test-end",
            "2024-12-31",
        ]
    )

    assert args.adjustment == "back_ratio"
