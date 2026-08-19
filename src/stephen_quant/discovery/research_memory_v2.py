from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

RESEARCH_MEMORY_V2_VERSION = "6.1.0"
_GENESIS = "0" * 64


def _canonical(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class ResearchMemoryEvent:
    semantic_identity: str
    proposal_id: str
    family: str
    stage: str
    outcome: str
    failure_code: str | None
    trial_delta: int
    cumulative_trials: int
    evidence_snapshot_sha256: str
    available_at: str
    parent_semantic_identities: tuple[str, ...] = ()
    evidence_scope: str = "research_only"

    def validate(self) -> None:
        hashes = (
            self.semantic_identity,
            self.evidence_snapshot_sha256,
            *self.parent_semantic_identities,
        )
        if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in hashes):
            raise ValueError("research memory identities must be lowercase SHA-256 values")
        if not all(value.strip() for value in (self.proposal_id, self.family, self.stage, self.outcome)):
            raise ValueError("research memory event text cannot be empty")
        if self.trial_delta < 0 or self.cumulative_trials < self.trial_delta:
            raise ValueError("invalid research memory trial accounting")
        if self.evidence_scope != "research_only":
            raise ValueError("research memory accepts research-only evidence")
        try:
            available = datetime.fromisoformat(self.available_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("research memory available_at must be ISO-8601") from exc
        if available.tzinfo is None or available.utcoffset() != timezone.utc.utcoffset(available):
            raise ValueError("research memory available_at must be explicit UTC")

    @property
    def event_identity(self) -> str:
        self.validate()
        payload = {
            "semantic_identity": self.semantic_identity,
            "stage": self.stage,
            "outcome": self.outcome,
            "failure_code": self.failure_code,
            "evidence_snapshot_sha256": self.evidence_snapshot_sha256,
        }
        return hashlib.sha256(_canonical(payload).encode()).hexdigest()


@dataclass(frozen=True)
class MemoryLedgerRow:
    sequence: int
    event_identity: str
    previous_hash: str
    entry_hash: str
    event: ResearchMemoryEvent


@dataclass(frozen=True)
class FailurePattern:
    family: str
    failure_code: str
    occurrences: int
    unique_semantic_candidates: int
    latest_cumulative_trials: int


@dataclass(frozen=True)
class ResearchMemorySummary:
    memory_version: str
    entries: int
    chain_head: str
    total_recorded_trial_delta: int
    failure_patterns: tuple[FailurePattern, ...]
    recommended_action: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def replay_memory_ledger(path: str | Path) -> tuple[MemoryLedgerRow, ...]:
    ledger = Path(path)
    if not ledger.exists():
        return ()
    rows: list[MemoryLedgerRow] = []
    previous = _GENESIS
    identities: set[str] = set()
    for sequence, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        payload = json.loads(line)
        event_payload = dict(payload["event"])
        event_payload["parent_semantic_identities"] = tuple(
            event_payload.get("parent_semantic_identities", ())
        )
        event = ResearchMemoryEvent(**event_payload)
        event.validate()
        expected_payload = {
            "sequence": sequence,
            "event_identity": event.event_identity,
            "previous_hash": previous,
            "event": asdict(event),
        }
        expected_hash = hashlib.sha256(_canonical(expected_payload).encode()).hexdigest()
        if payload.get("sequence") != sequence or payload.get("previous_hash") != previous:
            raise ValueError("research memory sequence or previous hash mismatch")
        if payload.get("event_identity") != event.event_identity or payload.get("entry_hash") != expected_hash:
            raise ValueError("research memory entry hash mismatch")
        if event.event_identity in identities:
            raise ValueError("research memory contains duplicate semantic evidence")
        identities.add(event.event_identity)
        rows.append(MemoryLedgerRow(sequence, event.event_identity, previous, expected_hash, event))
        previous = expected_hash
    return tuple(rows)


def append_memory_event(path: str | Path, event: ResearchMemoryEvent) -> MemoryLedgerRow:
    event.validate()
    ledger = Path(path).expanduser().resolve()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = replay_memory_ledger(ledger)
    if event.event_identity in {row.event_identity for row in rows}:
        raise ValueError("research memory event already recorded")
    sequence = len(rows) + 1
    previous = rows[-1].entry_hash if rows else _GENESIS
    payload = {
        "sequence": sequence,
        "event_identity": event.event_identity,
        "previous_hash": previous,
        "event": asdict(event),
    }
    entry_hash = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    payload["entry_hash"] = entry_hash
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_canonical(payload) + "\n")
        handle.flush()
    return MemoryLedgerRow(sequence, event.event_identity, previous, entry_hash, event)


def summarize_research_memory(path: str | Path) -> ResearchMemorySummary:
    rows = replay_memory_ledger(path)
    grouped: dict[tuple[str, str], list[ResearchMemoryEvent]] = {}
    for row in rows:
        event = row.event
        if event.failure_code is not None:
            grouped.setdefault((event.family, event.failure_code), []).append(event)
    patterns = tuple(
        FailurePattern(
            family,
            failure,
            len(events),
            len({event.semantic_identity for event in events}),
            max(event.cumulative_trials for event in events),
        )
        for (family, failure), events in sorted(grouped.items())
    )
    worst = max(patterns, key=lambda item: (item.occurrences, item.family), default=None)
    if not rows:
        action = "EXPLORE"
    elif worst is not None and worst.occurrences >= 8:
        action = "STOP_FAMILY"
    elif worst is not None and worst.occurrences >= 3:
        action = "REPAIR"
    else:
        action = "MUTATE_OR_EXPLORE"
    return ResearchMemorySummary(
        RESEARCH_MEMORY_V2_VERSION,
        len(rows),
        rows[-1].entry_hash if rows else _GENESIS,
        sum(row.event.trial_delta for row in rows),
        patterns,
        action,
    )
