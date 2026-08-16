from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from stephen_quant.integrity import ExperimentRegistry
from stephen_quant.workflows import run_dynamic_cpcv_research


def _weekdays(start: date, count: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _write_daily(root: Path, days: list[date]) -> None:
    instruments = ("000001.SZ", "000002.SZ", "600001.SH", "600002.SH")
    previous = {instrument: 10.0 + index for index, instrument in enumerate(instruments)}
    for day_index, day in enumerate(days):
        with (root / f"{day:%Y%m%d}.csv").open(
            "w", encoding="utf-8-sig", newline=""
        ) as handle:
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
            for instrument_index, instrument in enumerate(instruments):
                prior = previous[instrument]
                gap = (instrument_index - 1.5) * 0.002 + (day_index % 3 - 1) * 0.001
                opening = prior * (1 + gap)
                close = opening * (1 + (1.5 - instrument_index) * 0.001)
                writer.writerow(
                    [
                        f"{day:%Y%m%d}",
                        instrument,
                        instrument,
                        opening,
                        max(opening, close) + 0.1,
                        min(opening, close) - 0.1,
                        close,
                        prior,
                        100_000 + instrument_index * 1_000,
                        100_000 + instrument_index * 1_000,
                        1,
                    ]
                )
                previous[instrument] = close


def test_dynamic_cpcv_registers_four_trials_and_writes_bilingual_reports(
    tmp_path: Path,
) -> None:
    days = _weekdays(date(2023, 1, 2), 80)
    daily = tmp_path / "daily"
    daily.mkdir()
    _write_daily(daily, days)
    members = ["000001.SZ", "000002.SZ", "600001.SH", "600002.SH"]
    membership = tmp_path / "membership.jsonl"
    membership.write_text(
        "".join(
            json.dumps(
                {
                    "decision_date": day.isoformat(),
                    "decision_at": f"{day.isoformat()}T15:01:00+08:00",
                    "members": members,
                }
            )
            + "\n"
            for day in days[21:]
        ),
        encoding="utf-8",
    )
    membership_sha = hashlib.sha256(membership.read_bytes()).hexdigest()
    manifest = tmp_path / "candidates.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "test-candidates-1.0.0",
                "research_window": {
                    "data_start": days[0].isoformat(),
                    "research_start": days[21].isoformat(),
                    "research_end": days[-1].isoformat(),
                    "validation_start": "2024-01-02",
                    "validation_end": "2024-12-31",
                    "test_start": "2025-01-02",
                    "test_end": "2025-12-31",
                },
                "universe": {"membership_sha256": membership_sha, "top_n": 4},
                "cpcv": {
                    "groups": 6,
                    "test_groups": 3,
                    "embargo_days": 1,
                    "purge": "closed_next_open_label_intervals",
                },
                "candidates": [
                    {
                        "candidate_id": "gap",
                        "components": ["overnight_gap_reversal_20@1.0.0"],
                        "weighting": "single",
                    },
                    {
                        "candidate_id": "location",
                        "components": ["close_location_20@1.0.0"],
                        "weighting": "single",
                    },
                    {
                        "candidate_id": "equal",
                        "components": [
                            "overnight_gap_reversal_20@1.0.0",
                            "close_location_20@1.0.0",
                        ],
                        "weighting": "equal_rank",
                    },
                    {
                        "candidate_id": "trained",
                        "components": [
                            "overnight_gap_reversal_20@1.0.0",
                            "close_location_20@1.0.0",
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

    run = run_dynamic_cpcv_research(
        daily,
        membership,
        manifest,
        registry=registry,
        output_dir=tmp_path / "report",
        code_version="test-sha",
    )

    assert registry.trial_count(run.report.experiment_id) == 4
    assert len(run.report.configurations) == 4
    assert run.report.evaluated_dates == len(days[21:]) - 2
    assert run.report.common_observations == run.report.evaluated_dates * len(members)
    assert run.report.pbo.paths == 10
    assert not run.report.validation_window_opened
    assert not run.report.execution_falsification_run
    assert run.json_path.exists()
    assert "Candidate results" in run.markdown_en_path.read_text(encoding="utf-8")
    assert "候选结果" in run.markdown_zh_path.read_text(encoding="utf-8")
