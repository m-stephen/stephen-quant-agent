from __future__ import annotations

import json
import zipfile
from pathlib import Path

import duckdb
import pytest

from stephen_quant.qmt.asset_inventory import inventory_assets
from stephen_quant.qmt.data_warehouse import (
    ingest_daily,
    verify_snapshot,
    weekly_update,
)
from stephen_quant.qmt.models import QmtDataError

HEADER = "日期,代码,名称,行业,开盘价,最高价,最低价,收盘价,成交量(手),成交额(千元),复权因子\n"


def _write_daily(root: Path, day: str, close: float = 11.0) -> Path:
    folder = root / "股票日K_按日期"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day}.csv"
    path.write_text(
        HEADER + f"{day},000001,平安银行,银行,10,12,9,{close},1000,11000,1\n",
        encoding="gb18030",
    )
    return path


def test_daily_ingest_replay_and_revision_history(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_daily(source, "20260105")
    inventory = inventory_assets(source, warehouse / "inventory")

    first = ingest_daily(source, warehouse, inventory["manifest_path"])
    assert first["status"] == "COMPLETED"
    assert first["new_revisions"] == 1
    verification = verify_snapshot(warehouse, str(first["snapshot_id"]))
    assert verification["passed"] is True
    assert verification["revision_rows"] == verification["current_rows"] == 1

    replay = ingest_daily(source, warehouse, inventory["manifest_path"])
    assert replay["status"] == "REPLAY_NOOP"
    assert replay["snapshot_id"] == first["snapshot_id"]

    _write_daily(source, "20260105", close=11.5)
    updated_inventory = inventory_assets(source, warehouse / "inventory")
    revised = ingest_daily(source, warehouse, updated_inventory["manifest_path"])
    assert revised["new_revisions"] == 1
    revised_verification = verify_snapshot(warehouse, str(revised["snapshot_id"]))
    assert revised_verification["passed"] is True
    assert revised_verification["revision_rows"] == 2
    assert revised_verification["current_rows"] == 1

    db = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    try:
        active = db.execute(
            "SELECT parquet_relative_path FROM partitions WHERE active"
        ).fetchone()[0]
        current_close = db.execute(
            'SELECT "close" FROM read_parquet(?) ORDER BY ingested_at DESC LIMIT 1',
            [str(warehouse / active)],
        ).fetchone()[0]
    finally:
        db.close()
    assert current_close == 11.5


def test_ingest_rejects_source_changed_after_inventory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    path = _write_daily(source, "20260105")
    inventory = inventory_assets(source, warehouse / "inventory")
    path.write_text(HEADER + "20260105,000001,x,x,10,12,9,99,1,1,1\n", encoding="gb18030")
    with pytest.raises(QmtDataError, match="changed after inventory"):
        ingest_daily(source, warehouse, inventory["manifest_path"])


def test_invalid_rows_fail_closed_without_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_daily(source, "20260105", close=13.0)
    inventory = inventory_assets(source, warehouse / "inventory")
    with pytest.raises(QmtDataError, match="inconsistent high"):
        ingest_daily(source, warehouse, inventory["manifest_path"])
    assert list((warehouse / "snapshots").glob("*.json")) == []


def test_multifile_failure_does_not_partially_register_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_daily(source, "20260105")
    _write_daily(source, "20260106", close=13.0)
    inventory = inventory_assets(source, warehouse / "inventory")
    with pytest.raises(QmtDataError, match="inconsistent high"):
        ingest_daily(source, warehouse, inventory["manifest_path"])
    db = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"))
    try:
        assert db.execute("SELECT count(*) FROM source_files").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
    finally:
        db.close()


def test_weekly_update_is_one_command_and_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_daily(source, "20260105")
    first = weekly_update(source, warehouse)
    second = weekly_update(source, warehouse)
    assert first["verification"]["passed"] is True
    assert second["ingest"]["status"] == "REPLAY_NOOP"


def test_weekly_update_reads_new_csv_directly_from_zip(tmp_path: Path) -> None:
    source = tmp_path / "source"
    folder = source / "股票日K_按日期" / "历史数据压缩包"
    folder.mkdir(parents=True)
    raw = (
        HEADER + "20260105,000001,平安银行,银行,10,12,9,11,1000,11000,1\n"
    ).encode("gb18030")
    with zipfile.ZipFile(folder / "weekly.zip", "w") as archive:
        archive.writestr("incoming/20260105.csv", raw)
    warehouse = tmp_path / "warehouse"

    first = weekly_update(source, warehouse)
    second = weekly_update(source, warehouse)

    assert first["ingest"]["new_source_files"] == 1
    assert first["ingest"]["new_revisions"] == 1
    assert first["verification"]["passed"] is True
    assert second["ingest"]["status"] == "REPLAY_NOOP"


def test_removing_extracted_copy_does_not_reingest_unchanged_archive_member(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    daily = source / "股票日K_按日期"
    daily.mkdir(parents=True)
    raw = (
        HEADER + "20260105,000001,平安银行,银行,10,12,9,11,1000,11000,1\n"
    ).encode("gb18030")
    extracted = daily / "20260105.csv"
    extracted.write_bytes(raw)
    with zipfile.ZipFile(daily / "history.zip", "w") as archive:
        archive.writestr("20260105.csv", raw)
    warehouse = tmp_path / "warehouse"
    first = weekly_update(source, warehouse)
    assert first["ingest"]["new_source_files"] == 1

    extracted.unlink()
    second = weekly_update(source, warehouse)

    assert second["ingest"]["status"] == "REPLAY_NOOP"
    assert second["ingest"]["new_revisions"] == 0


def test_manifest_carries_no_absolute_source_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_daily(source, "20260105")
    inventory = inventory_assets(source, warehouse / "inventory")
    text = Path(inventory["manifest_path"]).read_text(encoding="utf-8")
    assert str(source.resolve()) not in text
    assert json.loads(text)["source_root_name"] == "source"
