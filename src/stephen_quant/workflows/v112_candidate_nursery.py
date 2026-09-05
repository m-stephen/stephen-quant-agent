from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

V112_VERSION = "11.2.0"
V112_SPEC_VERSION = "11.2.0"
RAW_GLOBAL_TRIALS = 770
EXPECTED_PROTOCOL_SHA256 = "71ba4f198f2f3dcbc4877d684f5a5fd8023d806a469e2d2a482ead4174a77106"
EXPECTED_PROTOCOL_ARTIFACT_SHA256 = "bd05436613e94f4333383f66f68c1c6fa22f0703041fabbe23d5b3282deb546c"
EXPECTED_V111_REPORT_SHA256 = "6999406bd8151d51aa42a797cc26503fe12ff8101d229e5cea30e18e9937173f"
EXPECTED_V111_EVIDENCE_ARTIFACT_SHA256 = "4f0d47a48cb53f724c8a545889f6a8a9935f143b5bbcc1fa338b5d7a924bfde1"

FORWARD_CANDIDATE_IDS = (
    "ec9faf313b03bd78dd999158c994d9a8464149c220c256abca6fa2c96009c1f2",
    "25023e50365dc75cf614bc025ef36296193ac0447e06cc98feb18d4ff4340f7a",
)
SOURCE_REQUIREMENTS = {
    FORWARD_CANDIDATE_IDS[0]: ("daily", "minute"),
    FORWARD_CANDIDATE_IDS[1]: ("chip", "daily", "minute"),
}
DOMAIN_PRIORITY = (
    "announcement_expectation_surprise",
    "share_supply_corporate_action_shocks",
    "within_industry_relative_mechanisms",
)
DOMAIN_REQUIRED_FIELDS = {
    "announcement_expectation_surprise": {
        "instrument",
        "event_id",
        "actual_value",
        "expected_value",
        "effective_at",
        "available_at",
        "ingested_at",
        "revision_id",
    },
    "share_supply_corporate_action_shocks": {
        "instrument",
        "event_id",
        "event_type",
        "share_delta",
        "effective_at",
        "available_at",
        "ingested_at",
        "revision_id",
    },
    "within_industry_relative_mechanisms": {
        "instrument",
        "industry_code",
        "effective_at",
        "available_at",
        "ingested_at",
        "source_id",
    },
}

SPEC_CONTRACT: dict[str, object] = {
    "version": V112_SPEC_VERSION,
    "raw_global_trials": RAW_GLOBAL_TRIALS,
    "candidate_states": [
        "RESEARCH_CLUE",
        "FORWARD_CONFIRMATION_CANDIDATE",
        "VALIDATED_ALPHA",
        "RESEARCH_CLUE_SPECIFICATION_DEPENDENT",
        "REJECTED_DEVELOPMENT_EVIDENCE",
        "FORWARD_REJECTED",
    ],
    "forward_checkpoints": [25, 126, 252],
    "primary_estimand": "long_only_top40_minus_investable_dynamic_universe_equal_weight",
    "return_frequency": "holding-period-20-session-overlapping-positions",
    "benchmark": "contemporaneous_investable_dynamic_universe_equal_weight",
    "cost_bps": [41.0, 82.0],
    "missing_policy": "frozen_v10_stateful_execution_contract",
    "primary_inference": {
        "family": "two-frozen-hypothesis-family",
        "multiplicity": "Holm alpha=0.05 at family day 252 only",
        "interval": "HAC with lag=19; frozen block-bootstrap fallback block=20",
        "minimum_actionable_dates": 252,
        "prospective_pbo": "NOT_APPLICABLE without configuration selection",
        "historical_dsr_pbo": "permanent selection-risk provenance",
    },
    "calendar": "candidate coverage calendars plus actionable family intersection",
    "first_seen": "controlled UTC clock after genesis and no later than decision cutoff",
    "labels": "no historical or forward return interface in V11.2 data preparation",
    "orthogonal_required_fields": {
        key: sorted(value) for key, value in DOMAIN_REQUIRED_FIELDS.items()
    },
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


SPEC_HASH = _sha(SPEC_CONTRACT)


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_text(value: object) -> str:
    text = str(value)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError("SHA-256 values must be lowercase 64-character hexadecimal strings")
    return text


@dataclass(frozen=True)
class ProtocolReference:
    protocol_sha256: str
    artifact_sha256: str
    frozen_protocol_code_version: str
    runtime_runner_code_version: str
    first_eligible_date_exclusive: str
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClockManifest:
    ingestion_clock_genesis: str
    collector_id: str
    collector_version: str
    host_clock_source: str
    market_timezone: str
    content_hash: str


@dataclass(frozen=True)
class NurseryRecord:
    candidate_id: str
    name: str
    candidate_state: str
    direction: int
    expression: str
    mechanism: str
    horizon: int
    protocol_sha256: str | None
    evidence: dict[str, object]
    status_history: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ReceiptEvent:
    sequence: int
    source: str
    trade_date: str
    candidate_ids: tuple[str, ...]
    arrival_state: str
    reason_code: str
    source_event_time: str
    vendor_publish_time: str | None
    collection_started_at: str
    collection_completed_at: str
    raw_payload_hash: str
    decision_cutoff: str
    first_ingested_at: str
    revision_id: str
    supersedes_revision_id: str | None
    previous_receipt_hash: str | None
    receipt_hash: str


@dataclass(frozen=True)
class ForwardRuntime:
    clock_state: str
    forward_stage: str
    candidate_eligible_calendars: dict[str, tuple[str, ...]]
    candidate_calendar_hashes: dict[str, str]
    family_primary_calendar: tuple[str, ...]
    family_primary_calendar_hash: str
    source_watermarks: dict[str, str | None]
    arrival_counts: dict[str, int]
    receipt_events: tuple[ReceiptEvent, ...]
    performance_conclusion: None
    prospective_pbo: str


@dataclass(frozen=True)
class OrthogonalDataResult:
    state: str
    selected_domain: str | None
    evaluations: tuple[dict[str, object], ...]
    label_accesses: int


@dataclass(frozen=True)
class V112RunReport:
    content: dict[str, object]
    content_hash: str
    run_envelope: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(
            {**self.content, "content_hash": self.content_hash},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def load_frozen_protocol(path: str | Path, runtime_code_version: str) -> tuple[dict[str, object], ProtocolReference]:
    raw = Path(path).read_bytes()
    if _sha_bytes(raw) != EXPECTED_PROTOCOL_ARTIFACT_SHA256:
        raise ValueError("frozen protocol artifact bytes changed")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise TypeError("frozen protocol must be a JSON object")
    declared = _hash_text(payload.get("protocol_sha256"))
    semantic = dict(payload)
    del semantic["protocol_sha256"]
    if _sha(semantic) != declared or declared != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("frozen protocol semantic hash mismatch")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise TypeError("frozen protocol candidates are missing")
    ids = tuple(str(item.get("candidate_id")) for item in candidates if isinstance(item, dict))
    if ids != FORWARD_CANDIDATE_IDS:
        raise ValueError("frozen candidate identities or order changed")
    boundary = str(payload.get("first_eligible_date_exclusive"))
    date.fromisoformat(boundary)
    return payload, ProtocolReference(
        declared,
        _sha_bytes(raw),
        str(payload.get("code_version")),
        runtime_code_version,
        boundary,
        ids,
    )


def load_or_create_clock(
    path: str | Path,
    *,
    genesis_at: str | None,
    collector_id: str,
    collector_version: str,
    host_clock_source: str = "OS_UTC_CLOCK",
    market_timezone: str = "Asia/Shanghai",
) -> ClockManifest | None:
    target = Path(path)
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        content_hash = str(payload.pop("content_hash"))
        if _sha(payload) != content_hash:
            raise ValueError("clock manifest hash mismatch")
        manifest = ClockManifest(**payload, content_hash=content_hash)
        if genesis_at is not None and _utc_text(_parse_time(genesis_at, "ingestion_clock_genesis")) != manifest.ingestion_clock_genesis:
            raise ValueError("trusted ingestion clock genesis is immutable")
        if collector_id != manifest.collector_id or collector_version != manifest.collector_version:
            raise ValueError("trusted ingestion collector identity is immutable")
        return manifest
    if genesis_at is None:
        return None
    genesis = _parse_time(genesis_at, "ingestion_clock_genesis")
    payload = {
        "ingestion_clock_genesis": _utc_text(genesis),
        "collector_id": collector_id,
        "collector_version": collector_version,
        "host_clock_source": host_clock_source,
        "market_timezone": market_timezone,
    }
    manifest = ClockManifest(**payload, content_hash=_sha(payload))
    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, json.dumps(asdict(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def _load_evidence(path: str | Path) -> dict[str, object]:
    raw = Path(path).read_bytes()
    if _sha_bytes(raw) != EXPECTED_V111_EVIDENCE_ARTIFACT_SHA256:
        raise ValueError("V11.1 evidence freeze artifact bytes changed")
    payload = json.loads(raw)
    if payload.get("semantic_report_sha256") != EXPECTED_V111_REPORT_SHA256:
        raise ValueError("V11.1 evidence semantic report hash mismatch")
    if payload.get("raw_global_trials_after") != RAW_GLOBAL_TRIALS:
        raise ValueError("V11.1 evidence does not preserve raw Trial baseline 770")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 15:
        raise ValueError("V11.1 evidence must contain exactly 15 candidates")
    return payload


def build_nursery(protocol: dict[str, object], evidence: dict[str, object]) -> tuple[NurseryRecord, ...]:
    records: list[NurseryRecord] = []
    for item in protocol["candidates"]:  # type: ignore[index]
        assert isinstance(item, dict)
        candidate_id = str(item["candidate_id"])
        state = "FORWARD_CONFIRMATION_CANDIDATE"
        records.append(
            NurseryRecord(
                candidate_id,
                str(item["name"]),
                state,
                int(item["direction"]),
                str(item["expression"]),
                str(item["operator"]),
                int(item["holding_sessions"]),
                str(protocol["protocol_sha256"]),
                {
                    "trial_id": item["trial_id"],
                    "historical_selection_risk": "PRESERVED_NOT_RESET",
                    "forward_evidence_eligibility": "COVERAGE_ONLY_UNTIL_ACTIONABLE",
                },
                ({"sequence": 1, "from": None, "to": state, "reason": "V11_PROTOCOL_MIGRATION"},),
            )
        )
    clue_id = "v11-chip-crowding-level-clue"
    clue_state = "RESEARCH_CLUE_SPECIFICATION_DEPENDENT"
    records.append(
        NurseryRecord(
            clue_id,
            "V11 level-based chip clue",
            clue_state,
            1,
            "-(rank(profit_ratio)-rank(concentration))",
            "chip_crowding",
            20,
            None,
            {
                "net_excess": 0.6266,
                "sharpe": 1.249,
                "dsr": 0.001229,
                "pbo": 0.30,
                "reason": "V11.1 state-transition evidence weakened the level specification",
            },
            ({"sequence": 1, "from": "RESEARCH_CLUE", "to": clue_state, "reason": "V11_1_SPECIFICATION_DEPENDENCE"},),
        )
    )
    for item in evidence["candidates"]:  # type: ignore[index]
        assert isinstance(item, dict)
        state = "REJECTED_DEVELOPMENT_EVIDENCE"
        candidate_id = str(item["candidate_id"])
        candidate_evidence = {key: value for key, value in item.items() if key not in {"candidate_id", "expression", "mechanism", "horizon"}}
        candidate_evidence["source_report_sha256"] = evidence["semantic_report_sha256"]
        records.append(
            NurseryRecord(
                candidate_id,
                f"V11.1 {item['mechanism']} candidate",
                state,
                1,
                str(item["expression"]),
                str(item["mechanism"]),
                int(item["horizon"]),
                None,
                candidate_evidence,
                ({"sequence": 1, "from": "RESEARCH_CLUE", "to": state, "reason": "V11_1_ALPHA_COURT_REJECTION"},),
            )
        )
    ids = [item.candidate_id for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("nursery candidate identities must be unique")
    return tuple(records)


ALLOWED_TRANSITIONS = {
    "RESEARCH_CLUE": {
        "FORWARD_CONFIRMATION_CANDIDATE",
        "RESEARCH_CLUE_SPECIFICATION_DEPENDENT",
        "REJECTED_DEVELOPMENT_EVIDENCE",
    },
    "FORWARD_CONFIRMATION_CANDIDATE": {"FORWARD_REJECTED", "VALIDATED_ALPHA"},
}


def validate_transition(previous: str, following: str, *, allow_validated_alpha: bool = False) -> None:
    if following == "VALIDATED_ALPHA" and not allow_validated_alpha:
        raise ValueError("V11.2 cannot emit VALIDATED_ALPHA")
    if following not in ALLOWED_TRANSITIONS.get(previous, set()):
        raise ValueError(f"illegal or backward candidate transition: {previous} -> {following}")


def _receipt_payload(raw: dict[str, object]) -> dict[str, object]:
    prohibited = {"return", "forward_return", "label", "ic", "price"}
    if prohibited.intersection(raw):
        raise ValueError("forward receipt input exposes a forbidden return/price label field")
    required = {
        "source",
        "trade_date",
        "candidate_ids",
        "source_event_time",
        "first_ingested_at",
        "started_at",
        "completed_at",
        "raw_payload_hash",
        "decision_cutoff",
        "revision_id",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise ValueError(f"receipt is missing required fields: {missing}")
    return raw


def evaluate_forward_runtime(
    protocol: dict[str, object],
    clock: ClockManifest | None,
    receipts: list[dict[str, object]],
) -> ForwardRuntime:
    if clock is None:
        return ForwardRuntime(
            "PROSPECTIVE_CLOCK_NOT_ESTABLISHED",
            "FORWARD_COVERAGE_ONLY",
            {item: () for item in FORWARD_CANDIDATE_IDS},
            {item: _sha([]) for item in FORWARD_CANDIDATE_IDS},
            (),
            _sha([]),
            {},
            {},
            (),
            None,
            "NOT_APPLICABLE",
        )
    genesis = _parse_time(clock.ingestion_clock_genesis, "ingestion_clock_genesis")
    boundary = date.fromisoformat(str(protocol["first_eligible_date_exclusive"]))
    seen: dict[tuple[str, str, str], str] = {}
    events: list[ReceiptEvent] = []
    actionable: dict[str, dict[str, set[str]]] = {item: {} for item in FORWARD_CANDIDATE_IDS}
    watermarks: dict[str, str | None] = {}
    counts: dict[str, int] = {}
    previous_hash: str | None = None
    ordered = sorted(receipts, key=lambda item: (str(item.get("first_ingested_at")), str(item.get("source")), str(item.get("trade_date")), str(item.get("revision_id"))))
    for sequence, raw_value in enumerate(ordered, 1):
        raw = _receipt_payload(dict(raw_value))
        source = str(raw["source"])
        trade_day = date.fromisoformat(str(raw["trade_date"]))
        event_time = _parse_time(str(raw["source_event_time"]), "source_event_time")
        ingested = _parse_time(str(raw["first_ingested_at"]), "first_ingested_at")
        started = _parse_time(str(raw["started_at"]), "started_at")
        completed = _parse_time(str(raw["completed_at"]), "completed_at")
        cutoff = _parse_time(str(raw["decision_cutoff"]), "decision_cutoff")
        if not (started <= ingested <= completed):
            raise ValueError("receipt timing must satisfy started_at <= first_ingested_at <= completed_at")
        if event_time > completed:
            raise ValueError("source_event_time cannot be after collection completed_at")
        raw_hash = _hash_text(raw["raw_payload_hash"])
        raw_candidate_ids = raw["candidate_ids"]
        if not isinstance(raw_candidate_ids, list):
            raise TypeError("receipt candidate_ids must be a list")
        candidate_ids = tuple(sorted(str(item) for item in raw_candidate_ids))
        if (
            not candidate_ids
            or len(candidate_ids) != len(set(candidate_ids))
            or any(item not in FORWARD_CANDIDATE_IDS for item in candidate_ids)
        ):
            raise ValueError("receipt candidate_ids must reference frozen forward candidates")
        revision_id = str(raw["revision_id"])
        if not revision_id:
            raise ValueError("revision_id cannot be empty")
        supersedes = raw.get("supersedes_revision_id")
        supersedes_text = str(supersedes) if supersedes is not None else None
        key = (source, trade_day.isoformat(), revision_id)
        if key in seen:
            state = "DUPLICATE_REJECTED" if seen[key] == raw_hash else "OVERWRITE_REJECTED"
            reason = state
        elif trade_day <= boundary:
            state, reason = "PREEXISTING_UNVERIFIED_ARRIVAL", "TRADE_DATE_NOT_AFTER_FREEZE_BOUNDARY"
        elif ingested < genesis:
            state, reason = "PREEXISTING_UNVERIFIED_ARRIVAL", "OBSERVED_BEFORE_TRUSTED_CLOCK_GENESIS"
        elif supersedes_text is not None:
            superseded_key = (source, trade_day.isoformat(), supersedes_text)
            if superseded_key not in seen:
                state, reason = "REVISION_CHAIN_REJECTED", "SUPERSEDED_REVISION_NOT_OBSERVED"
            else:
                state, reason = "REVISION_QA_ONLY", "REVISION_CANNOT_REWRITE_AS_FIRST_SEEN"
        elif ingested > cutoff:
            state, reason = "LATE_NOT_ACTIONABLE", "FIRST_INGESTED_AFTER_DECISION_CUTOFF"
        else:
            state, reason = "FIRST_SEEN_ACTIONABLE", "ON_TIME_AFTER_TRUSTED_CLOCK_GENESIS"
        seen.setdefault(key, raw_hash)
        counts[state] = counts.get(state, 0) + 1
        current = watermarks.get(source)
        watermarks[source] = max(filter(None, (current, trade_day.isoformat())), default=None)
        if state == "FIRST_SEEN_ACTIONABLE":
            for candidate_id in candidate_ids:
                actionable[candidate_id].setdefault(trade_day.isoformat(), set()).add(source)
        vendor_publish = (
            _parse_time(str(raw["vendor_publish_time"]), "vendor_publish_time")
            if raw.get("vendor_publish_time") is not None
            else None
        )
        if vendor_publish is not None and vendor_publish > completed:
            raise ValueError("vendor_publish_time cannot be after collection completed_at")
        event_payload = {
            "sequence": sequence,
            "source": source,
            "trade_date": trade_day.isoformat(),
            "candidate_ids": candidate_ids,
            "arrival_state": state,
            "reason_code": reason,
            "source_event_time": _utc_text(event_time),
            "vendor_publish_time": _utc_text(vendor_publish) if vendor_publish else None,
            "collection_started_at": _utc_text(started),
            "collection_completed_at": _utc_text(completed),
            "raw_payload_hash": raw_hash,
            "decision_cutoff": _utc_text(cutoff),
            "first_ingested_at": _utc_text(ingested),
            "revision_id": revision_id,
            "supersedes_revision_id": supersedes_text,
            "previous_receipt_hash": previous_hash,
        }
        receipt_hash = _sha(event_payload)
        event = ReceiptEvent(**event_payload, receipt_hash=receipt_hash)
        events.append(event)
        previous_hash = receipt_hash
    calendars: dict[str, tuple[str, ...]] = {}
    for candidate_id in FORWARD_CANDIDATE_IDS:
        required = set(SOURCE_REQUIREMENTS[candidate_id])
        calendars[candidate_id] = tuple(sorted(day for day, sources in actionable[candidate_id].items() if required <= sources))
    family = tuple(sorted(set(calendars[FORWARD_CANDIDATE_IDS[0]]) & set(calendars[FORWARD_CANDIDATE_IDS[1]])))
    count = len(family)
    stage = (
        "FORWARD_PRIMARY_EVIDENCE_REQUIRED"
        if count >= 252
        else "FORWARD_INTERIM_DESCRIPTIVE"
        if count >= 126
        else "FORWARD_RUNTIME_CHECKPOINT"
        if count >= 25
        else "ACTIONABLE_DATES_INSUFFICIENT"
    )
    return ForwardRuntime(
        "ESTABLISHED",
        stage,
        calendars,
        {key: _sha(value) for key, value in calendars.items()},
        family,
        _sha(family),
        dict(sorted(watermarks.items())),
        dict(sorted(counts.items())),
        tuple(events),
        None,
        "NOT_APPLICABLE",
    )


def _contains_prohibited_key(value: object) -> bool:
    prohibited = {"return", "returns", "forward_return", "label", "labels", "ic", "price", "prices"}
    if isinstance(value, dict):
        return any(str(key).lower() in prohibited or _contains_prohibited_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_prohibited_key(item) for item in value)
    return False


def evaluate_orthogonal_domains(payload: dict[str, object] | None) -> OrthogonalDataResult:
    if payload is None:
        return OrthogonalDataResult("ORTHOGONAL_DATA_NOT_READY", None, (), 0)
    if _contains_prohibited_key(payload):
        raise ValueError("orthogonal data preparation cannot expose returns, IC, labels, or prices")
    domains = payload.get("domains")
    if not isinstance(domains, list):
        raise TypeError("orthogonal domain inventory must contain a domains list")
    by_name: dict[str, dict[str, object]] = {}
    for raw in domains:
        if not isinstance(raw, dict):
            raise TypeError("orthogonal domain entries must be objects")
        name = str(raw.get("name"))
        if name not in DOMAIN_PRIORITY or name in by_name:
            raise ValueError("orthogonal domains must be unique members of the frozen priority")
        by_name[name] = raw
    evaluations: list[dict[str, object]] = []
    selected: str | None = None
    gates = (
        "authorization_sustainable",
        "stable_entity_ids",
        "deterministic_dedup",
        "pit_semantics_verified",
        "revision_semantics_verified",
        "replay_passed",
    )
    for name in DOMAIN_PRIORITY:
        if name not in by_name:
            evaluations.append({"name": name, "passed": False, "reason_codes": ["DOMAIN_INVENTORY_ABSENT"]})
            continue
        raw = by_name[name]
        reasons = [f"HARD_GATE_{gate.upper()}" for gate in gates if raw.get(gate) is not True]
        try:
            _hash_text(raw.get("raw_snapshot_sha256"))
        except ValueError:
            reasons.append("HARD_GATE_RAW_SNAPSHOT_SHA256")
        interfaces = raw.get("label_interfaces")
        if interfaces != []:
            reasons.append("HARD_GATE_LABEL_INTERFACE_PRESENT")
        if not isinstance(raw.get("source_inventory"), list) or not raw["source_inventory"]:
            reasons.append("HARD_GATE_SOURCE_INVENTORY")
        if not isinstance(raw.get("field_dictionary"), dict) or not raw["field_dictionary"]:
            reasons.append("HARD_GATE_FIELD_DICTIONARY")
        else:
            available_fields = set(map(str, raw["field_dictionary"]))  # type: ignore[arg-type]
            missing_fields = sorted(DOMAIN_REQUIRED_FIELDS[name] - available_fields)
            if missing_fields:
                reasons.append("HARD_GATE_REQUIRED_FIELDS:" + ",".join(missing_fields))
        timestamps = raw.get("timestamp_fields")
        if not isinstance(timestamps, list) or not {
            "effective_at",
            "available_at",
            "ingested_at",
        }.issubset(set(map(str, timestamps or []))):
            reasons.append("HARD_GATE_TIMESTAMP_FIELDS")
        for field in (
            "revision_policy",
            "proposed_hypothesis",
            "negative_control",
            "primary_horizon",
            "future_trial_budget",
        ):
            if raw.get(field) in (None, "", []):
                reasons.append(f"HARD_GATE_{field.upper()}")
        metrics = {
            key: raw.get(key)
            for key in ("coverage_ratio", "missing_ratio", "median_delay_hours", "revision_completeness")
        }
        passed = not reasons
        evaluations.append({"name": name, "passed": passed, "reason_codes": reasons, "label_free_metrics": metrics})
        if selected is None and passed:
            selected = name
            break
    return OrthogonalDataResult(
        "ORTHOGONAL_DATA_READY_FOR_PREREGISTRATION" if selected else "ORTHOGONAL_DATA_NOT_READY",
        selected,
        tuple(evaluations),
        0,
    )


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _markdown(content: dict[str, object], language: str) -> str:
    zh = language == "zh"
    runtime = content["forward_runtime"]
    domain = content["orthogonal_data"]
    statuses = content["statuses"]
    assert isinstance(runtime, dict) and isinstance(domain, dict) and isinstance(statuses, dict)
    lines = [
        "# V11.2 候选苗圃与前向运行结果" if zh else "# V11.2 Candidate Nursery and Forward Runtime Result",
        "",
        f"- {'运行状态' if zh else 'Run status'}: `{statuses['run_status']}`",
        f"- {'苗圃状态' if zh else 'Nursery state'}: `{statuses['candidate_state']}`",
        f"- {'前向阶段' if zh else 'Forward stage'}: `{runtime['forward_stage']}`",
        f"- {'正交数据' if zh else 'Orthogonal data'}: `{domain['state']}`",
        f"- {'全局 Trial' if zh else 'Global Trials'}: `{content['raw_global_trial_count']}`",
        f"- {'新增推断 Trial' if zh else 'New inferential Trials'}: `0`",
        f"- {'共同可执行日期' if zh else 'Family actionable dates'}: `{len(runtime['family_primary_calendar'])}`",
        "",
        "## 结论" if zh else "## Conclusion",
        "",
        (
            "本版本完成证据治理和可信前向运行能力；没有读取收益标签，也没有发现或验证 Alpha。"
            if zh
            else "This release completes evidence governance and trusted prospective runtime capability; it reads no return labels and discovers or validates no alpha."
        ),
        "",
        (
            "> 若可执行日期不足，这是诚实的前向证据状态，不是工程失败。"
            if zh
            else "> Insufficient actionable dates are an honest evidence state, not an engineering failure."
        ),
        "",
    ]
    return "\n".join(lines)


def run_v112_candidate_nursery(
    *,
    frozen_protocol: str | Path,
    v111_evidence: str | Path,
    clock_manifest: str | Path,
    output_root: str | Path,
    runtime_code_version: str,
    genesis_at: str | None = None,
    collector_id: str = "stephen-quant-v112",
    collector_version: str = V112_VERSION,
    receipts_path: str | Path | None = None,
    domain_inventory_path: str | Path | None = None,
    operation_id: str | None = None,
    created_at: str | None = None,
) -> V112RunReport:
    protocol, reference = load_frozen_protocol(frozen_protocol, runtime_code_version)
    evidence = _load_evidence(v111_evidence)
    clock = load_or_create_clock(
        clock_manifest,
        genesis_at=genesis_at,
        collector_id=collector_id,
        collector_version=collector_version,
    )
    receipts: list[dict[str, object]] = []
    if receipts_path is not None:
        for line in Path(receipts_path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("receipt JSONL rows must be objects")
                receipts.append(value)
    domain_payload = None
    if domain_inventory_path is not None:
        value = json.loads(Path(domain_inventory_path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("domain inventory must be a JSON object")
        domain_payload = value
    nursery = build_nursery(protocol, evidence)
    runtime = evaluate_forward_runtime(protocol, clock, receipts)
    orthogonal = evaluate_orthogonal_domains(domain_payload)
    content: dict[str, object] = {
        "version": V112_VERSION,
        "spec_version": V112_SPEC_VERSION,
        "spec_hash": SPEC_HASH,
        "raw_global_trial_count": RAW_GLOBAL_TRIALS,
        "inferential_trials_added": 0,
        "unauthorized_sealed_label_reads": 0,
        "historical_search_frozen": True,
        "protocol_reference": asdict(reference),
        "nursery": [asdict(item) for item in nursery],
        "nursery_hash": _sha([asdict(item) for item in nursery]),
        "forward_runtime": asdict(runtime),
        "orthogonal_data": asdict(orthogonal),
        "statistical_scope": SPEC_CONTRACT["primary_inference"],
        "statuses": {
            "candidate_state": "CANDIDATE_NURSERY_READY",
            "forward_stage": runtime.forward_stage,
            "orthogonal_data_state": orthogonal.state,
            "run_status": "COMPLETED",
        },
    }
    content_hash = _sha(content)
    created = _parse_time(created_at, "created_at") if created_at else datetime.now(timezone.utc)
    operation = operation_id or f"v112-{uuid.uuid4().hex}"
    if operation in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", operation):
        raise ValueError("operation_id contains unsafe characters")
    envelope_payload = {
        "operation_id": operation,
        "created_at": _utc_text(created),
        "runtime_runner_code_version": runtime_code_version,
        "content_hash": content_hash,
    }
    envelope = {**envelope_payload, "run_envelope_hash": _sha(envelope_payload)}
    report = V112RunReport(content, content_hash, envelope)
    operation_dir = Path(output_root).resolve() / operation
    operation_dir.mkdir(parents=True, exist_ok=False)
    _atomic_write(operation_dir / "V11_2_RESULT.json", report.to_json() + "\n")
    _atomic_write(operation_dir / "V11_2_RESULT.zh.md", _markdown({**content, "content_hash": content_hash}, "zh"))
    _atomic_write(operation_dir / "V11_2_RESULT.en.md", _markdown({**content, "content_hash": content_hash}, "en"))
    _atomic_write(operation_dir / "RUN_ENVELOPE.json", json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report
