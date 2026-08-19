from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, pstdev

FORWARD_SHADOW_VERSION = "6.3.0"
_GENESIS = "0" * 64


def _canonical(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be lowercase SHA-256")


@dataclass(frozen=True)
class ForwardShadowProtocol:
    candidate_semantic_identity: str
    frozen_through: str
    required_sources: tuple[str, ...]
    cost_model_sha256: str
    portfolio_config_sha256: str
    minimum_new_sessions: int = 25

    def validate(self) -> None:
        _sha(self.candidate_semantic_identity, "candidate identity")
        _sha(self.cost_model_sha256, "cost model")
        _sha(self.portfolio_config_sha256, "portfolio config")
        try:
            date.fromisoformat(self.frozen_through)
        except ValueError as exc:
            raise ValueError("frozen_through must be an ISO date") from exc
        if self.minimum_new_sessions < 25:
            raise ValueError("forward shadow requires at least 25 genuinely new sessions")
        if not self.required_sources or len(set(self.required_sources)) != len(self.required_sources):
            raise ValueError("forward shadow requires unique source names")

    @property
    def protocol_id(self) -> str:
        self.validate()
        return hashlib.sha256(_canonical(asdict(self)).encode()).hexdigest()


@dataclass(frozen=True)
class ForwardShadowObservation:
    protocol_id: str
    session: str
    source_snapshot_sha256: tuple[tuple[str, str], ...]
    standard_net_excess_return: float
    double_cost_net_excess_return: float
    available_at: str

    def validate(self, protocol: ForwardShadowProtocol) -> None:
        if self.protocol_id != protocol.protocol_id:
            raise ValueError("forward observation is not bound to the protocol")
        try:
            session = date.fromisoformat(self.session)
            available = datetime.fromisoformat(self.available_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("forward observation dates must be ISO-8601") from exc
        if self.session <= protocol.frozen_through:
            raise ValueError("forward observation must be strictly after the frozen window")
        if available.tzinfo is None or available.utcoffset() != timezone.utc.utcoffset(available):
            raise ValueError("forward observation available_at must be UTC")
        if available.date() < session:
            raise ValueError("forward observation cannot be available before its session")
        if tuple(source for source, _ in self.source_snapshot_sha256) != tuple(
            sorted(protocol.required_sources)
        ):
            raise ValueError("forward observation must contain every required source exactly once")
        for source, value in self.source_snapshot_sha256:
            _sha(value, f"source snapshot {source}")
        returns = (self.standard_net_excess_return, self.double_cost_net_excess_return)
        if any(not math.isfinite(value) or value <= -1 for value in returns):
            raise ValueError("forward returns must be finite and greater than -100%")


@dataclass(frozen=True)
class ForwardLedgerRow:
    sequence: int
    previous_hash: str
    entry_hash: str
    observation: ForwardShadowObservation


@dataclass(frozen=True)
class ForwardShadowSummary:
    method_version: str
    protocol_id: str
    sessions: int
    first_session: str | None
    last_session: str | None
    standard_cumulative_excess: float | None
    double_cost_cumulative_excess: float | None
    standard_annualized_sharpe: float | None
    double_cost_annualized_sharpe: float | None
    ledger_head: str
    decision: str
    inferential_trial_delta: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def replay_forward_ledger(
    path: str | Path, protocol: ForwardShadowProtocol
) -> tuple[ForwardLedgerRow, ...]:
    protocol.validate()
    ledger = Path(path)
    if not ledger.exists():
        return ()
    rows: list[ForwardLedgerRow] = []
    previous = _GENESIS
    last_session: str | None = None
    for sequence, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        payload = json.loads(line)
        observation_payload = dict(payload["observation"])
        observation_payload["source_snapshot_sha256"] = tuple(
            tuple(item) for item in observation_payload["source_snapshot_sha256"]
        )
        observation = ForwardShadowObservation(**observation_payload)
        observation.validate(protocol)
        if last_session is not None and observation.session <= last_session:
            raise ValueError("forward observations must be strictly append-only by session")
        row_payload = {
            "sequence": sequence,
            "previous_hash": previous,
            "observation": asdict(observation),
        }
        entry_hash = hashlib.sha256(_canonical(row_payload).encode()).hexdigest()
        if payload.get("sequence") != sequence or payload.get("previous_hash") != previous:
            raise ValueError("forward ledger sequence or previous hash mismatch")
        if payload.get("entry_hash") != entry_hash:
            raise ValueError("forward ledger entry hash mismatch")
        rows.append(ForwardLedgerRow(sequence, previous, entry_hash, observation))
        previous, last_session = entry_hash, observation.session
    return tuple(rows)


def append_forward_observation(
    path: str | Path,
    protocol: ForwardShadowProtocol,
    observation: ForwardShadowObservation,
) -> ForwardLedgerRow:
    observation.validate(protocol)
    ledger = Path(path).expanduser().resolve()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    rows = replay_forward_ledger(ledger, protocol)
    if rows and observation.session <= rows[-1].observation.session:
        raise ValueError("forward observation session is duplicate or out of order")
    sequence = len(rows) + 1
    previous = rows[-1].entry_hash if rows else _GENESIS
    payload = {
        "sequence": sequence,
        "previous_hash": previous,
        "observation": asdict(observation),
    }
    entry_hash = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    payload["entry_hash"] = entry_hash
    with ledger.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_canonical(payload) + "\n")
        handle.flush()
    return ForwardLedgerRow(sequence, previous, entry_hash, observation)


def _cumulative(values: tuple[float, ...]) -> float:
    wealth = 1.0
    for value in values:
        wealth *= 1 + value
    return wealth - 1


def _sharpe(values: tuple[float, ...]) -> float:
    deviation = pstdev(values)
    return 0.0 if deviation == 0 else mean(values) / deviation * math.sqrt(252)


def summarize_forward_shadow(
    path: str | Path, protocol: ForwardShadowProtocol
) -> ForwardShadowSummary:
    rows = replay_forward_ledger(path, protocol)
    if len(rows) < protocol.minimum_new_sessions:
        return ForwardShadowSummary(
            FORWARD_SHADOW_VERSION,
            protocol.protocol_id,
            len(rows),
            rows[0].observation.session if rows else None,
            rows[-1].observation.session if rows else None,
            None,
            None,
            None,
            None,
            rows[-1].entry_hash if rows else _GENESIS,
            "WAITING_FOR_FORWARD_DATA",
            0,
        )
    standard = tuple(row.observation.standard_net_excess_return for row in rows)
    doubled = tuple(row.observation.double_cost_net_excess_return for row in rows)
    return ForwardShadowSummary(
        FORWARD_SHADOW_VERSION,
        protocol.protocol_id,
        len(rows),
        rows[0].observation.session,
        rows[-1].observation.session,
        _cumulative(standard),
        _cumulative(doubled),
        _sharpe(standard),
        _sharpe(doubled),
        rows[-1].entry_hash,
        "FORWARD_EVIDENCE_READY",
        0,
    )
