from __future__ import annotations

from pathlib import Path

import pytest

from stephen_quant.qmt import QmtDataError, load_point_in_time_memberships

HEADER = "membership_kind,effective_at,available_at,instrument,group_id,group_name\n"


def test_point_in_time_industry_and_concept_membership_audit(tmp_path: Path) -> None:
    source = tmp_path / "membership.csv"
    source.write_text(
        HEADER
        + "industry,2024-01-02T15:00:00+08:00,2024-01-02T18:00:00+08:00,"
        "000001.SZ,801780,银行\n"
        + "concept,2024-01-02T15:00:00+08:00,2024-01-02T18:00:00+08:00,"
        "000001.SZ,C001,数字经济\n",
        encoding="utf-8",
    )
    rows, audit = load_point_in_time_memberships(
        source, ingested_at="2024-01-03T12:00:00+08:00"
    )
    assert len(rows) == 2
    assert audit.kinds == ("concept", "industry")
    assert audit.duplicate_keys == 0
    assert audit.timing_violations == 0
    assert len(audit.source_sha256) == 64


def test_point_in_time_membership_rejects_leakage_and_duplicates(tmp_path: Path) -> None:
    source = tmp_path / "membership.csv"
    row = (
        "concept,2024-01-02T15:00:00+08:00,2024-01-02T14:00:00+08:00,"
        "000001.SZ,C001,数字经济\n"
    )
    source.write_text(HEADER + row, encoding="utf-8")
    with pytest.raises(QmtDataError, match="available before effective"):
        load_point_in_time_memberships(
            source, ingested_at="2024-01-03T12:00:00+08:00"
        )

    valid = row.replace("14:00:00", "18:00:00")
    source.write_text(HEADER + valid + valid, encoding="utf-8")
    with pytest.raises(QmtDataError, match="duplicate"):
        load_point_in_time_memberships(
            source, ingested_at="2024-01-03T12:00:00+08:00"
        )
