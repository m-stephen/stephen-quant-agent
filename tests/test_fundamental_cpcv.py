from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.workflows import run_fundamental_cpcv_research


def _weekdays(start: date, count: int) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _sources(root: Path, days: list[date]) -> tuple[Path, Path, list[str]]:
    daily, fundamental = root / "daily", root / "fundamental"
    daily.mkdir()
    fundamental.mkdir()
    instruments = [f"00000{index + 1}.SZ" for index in range(6)]
    previous = {item: 10.0 + index for index, item in enumerate(instruments)}
    for day_index, day in enumerate(days):
        with (daily / f"{day:%Y%m%d}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "日期",
                    "代码",
                    "名称",
                    "开盘价",
                    "最高价",
                    "最低价",
                    "收盘价",
                    "昨日收盘价",
                    "成交量(手)",
                    "成交额(千元)",
                    "复权因子",
                ]
            )
            for index, instrument in enumerate(instruments):
                opening = previous[instrument] * (1 + (index - 2.5) * 0.001)
                close = opening * (1 + ((day_index + index) % 3 - 1) * 0.001)
                writer.writerow(
                    [
                        day.strftime("%Y%m%d"),
                        instrument,
                        instrument,
                        opening,
                        max(opening, close),
                        min(opening, close),
                        close,
                        previous[instrument],
                        10000,
                        100000,
                        2,
                    ]
                )
                previous[instrument] = close
        with (fundamental / f"{day:%Y%m%d}.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "日期",
                    "代码",
                    "行业",
                    "总股本(亿)",
                    "每股净资产",
                    "每股收益",
                    "净利润率%",
                    "收入同比%",
                    "利润同比%",
                ]
            )
            for index, instrument in enumerate(instruments):
                writer.writerow(
                    [
                        day.strftime("%Y%m%d"),
                        instrument,
                        "行业A" if index < 3 else "行业B",
                        index + 1,
                        index + 5,
                        (index + 1) / 10,
                        index + 1,
                        5,
                        5,
                    ]
                )
    return daily, fundamental, instruments


def test_fundamental_cpcv_registers_six_trials_and_keeps_windows_sealed(tmp_path: Path) -> None:
    days = _weekdays(date(2023, 1, 2), 60)
    daily, fundamental, instruments = _sources(tmp_path, days)
    membership = tmp_path / "membership.jsonl"
    membership.write_text(
        "".join(
            json.dumps({"decision_date": day.isoformat(), "members": instruments}) + "\n"
            for day in days[2:]
        ),
        encoding="utf-8",
    )
    membership_sha = hashlib.sha256(membership.read_bytes()).hexdigest()
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "test-1.0.0",
                "research_window": {
                    "data_start": days[0].isoformat(),
                    "research_start": days[2].isoformat(),
                    "research_end": days[-1].isoformat(),
                    "validation_start": "2024-01-02",
                    "validation_end": "2024-12-31",
                    "test_start": "2025-01-02",
                    "test_end": "2025-12-31",
                },
                "universe": {"membership_sha256": membership_sha, "top_n": 6},
                "fundamentals": {
                    "confirmation_sessions": 2,
                    "warmup_sessions": 2,
                    "minimum_industry_members": 3,
                    "winsor_tail": 0.01,
                },
                "cpcv": {
                    "groups": 6,
                    "test_groups": 3,
                    "embargo_days": 1,
                    "purge": "closed_next_open_label_intervals",
                },
                "candidates": [
                    {
                        "candidate_id": "book",
                        "components": ["book_to_price"],
                        "weighting": "single",
                    },
                    {
                        "candidate_id": "earnings",
                        "components": ["earnings_yield"],
                        "weighting": "single",
                    },
                    {
                        "candidate_id": "profit",
                        "components": ["profitability"],
                        "weighting": "single",
                    },
                    {"candidate_id": "margin", "components": ["net_margin"], "weighting": "single"},
                    {
                        "candidate_id": "equal",
                        "components": [
                            "book_to_price",
                            "earnings_yield",
                            "profitability",
                            "net_margin",
                        ],
                        "weighting": "equal_rank",
                    },
                    {
                        "candidate_id": "trained",
                        "components": [
                            "book_to_price",
                            "earnings_yield",
                            "profitability",
                            "net_margin",
                        ],
                        "weighting": "fold_local_positive_rank_ic",
                    },
                ],
                "research_gates": {
                    "minimum_mean_path_rank_ic": 0.02,
                    "minimum_positive_paths": 8,
                    "maximum_pbo": 0.2,
                    "minimum_dsr_probability": 0.95,
                    "maximum_placebo_p_value": 0.05,
                },
            }
        ),
        encoding="utf-8",
    )
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")

    run = run_fundamental_cpcv_research(
        daily,
        fundamental,
        membership,
        manifest,
        registry=registry,
        output_dir=tmp_path / "output",
        code_version="test-sha",
    )

    assert registry.trial_count(run.report.experiment_id) == 6
    assert len(run.report.configurations) == 6
    assert run.report.evaluated_dates == len(days[2:]) - 2
    assert not run.report.validation_window_opened
    assert not run.report.execution_falsification_run
    assert run.json_path.exists() and run.markdown_zh_path.exists()
