from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.qmt.models import QmtDataError
from stephen_quant.qmt.pit_staging import (
    FinancialVisibility,
    IndustryMembershipPIT,
    alphapai_missing_credentials_ledger,
    audit_pit_staging,
    default_staging_contract,
    validate_financial_visibility,
    validate_industry_memberships,
    visible_financial_revision,
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


def test_financial_visibility_rejects_future_and_duplicate_revision() -> None:
    row = _financial()
    with pytest.raises(QmtDataError, match="precedes announcement"):
        validate_financial_visibility((replace(
            row, actual_publish_time="2025-04-30T16:00:00+08:00"
        ),))
    with pytest.raises(QmtDataError, match="duplicate"):
        validate_financial_visibility((row, row))
    with pytest.raises(QmtDataError, match="report period"):
        validate_financial_visibility((replace(row, report_period="2025-05-01"),))


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


def test_staging_contract_output_is_deterministic(tmp_path: Path) -> None:
    contract = default_staging_contract()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert write_pit_staging_contract(contract, first) == write_pit_staging_contract(
        contract, second
    )
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8"))["formal_research_eligible"] is False
