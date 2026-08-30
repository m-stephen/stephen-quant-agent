from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.cli import main


def test_warehouse_cli_round_trip(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "source" / "股票日K_按日期"
    source.mkdir(parents=True)
    (source / "20260105.csv").write_text(
        "日期,代码,名称,行业,开盘价,最高价,最低价,收盘价,成交量(手),成交额(千元),复权因子\n"
        "20260105,000001,平安银行,银行,10,12,9,11,1000,11000,1\n",
        encoding="gb18030",
    )
    config = tmp_path / "paths.local.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "paths": {
                    "qd_asset_root": str(tmp_path / "source"),
                    "qd_warehouse_root": str(tmp_path / "warehouse"),
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv", ["stephen-quant", "data-update-weekly", "--paths-config", str(config)]
    )
    main()
    payload = json.loads(capsys.readouterr().out)
    assert payload["verification"]["passed"] is True
    assert payload["ingest"]["new_revisions"] == 1
