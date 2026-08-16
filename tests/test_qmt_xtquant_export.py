from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.qmt import load_qmt_daily_csv
from stephen_quant.qmt.xtquant_export import (
    XtquantExportConfig,
    XtquantExportError,
    export_qmt_daily_csv,
    find_xtquant_site_packages,
    read_stock_file,
)


class _FakeFrame:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records
        self.index = list(range(len(records)))

    def to_dict(self, *, orient: str) -> list[dict[str, object]]:
        assert orient == "records"
        return self._records


class _FakeXtdata:
    def __init__(self, frames: dict[str, _FakeFrame] | Exception) -> None:
        self.frames = frames
        self.calls: list[dict[str, object]] = []
        self.sectors = {"沪深A股": ["000001.SZ", "600000.SH"]}

    def get_local_data(self, **kwargs: object) -> dict[str, _FakeFrame]:
        self.calls.append(kwargs)
        if isinstance(self.frames, Exception):
            raise self.frames
        return self.frames

    def get_stock_list_in_sector(self, sector: str) -> list[str]:
        return self.sectors.get(sector, [])


def _milliseconds(day: int) -> int:
    market_tz = timezone(timedelta(hours=8))
    return int(datetime(2025, 1, day, tzinfo=market_tz).timestamp() * 1000)


def _record(day: int, price: float) -> dict[str, object]:
    return {
        "time": _milliseconds(day),
        "open": price,
        "high": price + 0.2,
        "low": price - 0.2,
        "close": price + 0.1,
        "volume": 1_000_000.0,
        "amount": 10_000_000.0,
    }


def _config(tmp_path: Path, **changes: object) -> XtquantExportConfig:
    values: dict[str, object] = {
        "qmt_home": str(tmp_path / "QMT" / "datadir"),
        "output_csv": str(tmp_path / "qmt-daily.csv"),
        "start_time": "2025-01-02",
        "end_time": "2025-01-03",
        "adjustment": "front_ratio",
        "stocks": ("000001.SZ", "600000.SH"),
    }
    values.update(changes)
    return XtquantExportConfig(**values)  # type: ignore[arg-type]


def test_xtquant_export_uses_local_only_api_and_writes_canonical_csv(tmp_path: Path) -> None:
    fake = _FakeXtdata(
        {
            "000001.SZ": _FakeFrame([_record(2, 10.0), _record(3, 10.5)]),
            "600000.SH": _FakeFrame([_record(2, 8.0), _record(3, 8.2)]),
        }
    )

    result = export_qmt_daily_csv(_config(tmp_path), xtdata_module=fake)
    dataset = load_qmt_daily_csv(result.output_csv, adjustment="front_ratio")

    assert result.rows == 4
    assert result.exported_instruments == 2
    assert dataset.audit.column_mapping["trade_date"] == "trade_date"
    assert fake.calls[0]["period"] == "1d"
    assert fake.calls[0]["fill_data"] is False
    assert fake.calls[0]["start_time"] == "20250102"
    assert fake.calls[0]["end_time"] == "20250103"


def test_sector_export_and_unavailable_bars_are_explicit(tmp_path: Path) -> None:
    unavailable = {
        "time": _milliseconds(2),
        "open": math.nan,
        "high": math.nan,
        "low": math.nan,
        "close": math.nan,
        "volume": 0.0,
        "amount": 0.0,
    }
    fake = _FakeXtdata(
        {
            "000001.SZ": _FakeFrame([unavailable, _record(3, 10.5)]),
            "600000.SH": _FakeFrame([_record(2, 8.0), _record(3, 8.2)]),
        }
    )

    result = export_qmt_daily_csv(
        _config(tmp_path, stocks=(), sector="沪深A股"), xtdata_module=fake
    )

    assert result.rows == 3
    assert result.skipped_unavailable_bars == 1
    assert fake.calls[0]["stock_list"] == ["000001.SZ", "600000.SH"]


def test_partial_corrupt_bar_fails_without_replacing_destination(tmp_path: Path) -> None:
    corrupt = _record(2, 10.0)
    corrupt["high"] = math.nan
    fake = _FakeXtdata(
        {
            "000001.SZ": _FakeFrame([corrupt]),
            "600000.SH": _FakeFrame([_record(2, 8.0)]),
        }
    )

    with pytest.raises(XtquantExportError, match="non-finite high"):
        export_qmt_daily_csv(_config(tmp_path), xtdata_module=fake)

    assert not Path(_config(tmp_path).output_csv).exists()


def test_export_refuses_overwrite_and_missing_instruments(tmp_path: Path) -> None:
    output = Path(_config(tmp_path).output_csv)
    output.write_text("do not replace", encoding="utf-8")
    fake = _FakeXtdata({"000001.SZ": _FakeFrame([_record(2, 10.0)])})

    with pytest.raises(XtquantExportError, match="output already exists"):
        export_qmt_daily_csv(_config(tmp_path), xtdata_module=fake)
    assert output.read_text(encoding="utf-8") == "do not replace"

    output.unlink()
    with pytest.raises(XtquantExportError, match="no frame"):
        export_qmt_daily_csv(_config(tmp_path), xtdata_module=fake)
    assert not output.exists()


def test_connection_failure_has_actionable_message(tmp_path: Path) -> None:
    fake = _FakeXtdata(RuntimeError("opaque vendor error"))

    with pytest.raises(XtquantExportError, match="log in to QMT"):
        export_qmt_daily_csv(_config(tmp_path), xtdata_module=fake)


def test_qmt_path_discovery_stock_file_and_cli_contract(tmp_path: Path) -> None:
    home = tmp_path / "QMT"
    package = home / "bin.x64" / "Lib" / "site-packages" / "xtquant"
    package.mkdir(parents=True)
    (package / "xtdata.py").write_text("", encoding="utf-8")
    assert find_xtquant_site_packages(home / "datadir") == package.parent

    stock_file = tmp_path / "stocks.txt"
    stock_file.write_text("000001.sz\n# comment\n600000.SH # bank\n", encoding="utf-8")
    assert read_stock_file(stock_file) == ("000001.SZ", "600000.SH")

    args = build_parser().parse_args(
        [
            "qmt-export",
            "--qmt-home",
            str(home),
            "--output-csv",
            str(tmp_path / "out.csv"),
            "--start",
            "2025-01-01",
            "--end",
            "2025-12-31",
            "--adjustment",
            "front_ratio",
            "--stock-file",
            str(stock_file),
        ]
    )
    assert args.command == "qmt-export"
    assert args.stock_file == str(stock_file)
