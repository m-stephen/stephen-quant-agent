from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.qmt import (
    QmtDataError,
    load_qd_confirmed_fundamentals,
    read_dynamic_memberships,
    write_qd_fundamental_dataset,
)


def _write_snapshot(
    root: Path,
    day: date,
    *,
    book_value: str,
    earnings: str = "1.2",
    include_second: bool = True,
) -> None:
    with (root / f"{day:%Y%m%d}.csv").open(
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
        writer.writerow(
            [day.strftime("%Y%m%d"), "000001.SZ", "银行", 10, book_value, earnings, 20, 8, 6]
        )
        if include_second:
            writer.writerow(
                [day.strftime("%Y%m%d"), "000002.SZ", "地产", 20, 5, 0.4, 10, -2, -5]
            )


def test_confirmed_fundamentals_hold_old_value_during_transition(tmp_path: Path) -> None:
    start = date(2024, 1, 2)
    days = [start + timedelta(days=index) for index in range(4)]
    _write_snapshot(tmp_path, days[0], book_value="10")
    _write_snapshot(tmp_path, days[1], book_value="10")
    _write_snapshot(tmp_path, days[2], book_value="12")
    _write_snapshot(tmp_path, days[3], book_value="12")
    memberships = {
        days[2].isoformat(): ("000001.SZ", "000002.SZ"),
        days[3].isoformat(): ("000001.SZ", "000002.SZ"),
    }

    dataset = load_qd_confirmed_fundamentals(
        tmp_path, memberships, confirmation_sessions=2, warmup_sessions=2
    )

    first, _, second, _ = dataset.observations
    assert first.book_value_per_share == 10.0
    assert second.book_value_per_share == 12.0
    assert first.total_shares == 1_000_000_000
    assert first.available_at.endswith("T15:01:00+08:00")
    assert dataset.audit.source_files == 4
    assert dataset.audit.requested_member_rows == 4
    assert dataset.audit.field_coverage["book_value_per_share"] == 1.0
    assert dataset.audit.withheld_transition_cells["book_value_per_share"] == 1
    assert dataset.audit.nonpositive_confirmed_cells["book_value_per_share"] == 0
    assert dataset.audit.numeric_ranges["book_value_per_share"] == {
        "minimum": 5.0,
        "maximum": 12.0,
    }
    assert dataset.audit.source_snapshot_sha256


def test_fundamental_adapter_reports_missing_rows_and_invalid_cells(tmp_path: Path) -> None:
    start = date(2024, 1, 2)
    days = [start + timedelta(days=index) for index in range(3)]
    _write_snapshot(tmp_path, days[0], book_value="bad")
    _write_snapshot(tmp_path, days[1], book_value="bad")
    _write_snapshot(tmp_path, days[2], book_value="bad", include_second=False)

    dataset = load_qd_confirmed_fundamentals(
        tmp_path,
        {days[2].isoformat(): ("000001.SZ", "000002.SZ")},
        confirmation_sessions=2,
        warmup_sessions=2,
    )

    assert dataset.audit.invalid_numeric_cells["book_value_per_share"] == 3
    assert dataset.audit.missing_member_rows == 1
    assert dataset.audit.emitted_rows == 1
    assert dataset.observations[0].book_value_per_share is None


def test_membership_reader_and_artifact_writer(tmp_path: Path) -> None:
    membership = tmp_path / "membership.jsonl"
    membership.write_text(
        json.dumps({"decision_date": "2024-01-02", "members": ["000002.sz", "000001.SZ"]})
        + "\n",
        encoding="utf-8",
    )
    memberships = read_dynamic_memberships(membership)
    source = tmp_path / "source"
    source.mkdir()
    day = date(2024, 1, 2)
    _write_snapshot(source, day, book_value="10")
    dataset = load_qd_confirmed_fundamentals(
        source, memberships, confirmation_sessions=1, warmup_sessions=1
    )

    audit_path, observations_path, audit_sha, observations_sha = (
        write_qd_fundamental_dataset(dataset, tmp_path / "output")
    )

    assert memberships["2024-01-02"] == ("000001.SZ", "000002.SZ")
    assert audit_path.exists() and observations_path.exists()
    assert len(audit_sha) == len(observations_sha) == 64


def test_fundamental_adapter_rejects_missing_same_day_snapshot(tmp_path: Path) -> None:
    day = date(2024, 1, 2)
    _write_snapshot(tmp_path, day, book_value="10")

    with pytest.raises(QmtDataError, match="missing exact same-day"):
        load_qd_confirmed_fundamentals(
            tmp_path,
            {"2024-01-03": ("000001.SZ",)},
            confirmation_sessions=1,
            warmup_sessions=1,
        )
