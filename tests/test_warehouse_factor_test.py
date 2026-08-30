from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.qmt.asset_inventory import inventory_assets
from stephen_quant.qmt.data_warehouse import ingest_daily
from stephen_quant.qmt.warehouse_adapter import load_qd_warehouse_daily
from stephen_quant.workflows.warehouse_factor_test import (
    WarehouseFactorTestConfig,
    run_warehouse_factor_test,
)

HEADER = "日期,代码,名称,行业,开盘价,最高价,最低价,收盘价,成交量(手),成交额(千元),复权因子\n"


def _sessions(start: date, count: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _write_panel(root: Path) -> tuple[list[date], list[date]]:
    folder = root / "股票日K_按日期"
    folder.mkdir(parents=True)
    selection = _sessions(date(2021, 11, 1), 5)
    research = _sessions(date(2022, 1, 3), 30)
    instruments = ("000001", "000002", "000003")
    for index, day in enumerate(selection + research):
        rows = [HEADER]
        for stock_index, instrument in enumerate(instruments):
            close = 10 + stock_index + index * (0.01 + stock_index * 0.002)
            amount = 10_000 + (2 - stock_index) * 1_000
            rows.append(
                f"{day:%Y%m%d},{instrument},TEST{stock_index},TEST,{close:.4f},"
                f"{close * 1.02:.4f},{close * 0.98:.4f},{close:.4f},1000,{amount},1\n"
            )
        (folder / f"{day:%Y%m%d}.csv").write_text("".join(rows), encoding="gb18030")
    return selection, research


def test_warehouse_adapter_and_factor_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    warehouse = tmp_path / "warehouse"
    selection, research = _write_panel(source)
    inventory = inventory_assets(source, warehouse / "inventory")
    ingest = ingest_daily(source, warehouse, inventory["manifest_path"])

    dataset = load_qd_warehouse_daily(
        warehouse,
        start_date=research[0].isoformat(),
        end_date=research[-1].isoformat(),
        instruments=("000001", "000002", "000003"),
    )
    assert dataset.audit.source_sha256 == ingest["snapshot_id"]
    assert dataset.audit.encoding == "duckdb/parquet"
    assert dataset.audit.rows == 90
    assert dataset.bars[0].volume == 100_000

    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    report = run_warehouse_factor_test(
        warehouse,
        registry=registry,
        output_dir=tmp_path / "report",
        code_version="test",
        config=WarehouseFactorTestConfig(
            universe_start=selection[0].isoformat(),
            universe_end=selection[-1].isoformat(),
            data_start=research[0].isoformat(),
            data_end=research[-1].isoformat(),
            evaluation_start=research[22].isoformat(),
            evaluation_end=research[-2].isoformat(),
            top_n=3,
            minimum_universe_sessions=3,
            minimum_cross_section=2,
        ),
    )
    assert report.verdict == "DATABASE_FACTOR_PATH_OPERATIONAL"
    assert report.trial_number == 1
    assert report.evaluation_dates >= 2
    assert registry.trial_count(report.experiment_id) == 1
    assert (tmp_path / "report" / "warehouse-factor-test.zh.md").is_file()
    assert (tmp_path / "report" / "warehouse-factor-test.en.md").is_file()
