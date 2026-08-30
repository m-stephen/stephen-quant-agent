from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.qmt.asset_inventory import inventory_assets
from stephen_quant.qmt.data_warehouse import ingest_daily
from stephen_quant.workflows.v70_discover_alpha import run_v70_discover_alpha


def test_v70_metadata_prefers_warehouse_without_daily_directory(tmp_path: Path) -> None:
    source = tmp_path / "source" / "股票日K_按日期"
    source.mkdir(parents=True)
    (source / "20220104.csv").write_text(
        "日期,代码,名称,行业,开盘价,最高价,最低价,收盘价,成交量(手),成交额(千元),复权因子\n"
        "20220104,000001,TEST,TEST,10,11,9,10.5,1000,10000,1\n",
        encoding="gb18030",
    )
    warehouse = tmp_path / "warehouse"
    inventory = inventory_assets(tmp_path / "source", warehouse / "inventory")
    ingest_daily(tmp_path / "source", warehouse, inventory["manifest_path"])
    config = tmp_path / "paths.local.json"
    config.write_text(
        json.dumps({"version": 1, "paths": {"qd_warehouse_root": str(warehouse)}}),
        encoding="utf-8",
    )

    report = run_v70_discover_alpha(
        config,
        registry=ExperimentRegistry(tmp_path / "registry.sqlite3"),
        output_dir=tmp_path / "output",
        code_version="test",
        metadata_only=True,
    )

    daily = next(item for item in report.source_coverage if item.source == "qd_daily")
    assert daily.status == "AVAILABLE"
    assert daily.dated_sessions == 1
    assert daily.coverage_manifest_sha256 is not None
