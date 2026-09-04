from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from stephen_quant.qmt.minute_warehouse import ingest_minute_archives
from stephen_quant.workflows.v10_platform import run_v10_platform


def _source(root: Path) -> str:
    folder = root / "分钟K线合集" / "2024" / "最新更新"
    folder.mkdir(parents=True)
    archive = folder / "20240102.zip"
    header = "日期,时间,开盘,最高,最低,收盘,成交量,成交额\n"
    rows = header + "2024-01-02,09:31,10,10.1,9.9,10.05,100,1005\n2024-01-02,15:00,10.05,10.2,10,10.1,150,1515\n"
    with zipfile.ZipFile(archive, "w") as handle:
        for interval in (1, 5, 15, 30, 60):
            handle.writestr(f"{interval}min/sz000001.csv", rows.encode("utf-8-sig"))
    return str(archive)


def test_v10_platform_replays_and_writes_bilingual_reports(tmp_path: Path) -> None:
    _source(tmp_path / "source")
    warehouse = tmp_path / "warehouse"
    minute = ingest_minute_archives(
        tmp_path / "source", warehouse, intervals=(1, 5, 15, 30, 60)
    )
    report = run_v10_platform(
        warehouse,
        minute_snapshot_id=str(minute["snapshot_id"]),
        feature_start=date(2024, 1, 1),
        feature_end=date(2024, 12, 31),
        candidate_budget=20,
        output_dir=tmp_path / "reports",
    )
    assert report.decision == "READY_FOR_BOUNDED_EMPIRICAL_COURT"
    assert len(report.candidate_packet.candidates) == 20
    assert report.inferential_trial_delta == 0
    assert (tmp_path / "reports" / "v10-platform.zh.md").is_file()
    assert (tmp_path / "reports" / "v10-platform.en.md").is_file()
