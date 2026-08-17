from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.pit_staging import (
    CorporateActionPIT,
    FinancialVisibility,
    IndustryMembershipPIT,
    alphapai_missing_credentials_ledger,
    audit_pit_staging,
    build_pit_market_cap,
    default_staging_contract,
    ingest_alphapai_announcement_pages,
    ingest_alphapai_announcement_partitions,
    ingest_alphapai_announcement_response,
    validate_corporate_actions,
    validate_financial_visibility,
    validate_industry_memberships,
    visible_financial_revision,
    visible_industry_membership,
    write_pit_bundle,
    write_pit_staging_contract,
)


def _financial(revision: str = "r1", publish: str = "2025-04-30T18:00:00+08:00") -> FinancialVisibility:
    return FinancialVisibility(
        code="000001.SZ", report_period="2025-03-31", report_type="quarterly_report",
        announcement_time="2025-04-30T17:00:00+08:00", actual_publish_time=publish,
        revision_id=revision, source_document_id=f"document-{revision}", source_hash="a" * 64,
    )


def _industry(start: str, end: str | None, code: str = "801780") -> IndustryMembershipPIT:
    return IndustryMembershipPIT(
        code="000001.SZ", industry_system="SW2021", industry_level="L1",
        industry_code=code, industry_name="Bank", effective_from=start,
        effective_to=end, source="constituent-change-document",
    )


def test_financial_visibility_respects_publish_boundary_and_revision_chain() -> None:
    first = _financial()
    revised = replace(
        _financial("r2", "2025-05-02T18:00:00+08:00"),
        announcement_time="2025-05-02T17:00:00+08:00", source_hash="b" * 64,
        supersedes_revision_id="r1",
    )
    rows = validate_financial_visibility((revised, first))
    assert rows == (first, revised)
    assert visible_financial_revision(
        rows, code="000001.SZ", report_period="2025-03-31",
        report_type="quarterly_report", as_of="2025-04-30T17:59:59+08:00",
    ) is None
    assert visible_financial_revision(
        rows, code="000001.SZ", report_period="2025-03-31",
        report_type="quarterly_report", as_of="2025-05-01T00:00:00+08:00",
    ) == first
    assert visible_financial_revision(
        rows, code="000001.SZ", report_period="2025-03-31",
        report_type="quarterly_report", as_of="2025-05-03T00:00:00+08:00",
    ) == revised


def test_financial_visibility_rejects_invalid_timing_and_duplicate_revision() -> None:
    row = _financial()
    with pytest.raises(QmtDataError, match="timezone"):
        validate_financial_visibility((replace(
            row, actual_publish_time="2025-04-30T16:00:00"
        ),))
    with pytest.raises(QmtDataError, match="duplicate"):
        validate_financial_visibility((row, row))
    with pytest.raises(QmtDataError, match="report period"):
        validate_financial_visibility((replace(row, report_period="2025-05-01"),))
    forecast = replace(
        row, report_period="2025-06-30", source_type="earnings_forecast",
        effective_at="2025-04-30T18:00:00+08:00",
    )
    assert validate_financial_visibility((forecast,)) == (forecast,)
    with pytest.raises(QmtDataError, match="revision chain"):
        validate_financial_visibility((row, replace(
            _financial("r2", "2025-05-02T18:00:00+08:00"), source_hash="b" * 64
        )))


def test_industry_membership_intervals_are_non_overlapping() -> None:
    rows = validate_industry_memberships((
        _industry("2025-01-01", "2025-06-01"),
        _industry("2025-06-01", None, "801790"),
    ))
    assert len(rows) == 2
    with pytest.raises(QmtDataError, match="overlapping"):
        validate_industry_memberships((
            _industry("2025-01-01", "2025-07-01"),
            _industry("2025-06-01", None, "801790"),
        ))


def test_industry_membership_is_not_visible_before_announcement() -> None:
    row = replace(
        _industry("2025-06-01", None),
        announcement_at="2025-05-20T18:00:00+08:00",
        available_at="2025-05-20T18:00:00+08:00",
        revision_id="industry-r1", source_document_id="industry-document",
        source_hash="c" * 64, classification_version="SW2021-2025",
    )
    assert visible_industry_membership(
        (row,), code="000001.SZ", industry_system="SW2021", industry_level="L1",
        as_of="2025-05-31T23:59:59+08:00",
    ) is None
    assert visible_industry_membership(
        (row,), code="000001.SZ", industry_system="SW2021", industry_level="L1",
        as_of="2025-06-01T00:00:00+08:00",
    ) == row


def test_corporate_action_revision_and_market_cap_boundaries() -> None:
    action = CorporateActionPIT(
        code="000001.SZ", event_type="share_change",
        announcement_at="2025-04-10T18:00:00+08:00",
        available_at="2025-04-10T18:00:00+08:00", effective_date="2025-04-20",
        revision_id="ca-r1", source_document_id="ca-document", source_hash="d" * 64,
        total_shares_after="1000",
    )
    assert validate_corporate_actions((action,)) == (action,)
    with pytest.raises(QmtDataError, match="not visible"):
        build_pit_market_cap(
            code="000001.SZ", decision_at="2025-04-09T15:00:00+08:00", shares="1000",
            share_type="total", share_unit="share", price="10.50", price_currency="CNY",
            shares_revision_id="ca-r1", shares_available_at=action.available_at,
            price_available_at="2025-04-09T15:00:00+08:00", source_hash="e" * 64,
        )
    result = build_pit_market_cap(
        code="000001.SZ", decision_at="2025-04-21T15:00:00+08:00", shares="1000",
        share_type="total", share_unit="share", price="10.50", price_currency="CNY",
        shares_revision_id="ca-r1", shares_available_at=action.available_at,
        price_available_at="2025-04-21T15:00:00+08:00", source_hash="e" * 64,
    )
    assert result.market_cap == "10500.00"


def test_default_contract_has_safe_a_b_c_admission_and_no_promotion() -> None:
    contract = default_staging_contract()
    admissions = {(row.layer, row.classification): row for row in contract.admissions}
    assert admissions[("daily_bars", "A")].formal_alpha_allowed is True
    assert admissions[("fundamental_snapshot", "B")].formal_alpha_allowed is False
    assert admissions[("attention_candidate", "C")].formal_alpha_allowed is False
    assert contract.formal_research_eligible is False
    assert audit_pit_staging(
        (_financial(),), (_industry("2025-01-01", None),), contract
    ).gate_pass is True


def test_leakage_audit_fails_closed_for_c_admission_and_interval_overlap() -> None:
    contract = default_staging_contract()
    unsafe = replace(contract, admissions=tuple(
        replace(row, formal_alpha_allowed=True) if row.classification == "C" else row
        for row in contract.admissions
    ))
    audit = audit_pit_staging((_financial(),), (
        _industry("2025-01-01", "2025-07-01"),
        _industry("2025-06-01", None, "801790"),
    ), unsafe)
    assert audit.gate_pass is False
    assert audit.industry_interval_overlaps == 1
    assert audit.c_fields_formally_admitted == 2


def test_missing_alphapai_credentials_are_recorded_without_fabrication() -> None:
    ledger = alphapai_missing_credentials_ledger("2025-01-01", "2026-08-17")
    assert ledger.status == "not_run_missing_credentials"
    assert ledger.documents_received == 0
    assert ledger.inferential_trial_delta == 0
    assert "fabricated" in ledger.note


def test_alphapai_periodic_metadata_builds_stable_visibility_without_encrypted_id() -> None:
    response = {
        "code": 200000,
        "message": "success",
        "data": {
            "pageNum": 1,
            "pageSize": 2,
            "totalPageNum": 1,
            "totalSize": 2,
            "data": [
                {
                    "announcementId": "transient-secret-id",
                    "title": "Example 2025 first-quarter report",
                    "publishTime": "2025-04-30 18:00:00",
                    "actualPublishTime": "2025-04-30 17:59:00",
                    "endDate": "2025-03-31 00:00:00",
                    "announcementType": "季度报告",
                    "announcementTypeCode": "periodic-quarterly",
                    "market": "A",
                    "stockTag": [{"code": "000001.SZ", "name": "Example"}],
                    "industryTag": [],
                    "hasPdf": True,
                },
                {
                    "announcementId": "ignored-id",
                    "title": "Daily operation notice",
                    "publishTime": "2025-04-30 18:00:00",
                    "actualPublishTime": "2025-04-30 18:00:00",
                    "endDate": "2025-04-30 00:00:00",
                    "announcementType": "日常经营其他",
                    "stockTag": [{"code": "000001.SZ", "name": "Example"}],
                },
            ],
        },
    }
    rows, ledger = ingest_alphapai_announcement_response(
        response, query_start="2025-01-01", query_end="2025-12-31"
    )
    assert len(rows) == 1
    assert rows[0].code == "000001.SZ"
    assert rows[0].actual_publish_time.endswith("+08:00")
    assert "transient-secret-id" not in json.dumps(rows[0].__dict__)
    assert len(rows[0].source_document_id) == 64
    assert ledger.status == "success"
    assert ledger.documents_received == 1
    assert ledger.inferential_trial_delta == 0


def test_alphapai_pagination_fails_closed_and_bundle_replays(tmp_path: Path) -> None:
    item = {
        "announcementId": "transient-id", "title": "Example annual report",
        "publishTime": "2025-04-30 18:00:00", "actualPublishTime": "2025-04-30 18:00:00",
        "endDate": "2024-12-31 00:00:00", "announcementType": "年度报告",
        "announcementTypeCode": "annual", "market": "A",
        "stockTag": [{"code": "000001.SZ", "name": "Example"}], "industryTag": [],
        "hasPdf": True,
    }
    page = lambda number, data, total=2: {
        "code": 200000, "data": {"pageNum": number, "pageSize": 1,
                                  "totalPageNum": 2, "totalSize": total, "data": data}
    }
    with pytest.raises(QmtDataError, match="incomplete"):
        ingest_alphapai_announcement_pages(
            (page(1, [item]),), query_start="2025-01-01", query_end="2025-12-31"
        )
    changed_total = page(2, [])
    changed_total["data"]["totalSize"] = 3
    with pytest.raises(QmtDataError, match="total changed"):
        ingest_alphapai_announcement_pages(
            (page(1, [item]), changed_total),
            query_start="2025-01-01", query_end="2025-12-31",
        )
    second_item = dict(item)
    second_item["title"] = "Second example annual report"
    second_item["stockTag"] = [{"code": "000002.SZ", "name": "Second"}]
    rows, ledger = ingest_alphapai_announcement_pages(
        (page(2, [second_item]), page(1, [item])),
        query_start="2025-01-01", query_end="2025-12-31",
        ingested_at="2026-08-17T21:30:00+08:00",
    )
    assert len(rows) == ledger.documents_received == 2
    partition_rows, _ = ingest_alphapai_announcement_partitions(
        ((page(1, [item]), page(2, [second_item])),),
        query_start="2025-01-01", query_end="2025-12-31",
        ingested_at="2026-08-17T21:30:00+08:00",
    )
    assert partition_rows == rows
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert write_pit_bundle(
        financial=rows, industry=(), corporate_actions=(), output=first
    ) == write_pit_bundle(financial=rows, industry=(), corporate_actions=(), output=second)
    assert first.read_bytes() == second.read_bytes()


def test_staging_contract_output_is_deterministic(tmp_path: Path) -> None:
    contract = default_staging_contract()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert write_pit_staging_contract(contract, first) == write_pit_staging_contract(
        contract, second
    )
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8"))["formal_research_eligible"] is False
