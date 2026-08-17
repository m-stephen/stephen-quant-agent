from __future__ import annotations

import csv
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import FactorSchema
from stephen_quant.qmt import (
    SOURCE_FIELDS,
    AlternativeObservation,
    QdAlternativeConfig,
    QmtDataError,
    build_alternative_factor_observations,
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
        ("chip", "chip_win_rate", 0.01, "15:00:00", "18:00:00"),
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


def test_limit_event_adapter_densifies_absence_and_aggregates_duplicates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "limit-event"
    source.mkdir()
    file_path = source / "20240102.csv"
    headers = [
        "日期",
        "代码",
        "名称",
        "标签",
        "主力净额(元)",
        "收盘封单额",
        "成交额",
        "实际流通市值",
        "日内最大封单额",
    ]
    with file_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerow([20240102, "000001.SZ", "平安银行", "涨停", 10, 20, 30, 40, 50])
        writer.writerow([20240102, "000001.SZ", "平安银行", "涨停", -15, 25, 35, 45, 55])
        writer.writerow([20240102, "000002.SZ", "万科A", "跌停", -10, "", 30, 40, 50])
    dataset = load_qd_alternative_directory(
        source,
        QdAlternativeConfig(
            source_kind="limit_event",
            start_date="2024-01-02",
            end_date="2024-01-02",
            ingested_at="2024-02-01T12:00:00+08:00",
            instruments=("000001.SZ", "000002.SZ", "600000.SH"),
        ),
    )
    assert len(dataset.observations) == 3
    by_instrument = {row.instrument: row for row in dataset.observations}
    assert by_instrument["000001.SZ"].value("kpl_limit_up_flag") == 1.0
    assert by_instrument["000001.SZ"].value("kpl_main_net_amount") == -15.0
    assert by_instrument["000001.SZ"].value("kpl_close_seal_amount") == 25.0
    assert by_instrument["000002.SZ"].value("kpl_limit_up_flag") == 0.0
    assert by_instrument["600000.SH"].value("kpl_turnover_amount") == 0.0
    assert dataset.audit.start_date == "2024-01-02"
    assert any("Duplicate event rows" in item for item in dataset.audit.warnings)


def test_alternative_factor_uses_only_values_available_before_execution() -> None:
    source = tuple(
        AlternativeObservation(
            source_kind="auction",
            instrument="000001.SZ",
            name="sample",
            trade_date=f"2024-01-0{day}",
            effective_at=f"2024-01-0{day}T09:25:00+08:00",
            available_at=f"2024-01-0{day}T09:26:00+08:00",
            ingested_at="2024-02-01T12:00:00+08:00",
            values=(("auction_return", float(day)),),
        )
        for day in (2, 3, 4)
    )
    anchors = tuple(
        BaselineObservation(
            instrument="000001.SZ",
            signal=0.0,
            signal_at=f"2024-01-0{day - 1}T15:00:00+08:00",
            signal_available_at=f"2024-01-0{day - 1}T15:01:00+08:00",
            average_daily_value=1_000_000.0,
            liquidity_available_at=f"2024-01-0{day - 1}T15:01:00+08:00",
            execution_at=f"2024-01-0{day}T09:30:00+08:00",
            return_end_at=f"2024-01-0{day + 1}T09:30:00+08:00",
            forward_return=0.01,
        )
        for day in (3, 4, 5)
    )
    schema = FactorSchema(
        schema_id="auction_mean_2",
        version="1.0.0",
        name="Auction mean",
        event="auction",
        context="pre_open",
        quality="point_in_time",
        direction=1,
        output="score",
        horizon="1d",
        formula="mean(auction_return, 2)",
        data_sources=("qd_auction",),
        required_fields=("auction_return",),
        availability_lag_days=0,
        economic_rationale="Opening auction demand.",
    )
    rows = build_alternative_factor_observations(source, schema.compile(), anchors)
    assert [row.signal for row in rows] == [2.5, 3.5, 0.0]
    assert rows[0].signal_available_at == "2024-01-03T09:26:00+08:00"
    assert rows[0].signal_available_at < rows[0].execution_at
    assert rows[-1].eligible is False


def test_alternative_factor_preserves_uncovered_assets_for_liquidation() -> None:
    source = (
        AlternativeObservation(
            source_kind="auction",
            instrument="000001.SZ",
            name="sample",
            trade_date="2024-01-03",
            effective_at="2024-01-03T09:25:00+08:00",
            available_at="2024-01-03T09:26:00+08:00",
            ingested_at="2024-02-01T12:00:00+08:00",
            values=(("auction_return", 1.0),),
        ),
    )
    anchor = BaselineObservation(
        instrument="603985.SH",
        signal=0.0,
        signal_at="2024-01-02T15:00:00+08:00",
        signal_available_at="2024-01-02T15:01:00+08:00",
        average_daily_value=1_000_000.0,
        liquidity_available_at="2024-01-02T15:01:00+08:00",
        execution_at="2024-01-03T09:30:00+08:00",
        return_end_at="2024-01-04T09:30:00+08:00",
        forward_return=0.01,
    )
    schema = FactorSchema(
        schema_id="auction_mean_1",
        version="1.0.0",
        name="Auction mean",
        event="auction",
        context="pre_open",
        quality="point_in_time",
        direction=1,
        output="score",
        horizon="1d",
        formula="mean(auction_return, 1)",
        data_sources=("qd_auction",),
        required_fields=("auction_return",),
        availability_lag_days=0,
        economic_rationale="Opening auction demand.",
    )
    rows = build_alternative_factor_observations(source, schema.compile(), (anchor,))
    assert len(rows) == 1
    assert rows[0].instrument == "603985.SH"
    assert rows[0].signal == 0.0
    assert rows[0].eligible is False
