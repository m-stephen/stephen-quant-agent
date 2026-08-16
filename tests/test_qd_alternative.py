from __future__ import annotations

import csv
from pathlib import Path

import pytest

from stephen_quant.qmt import (
    SOURCE_FIELDS,
    QdAlternativeConfig,
    QmtDataError,
    load_qd_alternative_directory,
)
from stephen_quant.research_agent import analyze_formula


def _write_source(path: Path, kind: str, *, row_date: str = "20240102") -> Path:
    path.mkdir()
    file_path = path / "20240102.csv"
    field_columns = [field.column for field in SOURCE_FIELDS[kind].values()]
    with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["日期", "代码", "名称", *field_columns])
        writer.writerow([row_date, "000001.SZ", "平安银行", *(["1"] * len(field_columns))])
    return file_path


@pytest.mark.parametrize(
    ("kind", "field", "expected", "effective_clock", "available_clock"),
    (
        ("fund_flow", "net_inflow_amount", 10_000.0, "15:00:00", "18:00:00"),
        ("auction", "auction_return", 0.01, "09:25:00", "09:26:00"),
        ("margin", "margin_financing_buy", 1.0, "15:00:00", "18:00:00"),
        ("industry", "industry_amount", 10_000.0, "15:00:00", "18:00:00"),
    ),
)
def test_alternative_adapters_normalize_units_and_timing(
    tmp_path: Path,
    kind: str,
    field: str,
    expected: float,
    effective_clock: str,
    available_clock: str,
) -> None:
    source = tmp_path / kind
    _write_source(source, kind)
    dataset = load_qd_alternative_directory(
        source,
        QdAlternativeConfig(
            source_kind=kind,
            start_date="2024-01-02",
            end_date="2024-01-02",
            ingested_at="2024-02-01T12:00:00+08:00",
        ),
    )
    row = dataset.observations[0]
    assert row.value(field) == expected
    assert row.effective_at == f"2024-01-02T{effective_clock}+08:00"
    assert row.available_at == f"2024-01-02T{available_clock}+08:00"
    assert dataset.audit.rows == 1
    assert dataset.audit.source_files == 1
    assert dataset.audit.source_sha256
    assert "user-declared" in dataset.audit.availability_policy


def test_alternative_adapter_rejects_schema_drift_partition_mismatch_and_bad_timing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing"
    file_path = _write_source(source, "auction")
    text = file_path.read_text(encoding="utf-8-sig")
    file_path.write_text(text.replace("集合竞价量比3", "未知字段"), encoding="utf-8-sig")
    config = QdAlternativeConfig(
        source_kind="auction",
        start_date="2024-01-02",
        end_date="2024-01-02",
        ingested_at="2024-02-01T12:00:00+08:00",
    )
    with pytest.raises(QmtDataError, match="missing alternative-data columns"):
        load_qd_alternative_directory(source, config)

    mismatch = tmp_path / "mismatch"
    _write_source(mismatch, "margin", row_date="20240103")
    with pytest.raises(QmtDataError, match="differs from partition"):
        load_qd_alternative_directory(
            mismatch,
            QdAlternativeConfig(
                source_kind="margin",
                start_date="2024-01-02",
                end_date="2024-01-02",
                ingested_at="2024-02-01T12:00:00+08:00",
            ),
        )

    timing = tmp_path / "timing"
    _write_source(timing, "fund_flow")
    with pytest.raises(QmtDataError, match="availability precedes"):
        load_qd_alternative_directory(
            timing,
            QdAlternativeConfig(
                source_kind="fund_flow",
                start_date="2024-01-02",
                end_date="2024-01-02",
                ingested_at="2024-02-01T12:00:00+08:00",
                effective_clock="15:00:00",
                available_clock="14:00:00",
            ),
        )


def test_safe_dsl_accepts_registered_alternative_fields() -> None:
    analysis = analyze_formula("mean(net_inflow_amount, 5) / mean(auction_amount, 5)")
    assert analysis.required_fields == ("auction_amount", "net_inflow_amount")
