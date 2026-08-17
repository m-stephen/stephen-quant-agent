from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from .models import QmtDataError

PIT_STAGING_VERSION = "qd-pit-staging-0.2.0"
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
    effective_at: str | None = None
    available_at: str | None = None
    ingested_at: str | None = None
    supersedes_revision_id: str | None = None
    parser_version: str = "alphapai-announcement-1"
    source_type: str = "announcement_metadata"
    exchange_calendar_version: str = "SSE-SZSE-calendar-unspecified"
    timezone: str = "Asia/Shanghai"

    @property
    def visible_at(self) -> str:
        if self.available_at:
            return _time(self.available_at, "available_at").isoformat()
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
    announcement_at: str | None = None
    available_at: str | None = None
    revision_id: str = "unversioned"
    supersedes_revision_id: str | None = None
    source_document_id: str = "unprovenanced"
    source_hash: str = "0" * 64
    classification_version: str = "unspecified"


@dataclass(frozen=True)
class CorporateActionPIT:
    code: str
    event_type: str
    announcement_at: str
    available_at: str
    effective_date: str
    revision_id: str
    source_document_id: str
    source_hash: str
    record_date: str | None = None
    ex_date: str | None = None
    cash_dividend_per_share: str | None = None
    split_ratio: str | None = None
    rights_ratio: str | None = None
    total_shares_after: str | None = None
    float_shares_after: str | None = None
    share_unit: str = "share"
    currency: str = "CNY"
    supersedes_revision_id: str | None = None
    parser_version: str = "manual-source-1"


@dataclass(frozen=True)
class PITMarketCap:
    code: str
    decision_at: str
    shares: str
    share_type: Literal["total", "float"]
    share_unit: str
    price: str
    price_currency: str
    market_cap: str
    market_cap_currency: str
    shares_revision_id: str
    source_hash: str


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
    corporate_action_rows: int = 0
    corporate_action_violations: int = 0

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
    document_versions: dict[tuple[str, str, str], list[FinancialVisibility]] = {}
    for row in rows:
        if not all((row.code, row.report_type, row.revision_id, row.source_document_id)):
            raise QmtDataError("financial visibility identifiers cannot be empty")
        report_period = _day(row.report_period, "report_period")
        announced = _time(row.announcement_time, "announcement_time")
        published = _time(row.actual_publish_time, "actual_publish_time")
        available = _time(row.visible_at, "available_at")
        if row.effective_at:
            effective = _time(row.effective_at, "effective_at")
            if row.source_type not in {"earnings_forecast", "earnings_flash"} \
                    and effective.date() < report_period:
                raise QmtDataError("financial effective_at precedes report period")
        if row.ingested_at and _time(row.ingested_at, "ingested_at") < available:
            raise QmtDataError("financial ingested_at precedes availability")
        if available < max(announced, published):
            raise QmtDataError("financial available_at precedes publication")
        if not all((row.parser_version, row.source_type, row.exchange_calendar_version, row.timezone)):
            raise QmtDataError("financial timing metadata cannot be empty")
        _sha256(row.source_hash, "source_hash")
        if row.source_type not in {"earnings_forecast", "earnings_flash"} \
                and report_period >= published.date():
            raise QmtDataError("financial report is visible before report period ends")
        key = (row.code.upper(), row.report_period, row.report_type, row.revision_id)
        if key in seen:
            raise QmtDataError("duplicate financial revision key")
        seen.add(key)
        chain_key = key[:3]
        document_versions.setdefault(chain_key, []).append(row)
    for chain in document_versions.values():
        ordered = sorted(chain, key=lambda row: (_time(row.visible_at, "visible_at"), row.revision_id))
        revisions = {row.revision_id for row in ordered}
        if len(revisions) != len(ordered):
            raise QmtDataError("financial revision id is reused")
        for index, row in enumerate(ordered):
            if index == 0 and row.supersedes_revision_id is not None:
                raise QmtDataError("first financial revision cannot supersede another revision")
            if index > 0 and row.supersedes_revision_id != ordered[index - 1].revision_id:
                raise QmtDataError("financial revision chain is broken")
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
        _sha256(row.source_hash, "industry source_hash")
        if row.available_at:
            available = _time(row.available_at, "industry available_at")
            if row.announcement_at and available < _time(row.announcement_at, "announcement_at"):
                raise QmtDataError("industry availability precedes announcement")
        if not all((row.revision_id, row.source_document_id, row.classification_version)):
            raise QmtDataError("industry provenance fields cannot be empty")
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


def visible_industry_membership(
    rows: tuple[IndustryMembershipPIT, ...], *, code: str, industry_system: str,
    industry_level: str, as_of: str,
) -> IndustryMembershipPIT | None:
    cutoff = _time(as_of, "as_of")
    eligible = [row for row in validate_industry_memberships(rows) if (
        row.code.upper() == code.upper()
        and row.industry_system == industry_system
        and row.industry_level == industry_level
        and (row.available_at is not None and _time(row.available_at, "available_at") <= cutoff)
        and _day(row.effective_from, "effective_from") <= cutoff.date()
        and (row.effective_to is None or cutoff.date() < _day(row.effective_to, "effective_to"))
    )]
    return max(eligible, key=lambda row: (_time(row.available_at or "", "available_at"),
                                          row.revision_id)) if eligible else None


def validate_corporate_actions(
    rows: tuple[CorporateActionPIT, ...],
) -> tuple[CorporateActionPIT, ...]:
    seen: set[tuple[str, str, str]] = set()
    chains: dict[tuple[str, str, str], list[CorporateActionPIT]] = {}
    for row in rows:
        if not all((row.code, row.event_type, row.revision_id, row.source_document_id,
                    row.parser_version, row.share_unit, row.currency)):
            raise QmtDataError("corporate action identifiers cannot be empty")
        announced = _time(row.announcement_at, "announcement_at")
        available = _time(row.available_at, "available_at")
        effective = _day(row.effective_date, "effective_date")
        if available < announced:
            raise QmtDataError("corporate action availability precedes announcement")
        for field, value in (("record_date", row.record_date), ("ex_date", row.ex_date)):
            if value:
                _day(value, field)
        _sha256(row.source_hash, "corporate action source_hash")
        numeric = (row.cash_dividend_per_share, row.split_ratio, row.rights_ratio,
                   row.total_shares_after, row.float_shares_after)
        try:
            if any(value is not None and Decimal(value) < 0 for value in numeric):
                raise QmtDataError("corporate action numeric values cannot be negative")
        except InvalidOperation as exc:
            raise QmtDataError("invalid corporate action numeric value") from exc
        key = (row.code.upper(), row.event_type, row.revision_id)
        if key in seen:
            raise QmtDataError("duplicate corporate action revision")
        seen.add(key)
        chain_key = (row.code.upper(), row.event_type, effective.isoformat())
        chains.setdefault(chain_key, []).append(row)
    for chain in chains.values():
        ordered = sorted(chain, key=lambda row: (_time(row.available_at, "available_at"),
                                                 row.revision_id))
        for index, row in enumerate(ordered):
            expected = None if index == 0 else ordered[index - 1].revision_id
            if row.supersedes_revision_id != expected:
                raise QmtDataError("corporate action revision chain is broken")
    return tuple(sorted(rows, key=lambda row: (
        row.code.upper(), row.effective_date, row.event_type,
        _time(row.available_at, "available_at"), row.revision_id,
    )))


def build_pit_market_cap(
    *, code: str, decision_at: str, shares: str, share_type: Literal["total", "float"],
    share_unit: str, price: str, price_currency: str, shares_revision_id: str,
    shares_available_at: str, price_available_at: str, source_hash: str,
) -> PITMarketCap:
    decision = _time(decision_at, "decision_at")
    if _time(shares_available_at, "shares_available_at") > decision:
        raise QmtDataError("shares are not visible at decision time")
    if _time(price_available_at, "price_available_at") > decision:
        raise QmtDataError("price is not visible at decision time")
    if share_unit != "share":
        raise QmtDataError("PIT market cap requires shares normalized to share")
    _sha256(source_hash, "market cap source_hash")
    try:
        share_value, price_value = Decimal(shares), Decimal(price)
    except InvalidOperation as exc:
        raise QmtDataError("invalid PIT market cap numeric value") from exc
    if share_value < 0 or price_value < 0:
        raise QmtDataError("PIT market cap inputs cannot be negative")
    market_cap = share_value * price_value
    return PITMarketCap(
        code=code.upper(), decision_at=decision.isoformat(), shares=str(share_value),
        share_type=share_type, share_unit=share_unit, price=str(price_value),
        price_currency=price_currency, market_cap=format(market_cap, "f"),
        market_cap_currency=price_currency, shares_revision_id=shares_revision_id,
        source_hash=source_hash.lower(),
    )


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
    ingested_at: str | None = None,
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
        available_at = max(
            _time(announcement_time, "announcement_time"),
            _time(actual_publish_time, "actual_publish_time"),
        ).isoformat()
        source_type = "earnings_forecast" if "业绩预告" in f"{title} {type_name}" else (
            "earnings_flash" if "业绩快报" in f"{title} {type_name}" else "periodic_report"
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
                effective_at=(available_at if source_type in {"earnings_forecast", "earnings_flash"}
                              else f"{report_period}T23:59:59{timezone_offset}"),
                available_at=available_at,
                ingested_at=ingested_at,
                source_type=source_type,
            ))
    linked: list[FinancialVisibility] = []
    grouped: dict[tuple[str, str, str], list[FinancialVisibility]] = {}
    for row in rows:
        grouped.setdefault((row.code, row.report_period, row.report_type), []).append(row)
    for chain in grouped.values():
        ordered = sorted(chain, key=lambda row: (_time(row.visible_at, "visible_at"),
                                                 row.revision_id))
        for index, row in enumerate(ordered):
            linked.append(replace(
                row, supersedes_revision_id=None if index == 0 else ordered[index - 1].revision_id
            ))
    validated = validate_financial_visibility(tuple(linked)) if linked else ()
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


def ingest_alphapai_announcement_pages(
    responses: tuple[dict[str, Any], ...], *, query_start: str, query_end: str,
    ingested_at: str | None = None, timezone_offset: str = "+08:00",
) -> tuple[tuple[FinancialVisibility, ...], RemoteRetrievalLedger]:
    if not responses:
        raise QmtDataError("AlphaPai pagination requires at least one response")
    items: list[dict[str, Any]] = []
    expected_pages: int | None = None
    expected_total: int | None = None
    seen_pages: set[int] = set()
    for response in responses:
        if response.get("code") != 200000 or not isinstance(response.get("data"), dict):
            raise QmtDataError("AlphaPai pagination contains unsuccessful response")
        envelope = response["data"]
        page = int(envelope.get("pageNum", 0))
        total_pages = int(envelope.get("totalPageNum", 0))
        total_size = int(envelope.get("totalSize", -1))
        if page <= 0 or total_pages <= 0 or page in seen_pages:
            raise QmtDataError("AlphaPai pagination metadata is invalid")
        if expected_pages is None:
            expected_pages = total_pages
            expected_total = total_size
        if total_pages != expected_pages:
            raise QmtDataError("AlphaPai pagination changed during retrieval")
        if total_size != expected_total:
            raise QmtDataError("AlphaPai pagination total changed during retrieval")
        page_items = envelope.get("data")
        if not isinstance(page_items, list):
            raise QmtDataError("AlphaPai pagination data must be a list")
        seen_pages.add(page)
        items.extend(page_items)
    if expected_pages != len(seen_pages) or seen_pages != set(range(1, expected_pages + 1)):
        raise QmtDataError("AlphaPai pagination is incomplete")
    if expected_total != len(items):
        raise QmtDataError("AlphaPai pagination item count is incomplete")
    merged = {
        "code": 200000,
        "message": "success",
        "data": {
            "pageNum": 1, "pageSize": len(items), "totalPageNum": 1,
            "totalSize": len(items), "data": items,
        },
    }
    return ingest_alphapai_announcement_response(
        merged, query_start=query_start, query_end=query_end,
        timezone_offset=timezone_offset, ingested_at=ingested_at,
    )


def ingest_alphapai_announcement_partitions(
    partitions: tuple[tuple[dict[str, Any], ...], ...], *, query_start: str,
    query_end: str, ingested_at: str, timezone_offset: str = "+08:00",
) -> tuple[tuple[FinancialVisibility, ...], RemoteRetrievalLedger]:
    if not partitions:
        raise QmtDataError("AlphaPai partition collection cannot be empty")
    items: list[dict[str, Any]] = []
    for responses in partitions:
        ingest_alphapai_announcement_pages(
            responses, query_start=query_start, query_end=query_end,
            ingested_at=ingested_at, timezone_offset=timezone_offset,
        )
        for response in responses:
            items.extend(response["data"]["data"])
    merged = {
        "code": 200000,
        "message": "success",
        "data": {
            "pageNum": 1, "pageSize": len(items), "totalPageNum": 1,
            "totalSize": len(items), "data": items,
        },
    }
    return ingest_alphapai_announcement_response(
        merged, query_start=query_start, query_end=query_end,
        timezone_offset=timezone_offset, ingested_at=ingested_at,
    )


def write_pit_bundle(
    *, financial: tuple[FinancialVisibility, ...],
    industry: tuple[IndustryMembershipPIT, ...],
    corporate_actions: tuple[CorporateActionPIT, ...], output: str | Path,
) -> str:
    payload = {
        "version": PIT_STAGING_VERSION,
        "formal_research_eligible": False,
        "financial_visibility": [asdict(row) for row in validate_financial_visibility(financial)],
        "industry_membership_pit": [asdict(row) for row in validate_industry_memberships(industry)],
        "corporate_action_pit": [asdict(row) for row in validate_corporate_actions(
            corporate_actions
        )],
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_pit_staging_contract(contract: StagingContract, output: str | Path) -> str:
    content = contract.to_json() + "\n"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
