from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from .models import QmtDataError

PIT_STAGING_VERSION = "qd-pit-staging-0.1.0"
FieldClass = Literal["A", "B", "C"]


def _time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QmtDataError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise QmtDataError(f"{field} must include timezone")
    return parsed


def _day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise QmtDataError(f"invalid {field}") from exc


def _sha256(value: str, field: str) -> str:
    normalized = value.lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise QmtDataError(f"invalid {field}")
    return normalized


@dataclass(frozen=True)
class FinancialVisibility:
    code: str
    report_period: str
    report_type: str
    announcement_time: str
    actual_publish_time: str
    revision_id: str
    source_document_id: str
    source_hash: str

    @property
    def visible_at(self) -> str:
        return max(_time(self.announcement_time, "announcement_time"), _time(
            self.actual_publish_time, "actual_publish_time"
        )).isoformat()


@dataclass(frozen=True)
class IndustryMembershipPIT:
    code: str
    industry_system: str
    industry_level: str
    industry_code: str
    industry_name: str
    effective_from: str
    effective_to: str | None
    source: str


@dataclass(frozen=True)
class FieldAdmission:
    layer: str
    field: str
    classification: FieldClass
    available_at_policy: str
    formal_alpha_allowed: bool
    reason: str


@dataclass(frozen=True)
class StagingContract:
    version: str
    admissions: tuple[FieldAdmission, ...]
    restricted_years: tuple[int, ...]
    formal_research_eligible: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class PitLeakageAudit:
    financial_rows: int
    industry_rows: int
    duplicate_revision_keys: int
    financial_timing_violations: int
    industry_interval_overlaps: int
    provenance_breaks: int
    c_fields_formally_admitted: int
    gate_pass: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class RemoteRetrievalLedger:
    source: str
    operation: str
    query_start: str
    query_end: str
    status: str
    credential_available: bool
    documents_received: int
    inferential_trial_delta: int
    requested_outputs: tuple[str, ...]
    note: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def default_staging_contract() -> StagingContract:
    rows = (
        FieldAdmission("daily_bars", "ohlcv", "A", "after_close_or_next_session", True,
                       "direct market observation with frozen source hash"),
        FieldAdmission("valuation_snapshot", "pe_pb_ps_dividend_yield", "A",
                       "after_close_or_next_session", True,
                       "same-day valuation snapshot; nulls remain unavailable"),
        FieldAdmission("market_microstructure", "turnover_and_daily_derived_fields", "A",
                       "after_close_or_next_session", True,
                       "daily public-market snapshot, not Level-2"),
        FieldAdmission("security_master", "listing_and_share_fields", "B",
                       "requires effective metadata or conservative persistence", False,
                       "daily snapshots do not prove original effective time"),
        FieldAdmission("fundamental_snapshot", "financial_metrics", "B",
                       "requires FinancialVisibility.actual_publish_time", False,
                       "daily values alone do not prove report-period visibility"),
        FieldAdmission("industry_membership_pit", "stock_industry_membership", "B",
                       "requires effective_from/effective_to evidence", False,
                       "industry index quotes are not constituent history"),
        FieldAdmission("attention_candidate", "rank_hotness_and_social_fields", "C",
                       "candidate_only", False,
                       "attention signal cannot enter formal alpha acceptance"),
        FieldAdmission("technical_vendor", "strong_activity_attack_wave", "C",
                       "candidate_only", False,
                       "vendor-derived semantics lack reproducible definition"),
    )
    return StagingContract(
        version=PIT_STAGING_VERSION,
        admissions=rows,
        restricted_years=(2025, 2026),
        formal_research_eligible=False,
    )


def validate_financial_visibility(
    rows: tuple[FinancialVisibility, ...],
) -> tuple[FinancialVisibility, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    document_versions: dict[tuple[str, str, str], list[tuple[datetime, str]]] = {}
    for row in rows:
        if not all((row.code, row.report_type, row.revision_id, row.source_document_id)):
            raise QmtDataError("financial visibility identifiers cannot be empty")
        report_period = _day(row.report_period, "report_period")
        _time(row.announcement_time, "announcement_time")
        published = _time(row.actual_publish_time, "actual_publish_time")
        _sha256(row.source_hash, "source_hash")
        if report_period >= published.date():
            raise QmtDataError("financial report is visible before report period ends")
        key = (row.code.upper(), row.report_period, row.report_type, row.revision_id)
        if key in seen:
            raise QmtDataError("duplicate financial revision key")
        seen.add(key)
        chain_key = key[:3]
        document_versions.setdefault(chain_key, []).append((published, row.revision_id))
    for chain in document_versions.values():
        ordered = sorted(chain)
        if len({revision for _, revision in ordered}) != len(ordered):
            raise QmtDataError("financial revision id is reused")
    return tuple(sorted(rows, key=lambda row: (
        row.code.upper(), row.report_period, row.report_type,
        _time(row.actual_publish_time, "actual_publish_time"), row.revision_id,
    )))


def visible_financial_revision(
    rows: tuple[FinancialVisibility, ...], *, code: str, report_period: str,
    report_type: str, as_of: str,
) -> FinancialVisibility | None:
    cutoff = _time(as_of, "as_of")
    eligible = [row for row in validate_financial_visibility(rows) if (
        row.code.upper() == code.upper()
        and row.report_period == report_period
        and row.report_type == report_type
        and _time(row.visible_at, "visible_at") <= cutoff
    )]
    return max(eligible, key=lambda row: (_time(row.visible_at, "visible_at"), row.revision_id)) \
        if eligible else None


def validate_industry_memberships(
    rows: tuple[IndustryMembershipPIT, ...],
) -> tuple[IndustryMembershipPIT, ...]:
    grouped: dict[tuple[str, str, str], list[tuple[date, date | None, IndustryMembershipPIT]]] = {}
    for row in rows:
        if not all((row.code, row.industry_system, row.industry_level, row.industry_code,
                    row.industry_name, row.source)):
            raise QmtDataError("industry membership fields cannot be empty")
        start = _day(row.effective_from, "effective_from")
        end = _day(row.effective_to, "effective_to") if row.effective_to else None
        if end is not None and end <= start:
            raise QmtDataError("industry effective_to must be after effective_from")
        key = (row.code.upper(), row.industry_system, row.industry_level)
        grouped.setdefault(key, []).append((start, end, row))
    for intervals in grouped.values():
        ordered = sorted(intervals, key=lambda item: item[0])
        for previous, current in pairwise(ordered):
            if previous[1] is None or current[0] < previous[1]:
                raise QmtDataError("overlapping industry membership intervals")
    return tuple(sorted(rows, key=lambda row: (
        row.code.upper(), row.industry_system, row.industry_level, row.effective_from,
    )))


def audit_pit_staging(
    financial: tuple[FinancialVisibility, ...],
    industry: tuple[IndustryMembershipPIT, ...],
    contract: StagingContract,
) -> PitLeakageAudit:
    financial_violations = industry_overlaps = provenance = duplicates = 0
    try:
        validate_financial_visibility(financial)
    except QmtDataError as exc:
        financial_violations = int("time" in str(exc) or "period" in str(exc))
        duplicates = int("duplicate" in str(exc) or "reused" in str(exc))
        provenance = int("hash" in str(exc) or "identifier" in str(exc))
    try:
        validate_industry_memberships(industry)
    except QmtDataError as exc:
        industry_overlaps = int("overlapping" in str(exc))
        provenance += int("empty" in str(exc))
    forbidden = sum(
        admission.classification == "C" and admission.formal_alpha_allowed
        for admission in contract.admissions
    )
    failures = duplicates + financial_violations + industry_overlaps + provenance + forbidden
    return PitLeakageAudit(
        financial_rows=len(financial),
        industry_rows=len(industry),
        duplicate_revision_keys=duplicates,
        financial_timing_violations=financial_violations,
        industry_interval_overlaps=industry_overlaps,
        provenance_breaks=provenance,
        c_fields_formally_admitted=forbidden,
        gate_pass=failures == 0,
    )


def alphapai_missing_credentials_ledger(start: str, end: str) -> RemoteRetrievalLedger:
    if _day(start, "query_start") > _day(end, "query_end"):
        raise QmtDataError("AlphaPai query range is reversed")
    return RemoteRetrievalLedger(
        source="alphapai-announcement",
        operation="financial-visibility-metadata",
        query_start=start,
        query_end=end,
        status="not_run_missing_credentials",
        credential_available=False,
        documents_received=0,
        inferential_trial_delta=0,
        requested_outputs=(
            "announcement_metadata", "actual_publish_time", "source_document_provenance",
        ),
        note="No response was fabricated; configure ALPHAPAI_API_KEY for a later local retrieval.",
    )


def _alphapai_time(value: object, field: str, timezone_offset: str) -> str:
    raw = str(value or "").strip().replace(" ", "T")
    if not raw:
        raise QmtDataError(f"AlphaPai announcement requires {field}")
    if raw.endswith("Z") or "+" in raw[10:] or raw[10:].count("-"):
        return _time(raw, field).isoformat()
    return _time(f"{raw}{timezone_offset}", field).isoformat()


def ingest_alphapai_announcement_response(
    response: dict[str, Any],
    *,
    query_start: str,
    query_end: str,
    timezone_offset: str = "+08:00",
) -> tuple[tuple[FinancialVisibility, ...], RemoteRetrievalLedger]:
    if response.get("code") != 200000:
        raise QmtDataError("AlphaPai announcement request was not successful")
    if _day(query_start, "query_start") > _day(query_end, "query_end"):
        raise QmtDataError("AlphaPai query range is reversed")
    envelope = response.get("data")
    if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list):
        raise QmtDataError("AlphaPai announcement response has invalid pagination data")
    allowed_tokens = ("定期报告", "年度报告", "年报", "季度报告", "季报", "中期报告", "半年报",
                      "业绩预告", "业绩快报")
    rows: list[FinancialVisibility] = []
    for item in envelope["data"]:
        if not isinstance(item, dict):
            raise QmtDataError("AlphaPai announcement item must be an object")
        title = str(item.get("title") or "")
        report_type = str(item.get("announcementTypeCode") or item.get("announcementType") or "")
        type_name = str(item.get("announcementType") or "")
        if not any(token in f"{title} {type_name}" for token in allowed_tokens):
            continue
        report_period = str(item.get("endDate") or "")[:10]
        _day(report_period, "AlphaPai endDate")
        announcement_time = _alphapai_time(item.get("publishTime"), "publishTime", timezone_offset)
        actual_publish_time = _alphapai_time(
            item.get("actualPublishTime"), "actualPublishTime", timezone_offset
        )
        stocks = item.get("stockTag")
        if not isinstance(stocks, list) or not stocks:
            raise QmtDataError("AlphaPai periodic announcement requires stockTag")
        stable_metadata = {
            key: item.get(key) for key in (
                "title", "publishTime", "actualPublishTime", "endDate",
                "announcementType", "announcementTypeCode", "market", "stockTag", "industryTag",
                "hasPdf",
            )
        }
        source_hash = hashlib.sha256(json.dumps(
            stable_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        source_document_id = hashlib.sha256(
            f"alphapai-announcement|{source_hash}".encode()
        ).hexdigest()
        revision_id = hashlib.sha256(
            f"{report_period}|{report_type}|{actual_publish_time}|{source_hash}".encode()
        ).hexdigest()[:24]
        for stock in stocks:
            if not isinstance(stock, dict) or not str(stock.get("code") or "").strip():
                raise QmtDataError("AlphaPai stockTag contains invalid code")
            rows.append(FinancialVisibility(
                code=str(stock["code"]).strip().upper(),
                report_period=report_period,
                report_type=report_type,
                announcement_time=announcement_time,
                actual_publish_time=actual_publish_time,
                revision_id=revision_id,
                source_document_id=source_document_id,
                source_hash=source_hash,
            ))
    validated = validate_financial_visibility(tuple(rows)) if rows else ()
    ledger = RemoteRetrievalLedger(
        source="alphapai-announcement",
        operation="financial-visibility-metadata",
        query_start=query_start,
        query_end=query_end,
        status="success",
        credential_available=True,
        documents_received=len(validated),
        inferential_trial_delta=0,
        requested_outputs=(
            "announcement_metadata", "actual_publish_time", "source_document_provenance",
        ),
        note="Encrypted announcement IDs are transient and excluded from durable PIT identifiers.",
    )
    return validated, ledger


def write_pit_staging_contract(contract: StagingContract, output: str | Path) -> str:
    content = contract.to_json() + "\n"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
