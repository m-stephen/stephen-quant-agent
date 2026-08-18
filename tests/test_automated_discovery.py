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
    run_automated_discovery_suite,
)
from stephen_quant.workflows.automated_discovery import (
    _memberships_through,
    _trim_leading_warmup,
)


def test_dynamic_memberships_are_bounded_by_research_end() -> None:
    memberships = {
        "2022-12-30": ("000001.SZ",),
        "2023-01-03": ("601059.SH",),
        "2024-01-02": ("688001.SH",),
    }
    assert _memberships_through(memberships, "2022-12-30") == {
        "2022-12-30": ("000001.SZ",)
    }


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
        execution_budget=2,
        execution_top_k=2,
        placebo_repetitions=9,
        maximum_peer_rank_correlation=1.0,
        groups=6,
        test_groups=3,
        embargo_days=1,
        minimum_positive_paths=8,
        maximum_pbo=0.99,
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
    assert run.report.execution is None
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


def test_manifest_loader_normalizes_family_budgets(tmp_path: Path) -> None:
    sessions = _sessions()
    payload = {
        "manifest_version": "1.0.0",
        **_config(sessions).__dict__,
        "search_profile": "v1.8.17",
        "family_budgets": [["price_momentum", 1]],
    }
    payload["windows"] = list(payload["windows"])
    path = tmp_path / "manifest-v17.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_automated_discovery_config(path)

    assert loaded.family_budgets == (("price_momentum", 1),)


def test_multi_horizon_suite_uses_independent_experiments_and_global_ledger(
    tmp_path: Path,
) -> None:
    daily = tmp_path / "daily"
    sessions = _write_daily(daily)
    manifests = []
    for horizon in ("next_open", "5d"):
        payload = {
            "manifest_version": "1.0.0",
            **_config(sessions).__dict__, "horizon": horizon,
        }
        payload["windows"] = list(payload["windows"])
        path = tmp_path / f"{horizon}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        manifests.append(path.name)
    suite = tmp_path / "suite.json"
    suite.write_text(
        json.dumps(
            {
                "manifest_version": "1.0.0",
                "global_trial_budget": 20,
                "search_manifests": manifests,
            }
        ),
        encoding="utf-8",
    )
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    run = run_automated_discovery_suite(
        daily,
        ("000001.SZ", "000002.SZ", "600000.SH", "600001.SH"),
        registry=registry,
        output_dir=tmp_path / "suite-report",
        code_version="test-sha",
        suite_manifest=suite,
        ingested_at="2026-01-01T00:00:00+08:00",
    )
    assert len({item.experiment_id for item in run.report.runs}) == 2
    assert [item.horizon for item in run.report.runs] == ["next_open", "5d"]
    assert run.report.global_trial_count == 16
    assert run.report.frozen_suite_trial_budget == 20
    assert run.report.suite_trials_consumed == 16
    assert run.report.validation_window_opened is False
    assert run.report.test_window_opened is False
    assert run.json_path.is_file()


def test_warmup_trim_removes_only_leading_empty_dates() -> None:
    def row(day: str, eligible: bool) -> object:
        from stephen_quant.baseline import BaselineObservation

        return BaselineObservation(
            instrument="000001.SZ",
            signal=1.0,
            signal_at=f"{day}T00:00:00+08:00",
            signal_available_at=f"{day}T00:00:00+08:00",
            average_daily_value=1.0,
            liquidity_available_at=f"{day}T00:00:00+08:00",
            execution_at=f"{day}T09:30:00+08:00",
            return_end_at=f"{day}T10:00:00+08:00",
            forward_return=0.0,
            eligible=eligible,
        )

    rows = (row("2024-01-01", False), row("2024-01-02", True), row("2024-01-03", False))

    trimmed = _trim_leading_warmup(rows)

    assert [item.execution_at[:10] for item in trimmed] == ["2024-01-02", "2024-01-03"]
