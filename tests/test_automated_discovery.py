from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.workflows import (
    AutomatedDiscoveryConfig,
    load_automated_discovery_config,
    run_automated_discovery,
)


def _sessions(count: int = 100) -> list[date]:
    result: list[date] = []
    day = date(2024, 1, 2)
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return result


def _write_daily(root: Path) -> list[date]:
    root.mkdir()
    sessions = _sessions()
    growth = {
        "000001.SZ": 1.004,
        "000002.SZ": 1.003,
        "600000.SH": 1.002,
        "600001.SH": 1.001,
    }
    for index, day in enumerate(sessions):
        with (root / f"{day:%Y%m%d}.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "日期",
                    "代码",
                    "开盘价",
                    "最高价",
                    "最低价",
                    "收盘价",
                    "成交量(手)",
                    "成交额(千元)",
                    "复权因子",
                ]
            )
            for instrument, rate in growth.items():
                value = 10 * rate**index
                writer.writerow(
                    [
                        f"{day:%Y%m%d}",
                        instrument,
                        value,
                        value * 1.01,
                        value * 0.99,
                        value,
                        100_000,
                        100_000,
                        1.0,
                    ]
                )
    return sessions


def _config(sessions: list[date]) -> AutomatedDiscoveryConfig:
    return AutomatedDiscoveryConfig(
        data_start=sessions[0].isoformat(),
        research_start=sessions[25].isoformat(),
        research_end=sessions[-1].isoformat(),
        validation_start="2025-01-02",
        validation_end="2025-12-31",
        test_start="2026-01-02",
        test_end="2026-12-31",
        horizon="5d",
        windows=(2, 3),
        schema_budget=6,
        cpcv_budget=2,
        execution_budget=1,
        maximum_peer_rank_correlation=1.0,
        groups=6,
        test_groups=3,
        embargo_days=1,
        minimum_positive_paths=8,
        maximum_pbo=1.0,
    )


def test_automated_discovery_runs_generation_screen_cpcv_and_bilingual_reports(
    tmp_path: Path,
) -> None:
    daily = tmp_path / "daily"
    sessions = _write_daily(daily)
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    run = run_automated_discovery(
        daily,
        ("000001.SZ", "000002.SZ", "600000.SH", "600001.SH"),
        registry=registry,
        output_dir=tmp_path / "report",
        code_version="test-sha",
        config=_config(sessions),
    )
    assert run.report.generated_candidates == 6
    assert run.report.unique_candidates == 6
    assert run.report.cpcv is not None
    assert run.report.validation_window_opened is False
    assert run.report.test_window_opened is False
    assert registry.trial_count(run.report.experiment_id) == 8
    assert run.json_path.is_file()
    assert run.schemas_path.is_file()
    assert "Automated Factor Discovery" in run.markdown_en_path.read_text(encoding="utf-8")
    assert "自动因子发现" in run.markdown_zh_path.read_text(encoding="utf-8")


def test_manifest_loader_is_strict_and_normalizes_windows(tmp_path: Path) -> None:
    sessions = _sessions()
    payload = {"manifest_version": "1.0.0", **_config(sessions).__dict__}
    payload["windows"] = [2, 3]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_automated_discovery_config(path)
    assert loaded.windows == (2, 3)

    payload["unknown"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_automated_discovery_config(path)
    except ValueError as exc:
        assert "fields are invalid" in str(exc)
    else:
        raise AssertionError("unknown manifest field was accepted")
