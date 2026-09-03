from __future__ import annotations

import hashlib
import json
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest

from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.sw_industry_warehouse import (
    fetch_sw_l2_url,
    ingest_sw_l2_file,
    verify_sw_l2_snapshot,
    write_sw_l2_reports,
)


def _payload(*, duplicate: bool = False, label_mismatch: bool = False) -> dict[str, object]:
    stock_2021 = {"code": "000001.SZ", "name": "平安银行"}
    stocks_2021 = [stock_2021, dict(stock_2021)] if duplicate else [stock_2021]
    return {
        "meta": {
            "title": "申万二级年度快照",
            "source": "test fixture",
            "generated_years": [2020, 2021, 2025],
            "snapshot_labels": {
                "2020": "2020-12-31",
                "2021": "2021-12-30" if label_mismatch else "2021-12-31",
                "2025": "2025-12-31",
            },
            "note": "annual snapshots only",
        },
        "years": [
            {
                "year": 2020,
                "as_of": "2020-12-31",
                "industry_count": 1,
                "stock_total": 1,
                "industries": [
                    {
                        "code": "801780",
                        "name": "银行",
                        "count": 1,
                        "stocks": [{"code": "000001.SZ", "name": "平安银行"}],
                    }
                ],
            },
            {
                "year": 2021,
                "as_of": "2021-12-31",
                "industry_count": 1,
                "stock_total": len(stocks_2021),
                "industries": [
                    {
                        "code": "801780",
                        "name": "银行",
                        "count": len(stocks_2021),
                        "stocks": stocks_2021,
                    }
                ],
            },
            {
                "year": 2025,
                "as_of": "2025-12-31",
                "industry_count": 1,
                "stock_total": 1,
                "industries": [
                    {
                        "code": "801790",
                        "name": "非银金融",
                        "count": 1,
                        "stocks": [{"code": "000001.SZ", "name": "平安银行"}],
                    }
                ],
            },
        ],
        "industry_changes": [],
        "stock_changes": [],
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_ingest_verify_replay_and_reports(tmp_path: Path) -> None:
    source = tmp_path / "sw_l2_history.json"
    warehouse = tmp_path / "warehouse"
    _write(source, _payload())

    first = ingest_sw_l2_file(warehouse, source)
    assert first.status == "COMPLETED"
    assert first.row_count == 3
    assert first.change_count == 1
    assert [item.coverage_grade for item in first.year_quality] == [
        "PARTIAL",
        "PIT_LITE_B",
        "PIT_LITE_B",
    ]
    assert [item.sealed for item in first.year_quality] == [False, False, True]
    assert verify_sw_l2_snapshot(warehouse, first.snapshot_id)["passed"] is True

    connection = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        assert connection.execute("SELECT count(*) FROM qd_sw_l2_membership_current").fetchone()[0] == 3
        assert connection.execute(
            "SELECT industry_code FROM qd_sw_l2_membership_current "
            "WHERE snapshot_year=2025 AND instrument='000001.SZ'"
        ).fetchone()[0] == "801790"
        assert connection.execute(
            "SELECT count(*) FROM sw_l2_changes WHERE change_type='RECLASSIFIED'"
        ).fetchone()[0] == 1
    finally:
        connection.close()

    reports = write_sw_l2_reports(first, tmp_path / "reports")
    assert Path(reports["json"]).is_file()
    assert "PIT-Lite" in Path(reports["zh"]).read_text(encoding="utf-8")
    assert "Formal research eligible: no" in Path(reports["en"]).read_text(encoding="utf-8")

    replay = ingest_sw_l2_file(warehouse, source)
    assert replay.status == "REPLAY_NOOP"
    assert replay.snapshot_id == first.snapshot_id


def test_rejects_duplicate_assignment_and_label_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "sw.json"
    warehouse = tmp_path / "warehouse"
    _write(source, _payload(duplicate=True))
    with pytest.raises(QmtDataError, match="duplicate stock assignment"):
        ingest_sw_l2_file(warehouse, source)

    _write(source, _payload(label_mismatch=True))
    with pytest.raises(QmtDataError, match="snapshot label mismatch"):
        ingest_sw_l2_file(warehouse, source)


def test_snapshot_verifier_detects_source_tampering(tmp_path: Path) -> None:
    source = tmp_path / "sw.json"
    warehouse = tmp_path / "warehouse"
    _write(source, _payload())
    result = ingest_sw_l2_file(warehouse, source)
    cached = warehouse / "sw-l2-sources" / f"{result.source_sha256}.json"
    cached.write_bytes(b"tampered")

    verification = verify_sw_l2_snapshot(warehouse, result.snapshot_id)
    assert verification["passed"] is False
    assert "Shenwan source cache integrity mismatch" in verification["failures"]


def test_snapshot_id_is_bound_to_normalized_content(tmp_path: Path) -> None:
    source = tmp_path / "sw.json"
    _write(source, _payload())
    first = ingest_sw_l2_file(tmp_path / "warehouse-a", source)
    second = ingest_sw_l2_file(tmp_path / "warehouse-b", source)
    assert first.snapshot_id == second.snapshot_id
    assert len(first.snapshot_id) == 64
    assert hashlib.sha256(source.read_bytes()).hexdigest() == first.source_sha256


class _Response:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"
        self.headers["Content-Length"] = str(len(raw))

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.raw[:limit]


def test_http_fetch_ingests_without_persisting_url(tmp_path: Path) -> None:
    raw = json.dumps(_payload(), ensure_ascii=False).encode("utf-8")
    warehouse = tmp_path / "warehouse"
    with patch("urllib.request.urlopen", return_value=_Response(raw)):
        result = fetch_sw_l2_url(warehouse, "https://example.invalid/sw_l2_history.json")
    assert result.status == "COMPLETED"

    connection = duckdb.connect(str(warehouse / "catalog" / "warehouse.duckdb"), read_only=True)
    try:
        locator_hash = connection.execute(
            "SELECT source_locator_sha256 FROM sw_l2_batches"
        ).fetchone()[0]
    finally:
        connection.close()
    assert locator_hash == hashlib.sha256(
        b"https://example.invalid/sw_l2_history.json"
    ).hexdigest()
    assert "example.invalid" not in (warehouse / "sw-l2-snapshots" / f"{result.snapshot_id}.json").read_text(encoding="utf-8")


def test_http_fetch_rejects_oversize_response(tmp_path: Path) -> None:
    raw = json.dumps(_payload(), ensure_ascii=False).encode("utf-8")
    with (
        patch("urllib.request.urlopen", return_value=_Response(raw)),
        pytest.raises(QmtDataError, match="byte limit"),
    ):
        fetch_sw_l2_url(
            tmp_path / "warehouse",
            "https://example.invalid/sw_l2_history.json",
            max_bytes=10,
        )
