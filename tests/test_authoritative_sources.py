from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stephen_quant.qmt.authoritative_sources import build_authoritative_source_bundle
from stephen_quant.qmt.models import QmtDataError


def _write_config(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    exchange = source / "exchange.pdf"
    industry_document = source / "industry.csv"
    exchange.write_bytes(b"%PDF-exchange-evidence")
    industry_document.write_bytes(b"code,industry,effective_from\n000001.SZ,bank,2022-01-01\n")
    industry = source / "industry.jsonl"
    industry.write_text(json.dumps({
        "code": "000001.SZ", "industry_system": "SW2021", "industry_level": "L1",
        "industry_code": "801780", "industry_name": "Bank", "effective_from": "2022-01-01",
        "effective_to": None, "source": "licensed_industry_source", "revision_id": "i-r1",
        "source_document_id": "industry-1", "classification_version": "SW2021",
        "announcement_at": "2021-12-20T18:00:00+08:00",
        "available_at": "2021-12-20T18:00:00+08:00",
    }) + "\n", encoding="utf-8")
    corporate = source / "corporate.jsonl"
    corporate.write_text(json.dumps({
        "code": "000001.SZ", "event_type": "cash_dividend",
        "announcement_at": "2023-05-01T18:00:00+08:00",
        "available_at": "2023-05-01T18:00:00+08:00", "effective_date": "2023-06-01",
        "record_date": "2023-05-30", "ex_date": "2023-05-31", "revision_id": "c-r1",
        "source_document_id": "exchange-1", "cash_dividend_per_share": "0.10",
    }) + "\n", encoding="utf-8")
    transient_hash = hashlib.sha256(b"provider-id").hexdigest()
    config = tmp_path / "sources.local.json"
    config.write_text(json.dumps({
        "operation_id": "operation-1", "output_dir": str(tmp_path / "output"),
        "document_files": {"exchange-1": str(exchange), "industry-1": str(industry_document)},
        "source_types": {"exchange-1": "szse_announcement",
                         "industry-1": "licensed_industry_source"},
        "announcement_document_links": {transient_hash: "exchange-1"},
        "industry_records": str(industry), "corporate_action_records": str(corporate),
    }), encoding="utf-8")
    return config


def test_builds_immutable_source_bound_candidate(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    result = build_authoritative_source_bundle(config)
    assert result.industry_rows == result.corporate_action_rows == result.announcement_links == 1
    manifest = json.loads((result.output_dir / "authoritative-source-manifest.json").read_text())
    assert manifest["formal_research_eligible"] is False
    assert manifest["inferential_trial_delta"] == 0
    assert len(manifest["files"]) == 4
    links = json.loads((result.output_dir / "announcement-document-links.json").read_text())
    assert next(iter(links.values()))["source_hash"] == hashlib.sha256(
        b"%PDF-exchange-evidence"
    ).hexdigest()
    with pytest.raises(FileExistsError):
        build_authoritative_source_bundle(config)


def test_rejects_unverified_document_hash_and_link(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    payload = json.loads(config.read_text())
    corporate = Path(payload["corporate_action_records"])
    row = json.loads(corporate.read_text())
    row["source_hash"] = "a" * 64
    corporate.write_text(json.dumps(row) + "\n")
    with pytest.raises(QmtDataError, match="does not match"):
        build_authoritative_source_bundle(config)
    row.pop("source_hash")
    corporate.write_text(json.dumps(row) + "\n")
    payload["announcement_document_links"] = {hashlib.sha256(b"id").hexdigest(): "industry-1"}
    config.write_text(json.dumps(payload))
    with pytest.raises(QmtDataError, match="exchange document"):
        build_authoritative_source_bundle(config)


def test_rejects_missing_provenance_bad_identity_and_source_output_overlap(tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    payload = json.loads(config.read_text())
    corporate = Path(payload["corporate_action_records"])
    row = json.loads(corporate.read_text())
    row["source_document_id"] = "missing"
    corporate.write_text(json.dumps(row) + "\n")
    with pytest.raises(QmtDataError, match="no verified"):
        build_authoritative_source_bundle(config)
    row["source_document_id"] = "exchange-1"
    corporate.write_text(json.dumps(row) + "\n")
    payload["announcement_document_links"] = {"raw-provider-id": "exchange-1"}
    config.write_text(json.dumps(payload))
    with pytest.raises(QmtDataError, match="64 hexadecimal"):
        build_authoritative_source_bundle(config)
    payload["announcement_document_links"] = {}
    payload["output_dir"] = str(corporate.parent / "generated")
    config.write_text(json.dumps(payload))
    with pytest.raises(QmtDataError, match="physically disjoint"):
        build_authoritative_source_bundle(config)
