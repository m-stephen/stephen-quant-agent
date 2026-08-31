from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

from stephen_quant.qmt.multisource_warehouse import (
    ingest_multisource_assets,
    load_warehouse_alternative,
    verify_multisource_snapshot,
)
from stephen_quant.qmt.qd_alternative import SOURCE_FIELDS


def _write_source(
    root: Path,
    *,
    folder: str,
    source_kind: str,
    day: str = "20220104",
) -> None:
    path = root / folder / f"{day}.csv"
    path.parent.mkdir(parents=True)
    fields = SOURCE_FIELDS[source_kind]
    headers = ["日期", "代码", "名称", *(field.column for field in fields.values())]
    values = [day, "000001.SZ", "平安银行", *(str(index + 1) for index in range(len(fields)))]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow(values)


def test_multisource_ingest_verify_replay_and_factor_adapter(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    _write_source(source, folder="资金流向", source_kind="fund_flow")
    _write_source(source, folder="集合竞价", source_kind="auction")

    first = ingest_multisource_assets(
        source,
        warehouse,
        seven_zip_executable=sys.executable,
        datasets=("qd_fund_flow", "qd_auction"),
    )
    assert first["objects"] == 2
    assert first["rows"] == 2
    verification = verify_multisource_snapshot(warehouse, str(first["snapshot_id"]))
    assert verification["passed"] is True
    assert verification["coverage_complete"] is False
    assert "qd_fund_flow" not in verification["missing_datasets"]

    dataset = load_warehouse_alternative(
        warehouse,
        source_kind="fund_flow",
        start_date="2022-01-01",
        end_date="2022-12-31",
        instruments=("000001.SZ",),
        verified_snapshot_id=str(first["snapshot_id"]),
    )
    assert dataset.audit.rows == 1
    assert dataset.observations[0].value("small_buy_volume") == 100.0
    assert dataset.observations[0].available_at.startswith("2022-01-04T18:00:00")
    assert datetime.fromisoformat(dataset.observations[0].available_at).utcoffset() is not None

    replay = ingest_multisource_assets(
        source,
        warehouse,
        seven_zip_executable=sys.executable,
        datasets=("qd_fund_flow", "qd_auction"),
    )
    assert replay["objects"] == 0
    assert replay["rows"] == 0
    assert replay["snapshot_id"] == first["snapshot_id"]


def test_dated_xlsx_without_worksheet_is_preserved_as_document(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    artifact = source / "同花顺概念板块" / "概念统计_20251128.xlsx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"vendor report wrapper, not an OOXML workbook")

    result = ingest_multisource_assets(
        source,
        warehouse,
        seven_zip_executable=sys.executable,
        datasets=("qd_concept",),
    )

    assert result["rows"] == 0
    import duckdb

    connection = duckdb.connect(
        str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True
    )
    try:
        row = connection.execute(
            "SELECT relative_path, size_bytes FROM multisource_documents"
        ).fetchone()
    finally:
        connection.close()
    assert row == ("同花顺概念板块/概念统计_20251128.xlsx", artifact.stat().st_size)
