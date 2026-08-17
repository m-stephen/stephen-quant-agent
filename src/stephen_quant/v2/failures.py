from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

FAILURE_QUERY_VERSION = "failure-query-1.0.0"


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


class FailureCode(str, Enum):
    DUPLICATE = "DUPLICATE"
    LOW_COVERAGE = "LOW_COVERAGE"
    STALE_SIGNAL = "STALE_SIGNAL"
    NO_MARGINAL_VALUE = "NO_MARGINAL_VALUE"
    HIGH_COST = "HIGH_COST"
    CPCV_FAIL = "CPCV_FAIL"
    PLACEBO_FAIL = "PLACEBO_FAIL"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TEMPORAL_NON_GENERALIZATION = "TEMPORAL_NON_GENERALIZATION"
    PLACEBO_FAILURE_OOS = "PLACEBO_FAILURE_OOS"
    RETURN_CONCENTRATION = "RETURN_CONCENTRATION"
    DSR_FAILURE = "DSR_FAILURE"
    POLICY_OVERFIT_RISK = "POLICY_OVERFIT_RISK"


class SearchAction(str, Enum):
    EXPLORE = "EXPLORE"
    EXPLOIT = "EXPLOIT"
    MUTATE = "MUTATE"
    RECOMBINE = "RECOMBINE"
    STOP_FAMILY = "STOP_FAMILY"


@dataclass(frozen=True)
class FailureNode:
    node_id: str
    epoch_id: str
    family_id: str
    candidate_id: str
    stage: str
    code: FailureCode
    payload_json: str
    payload_sha256: str


@dataclass(frozen=True)
class EpochPolicy:
    version: str
    exhaustion_threshold: int
    permitted_actions: tuple[SearchAction, ...] = (
        SearchAction.EXPLORE,
        SearchAction.EXPLOIT,
        SearchAction.MUTATE,
        SearchAction.RECOMBINE,
        SearchAction.STOP_FAMILY,
    )

    def validate(self) -> None:
        if not self.version.strip() or self.exhaustion_threshold < 1:
            raise ValueError("epoch policy requires version and positive exhaustion threshold")
        if len(self.permitted_actions) != len(set(self.permitted_actions)):
            raise ValueError("epoch permitted actions must be unique")

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(asdict(self))


@dataclass(frozen=True)
class EpochBudget:
    family_budgets: tuple[tuple[str, int], ...]
    candidate_budget: int
    compute_budget: int
    token_budget: int
    statistical_trial_budget: int

    def validate(self) -> None:
        families = [family for family, _ in self.family_budgets]
        if len(families) != len(set(families)) or any(
            not family or value < 0 for family, value in self.family_budgets
        ):
            raise ValueError("family budgets must be unique and non-negative")
        if any(
            value < 0
            for value in (
                self.candidate_budget,
                self.compute_budget,
                self.token_budget,
                self.statistical_trial_budget,
            )
        ):
            raise ValueError("epoch budgets cannot be negative")

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(asdict(self))


@dataclass(frozen=True)
class EpochDecision:
    epoch_id: str
    family_id: str
    action: SearchAction
    allocated_budget: int
    reason_code: str
    source_failure_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class FamilySignature:
    mechanism_id: str
    data_semantics: tuple[str, ...]
    information_set: tuple[str, ...]
    economic_claim: str
    signal_direction: str

    def validate(self) -> None:
        if any(
            not value.strip()
            for value in (self.mechanism_id, self.economic_claim, self.signal_direction)
        ):
            raise ValueError("family signature contains empty identity data")
        for name, values in (
            ("data semantics", self.data_semantics),
            ("information set", self.information_set),
        ):
            if not values or any(not value.strip() for value in values):
                raise ValueError(f"family signature {name} cannot be empty")
            if len(values) != len(set(values)):
                raise ValueError(f"family signature {name} must be unique")

    def canonical_payload(self) -> dict[str, object]:
        self.validate()
        return {
            "mechanism_id": self.mechanism_id,
            "data_semantics": sorted(self.data_semantics),
            "information_set": sorted(self.information_set),
            "economic_claim": self.economic_claim,
            "signal_direction": self.signal_direction,
        }

    @property
    def sha256(self) -> str:
        return _sha(self.canonical_payload())


@dataclass(frozen=True)
class VariantSignature:
    family: FamilySignature
    expression_family: str
    primary_horizon: int
    secondary_horizon: int | None
    transformation_lineage: tuple[str, ...]
    portfolio_wrapper: str
    policy_wrapper: str

    def validate(self) -> None:
        self.family.validate()
        if not self.expression_family.strip() or self.primary_horizon < 1:
            raise ValueError("variant signature requires expression and primary horizon")
        if self.secondary_horizon is not None and self.secondary_horizon < 1:
            raise ValueError("secondary horizon must be positive")
        if self.secondary_horizon == self.primary_horizon:
            raise ValueError("secondary horizon must differ from primary horizon")
        if not self.transformation_lineage or any(
            not value.strip() for value in self.transformation_lineage
        ):
            raise ValueError("variant transformation lineage cannot be empty")
        if not self.portfolio_wrapper.strip() or not self.policy_wrapper.strip():
            raise ValueError("variant wrappers cannot be empty")

    @property
    def sha256(self) -> str:
        self.validate()
        return _sha(
            {
                "family_sha256": self.family.sha256,
                "expression_family": self.expression_family,
                "primary_horizon": self.primary_horizon,
                "secondary_horizon": self.secondary_horizon,
                "transformation_lineage": list(self.transformation_lineage),
                "portfolio_wrapper": self.portfolio_wrapper,
                "policy_wrapper": self.policy_wrapper,
            }
        )


@dataclass(frozen=True)
class FamilyTombstone:
    tombstone_id: str
    family_sha256: str
    reason_code: str
    authority: str
    source_failure_node_ids: tuple[str, ...]
    recorded_at: str


@dataclass(frozen=True)
class TombstoneDecision:
    family_sha256: str
    variant_sha256: str
    action: SearchAction
    reason_code: str
    tombstone_id: str | None


class WindowState(str, Enum):
    SEALED_VALIDATION = "SEALED_VALIDATION"
    CONSUMED_VALIDATION = "CONSUMED_VALIDATION"
    SEALED_FINAL_TEST = "SEALED_FINAL_TEST"


@dataclass(frozen=True)
class WindowStateEvent:
    event_id: str
    window_id: str
    event_index: int
    previous_state: WindowState
    new_state: WindowState
    authority: str
    source_artifact_sha256: str
    recorded_at: str
    payload_sha256: str


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS research_epochs (
    epoch_id TEXT PRIMARY KEY,
    epoch_index INTEGER NOT NULL UNIQUE,
    parent_epoch_id TEXT,
    policy_json TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    budget_sha256 TEXT NOT NULL,
    FOREIGN KEY(parent_epoch_id) REFERENCES research_epochs(epoch_id)
);
CREATE TABLE IF NOT EXISTS epoch_closures (
    epoch_id TEXT PRIMARY KEY,
    closure_payload_json TEXT NOT NULL,
    closure_sha256 TEXT NOT NULL,
    FOREIGN KEY(epoch_id) REFERENCES research_epochs(epoch_id)
);
CREATE TABLE IF NOT EXISTS failure_nodes (
    node_id TEXT PRIMARY KEY,
    epoch_id TEXT NOT NULL,
    family_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    FOREIGN KEY(epoch_id) REFERENCES research_epochs(epoch_id)
);
CREATE TABLE IF NOT EXISTS failure_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    FOREIGN KEY(source_node_id) REFERENCES failure_nodes(node_id),
    FOREIGN KEY(target_node_id) REFERENCES failure_nodes(node_id)
);
CREATE TABLE IF NOT EXISTS failure_events (
    event_id TEXT PRIMARY KEY,
    epoch_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    FOREIGN KEY(epoch_id) REFERENCES research_epochs(epoch_id)
);
CREATE TABLE IF NOT EXISTS epoch_decisions (
    decision_id TEXT PRIMARY KEY,
    epoch_id TEXT NOT NULL,
    family_id TEXT NOT NULL,
    action TEXT NOT NULL,
    allocated_budget INTEGER NOT NULL,
    reason_code TEXT NOT NULL,
    source_failure_node_ids_json TEXT NOT NULL,
    FOREIGN KEY(epoch_id) REFERENCES research_epochs(epoch_id),
    UNIQUE(epoch_id, family_id)
);
CREATE TABLE IF NOT EXISTS family_tombstones (
    tombstone_id TEXT PRIMARY KEY,
    family_sha256 TEXT NOT NULL UNIQUE,
    family_signature_json TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    authority TEXT NOT NULL,
    source_failure_node_ids_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS window_state_events (
    event_id TEXT PRIMARY KEY,
    window_id TEXT NOT NULL,
    event_index INTEGER NOT NULL,
    previous_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    authority TEXT NOT NULL,
    source_artifact_sha256 TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    UNIQUE(window_id, event_index)
);
CREATE TRIGGER IF NOT EXISTS research_epochs_no_update BEFORE UPDATE ON research_epochs
BEGIN SELECT RAISE(ABORT, 'research epochs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS research_epochs_no_delete BEFORE DELETE ON research_epochs
BEGIN SELECT RAISE(ABORT, 'research epochs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_nodes_no_update BEFORE UPDATE ON failure_nodes
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_nodes_no_delete BEFORE DELETE ON failure_nodes
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_edges_no_update BEFORE UPDATE ON failure_edges
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_edges_no_delete BEFORE DELETE ON failure_edges
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_events_no_update BEFORE UPDATE ON failure_events
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS failure_events_no_delete BEFORE DELETE ON failure_events
BEGIN SELECT RAISE(ABORT, 'failure graph is append-only'); END;
CREATE TRIGGER IF NOT EXISTS epoch_decisions_no_update BEFORE UPDATE ON epoch_decisions
BEGIN SELECT RAISE(ABORT, 'epoch decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS epoch_decisions_no_delete BEFORE DELETE ON epoch_decisions
BEGIN SELECT RAISE(ABORT, 'epoch decisions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS epoch_closures_no_update BEFORE UPDATE ON epoch_closures
BEGIN SELECT RAISE(ABORT, 'epoch closures are append-only'); END;
CREATE TRIGGER IF NOT EXISTS epoch_closures_no_delete BEFORE DELETE ON epoch_closures
BEGIN SELECT RAISE(ABORT, 'epoch closures are append-only'); END;
CREATE TRIGGER IF NOT EXISTS family_tombstones_no_update BEFORE UPDATE ON family_tombstones
BEGIN SELECT RAISE(ABORT, 'family tombstones are append-only'); END;
CREATE TRIGGER IF NOT EXISTS family_tombstones_no_delete BEFORE DELETE ON family_tombstones
BEGIN SELECT RAISE(ABORT, 'family tombstones are append-only'); END;
CREATE TRIGGER IF NOT EXISTS window_state_events_no_update BEFORE UPDATE ON window_state_events
BEGIN SELECT RAISE(ABORT, 'window state events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS window_state_events_no_delete BEFORE DELETE ON window_state_events
BEGIN SELECT RAISE(ABORT, 'window state events are append-only'); END;
"""


class FailureStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def start_epoch(
        self,
        epoch_id: str,
        epoch_index: int,
        policy: EpochPolicy,
        budget: EpochBudget,
        parent_epoch_id: str | None = None,
    ) -> None:
        policy.validate()
        budget.validate()
        with self.connect() as conn:
            if (
                parent_epoch_id is not None
                and conn.execute(
                    "SELECT 1 FROM epoch_closures WHERE epoch_id = ?", (parent_epoch_id,)
                ).fetchone()
                is None
            ):
                raise ValueError("parent epoch must be closed before starting the next epoch")
            conn.execute(
                "INSERT INTO research_epochs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    epoch_id,
                    epoch_index,
                    parent_epoch_id,
                    _canonical(asdict(policy)),
                    policy.sha256,
                    _canonical(asdict(budget)),
                    budget.sha256,
                ),
            )

    def assert_epoch_policy(self, epoch_id: str, policy: EpochPolicy) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT policy_sha256 FROM research_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
        if row is None or row[0] != policy.sha256:
            raise ValueError("epoch policy is frozen and does not match")

    def close_epoch(self, epoch_id: str, payload: dict[str, object]) -> None:
        encoded = _canonical(payload)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO epoch_closures VALUES (?, ?, ?)",
                (epoch_id, encoded, hashlib.sha256(encoded.encode()).hexdigest()),
            )

    def is_closed(self, epoch_id: str) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM epoch_closures WHERE epoch_id = ?", (epoch_id,)
                ).fetchone()
                is not None
            )

    def add_failure(
        self,
        *,
        epoch_id: str,
        family_id: str,
        candidate_id: str,
        stage: str,
        code: FailureCode,
        payload: dict[str, object],
    ) -> FailureNode:
        encoded = _canonical(payload)
        payload_sha = hashlib.sha256(encoded.encode()).hexdigest()
        identity = {
            "epoch": epoch_id,
            "family": family_id,
            "candidate": candidate_id,
            "stage": stage,
            "code": code.value,
            "payload_sha": payload_sha,
        }
        node_id = f"failure_{_sha(identity)[:24]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO failure_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    node_id,
                    epoch_id,
                    family_id,
                    candidate_id,
                    stage,
                    code.value,
                    encoded,
                    payload_sha,
                ),
            )
        return FailureNode(
            node_id, epoch_id, family_id, candidate_id, stage, code, encoded, payload_sha
        )

    def add_edge(self, source_node_id: str, target_node_id: str, relation: str) -> str:
        if relation not in {"DERIVED_FROM", "CAUSED_BY", "REVISES", "EXHAUSTS"}:
            raise ValueError("unsupported failure graph relation")
        edge_id = f"edge_{_sha((source_node_id, target_node_id, relation))[:24]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO failure_edges VALUES (?, ?, ?, ?)",
                (edge_id, source_node_id, target_node_id, relation),
            )
        return edge_id

    def record_event(
        self, epoch_id: str, event_type: str, subject_id: str, payload: dict[str, object]
    ) -> str:
        if not event_type.strip() or not subject_id.strip():
            raise ValueError("failure event type and subject are required")
        encoded = _canonical(payload)
        payload_sha = hashlib.sha256(encoded.encode()).hexdigest()
        event_id = f"event_{_sha((epoch_id, event_type, subject_id, payload_sha))[:24]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO failure_events VALUES (?, ?, ?, ?, ?, ?)",
                (event_id, epoch_id, event_type, subject_id, encoded, payload_sha),
            )
        return event_id

    def failures_for_family(
        self, epoch_id: str, family_id: str, *, query_version: str = FAILURE_QUERY_VERSION
    ) -> tuple[FailureNode, ...]:
        if query_version != FAILURE_QUERY_VERSION:
            raise ValueError("unsupported failure query version")
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT node_id, epoch_id, family_id, candidate_id, stage, code, "
                "payload_json, payload_sha256 FROM failure_nodes "
                "WHERE epoch_id = ? AND family_id = ? ORDER BY node_id",
                (epoch_id, family_id),
            ).fetchall()
        return tuple(
            FailureNode(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                FailureCode(str(row[5])),
                str(row[6]),
                str(row[7]),
            )
            for row in rows
        )

    def epoch_policy(self, epoch_id: str) -> EpochPolicy:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT policy_json FROM research_epochs WHERE epoch_id = ?", (epoch_id,)
            ).fetchone()
        if row is None:
            raise ValueError("unknown research epoch")
        payload = json.loads(row[0])
        return EpochPolicy(
            payload["version"],
            int(payload["exhaustion_threshold"]),
            tuple(SearchAction(value) for value in payload["permitted_actions"]),
        )

    def record_decision(self, decision: EpochDecision) -> str:
        payload = asdict(decision)
        decision_id = f"decision_{_sha(payload)[:24]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO epoch_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    decision_id,
                    decision.epoch_id,
                    decision.family_id,
                    decision.action.value,
                    decision.allocated_budget,
                    decision.reason_code,
                    _canonical(decision.source_failure_node_ids),
                ),
            )
        return decision_id

    def record_family_tombstone(
        self,
        signature: FamilySignature,
        *,
        reason_code: str,
        authority: str,
        source_failure_node_ids: tuple[str, ...],
        recorded_at: str,
    ) -> FamilyTombstone:
        signature.validate()
        if any(not value.strip() for value in (reason_code, authority, recorded_at)):
            raise ValueError("tombstone reason, authority and timestamp are required")
        if not source_failure_node_ids or len(source_failure_node_ids) != len(
            set(source_failure_node_ids)
        ):
            raise ValueError("tombstone failure nodes must be non-empty and unique")
        with self.connect() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM failure_nodes WHERE node_id IN "
                f"({','.join('?' for _ in source_failure_node_ids)})",
                source_failure_node_ids,
            ).fetchone()[0]
            if int(count) != len(source_failure_node_ids):
                raise ValueError("tombstone references unknown failure nodes")
            payload = {
                "family": signature.canonical_payload(),
                "reason_code": reason_code,
                "authority": authority,
                "source_failure_node_ids": list(source_failure_node_ids),
                "recorded_at": recorded_at,
            }
            payload_sha = _sha(payload)
            tombstone_id = f"tombstone_{_sha((signature.sha256, payload_sha))[:24]}"
            conn.execute(
                "INSERT INTO family_tombstones VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tombstone_id,
                    signature.sha256,
                    _canonical(signature.canonical_payload()),
                    reason_code,
                    authority,
                    _canonical(source_failure_node_ids),
                    recorded_at,
                    payload_sha,
                ),
            )
        return FamilyTombstone(
            tombstone_id,
            signature.sha256,
            reason_code,
            authority,
            source_failure_node_ids,
            recorded_at,
        )

    def tombstone_decision(self, variant: VariantSignature) -> TombstoneDecision:
        variant.validate()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT tombstone_id, reason_code FROM family_tombstones "
                "WHERE family_sha256 = ?",
                (variant.family.sha256,),
            ).fetchone()
        if row is None:
            return TombstoneDecision(
                variant.family.sha256,
                variant.sha256,
                SearchAction.EXPLORE,
                "MECHANISM_NOT_TOMBSTONED",
                None,
            )
        return TombstoneDecision(
            variant.family.sha256,
            variant.sha256,
            SearchAction.STOP_FAMILY,
            str(row[1]),
            str(row[0]),
        )

    def record_window_state(
        self,
        *,
        window_id: str,
        previous_state: WindowState,
        new_state: WindowState,
        authority: str,
        source_artifact_sha256: str,
        recorded_at: str,
    ) -> WindowStateEvent:
        if any(not value.strip() for value in (window_id, authority, recorded_at)):
            raise ValueError("window event identity, authority and timestamp are required")
        if len(source_artifact_sha256) != 64:
            raise ValueError("window event source artifact requires SHA-256")
        allowed = {
            (WindowState.SEALED_VALIDATION, WindowState.CONSUMED_VALIDATION),
            (WindowState.CONSUMED_VALIDATION, WindowState.CONSUMED_VALIDATION),
            (WindowState.SEALED_FINAL_TEST, WindowState.SEALED_FINAL_TEST),
        }
        if (previous_state, new_state) not in allowed:
            raise ValueError("window state transition is not permitted")
        with self.connect() as conn:
            latest = conn.execute(
                "SELECT event_index, new_state FROM window_state_events "
                "WHERE window_id = ? ORDER BY event_index DESC LIMIT 1",
                (window_id,),
            ).fetchone()
            if latest is not None and WindowState(str(latest[1])) != previous_state:
                raise ValueError("window previous state does not match append-only history")
            event_index = 1 if latest is None else int(latest[0]) + 1
            payload = {
                "window_id": window_id,
                "event_index": event_index,
                "previous_state": previous_state.value,
                "new_state": new_state.value,
                "authority": authority,
                "source_artifact_sha256": source_artifact_sha256,
                "recorded_at": recorded_at,
            }
            payload_sha = _sha(payload)
            event_id = f"window_{_sha((window_id, event_index, payload_sha))[:24]}"
            conn.execute(
                "INSERT INTO window_state_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    window_id,
                    event_index,
                    previous_state.value,
                    new_state.value,
                    authority,
                    source_artifact_sha256,
                    recorded_at,
                    payload_sha,
                ),
            )
        return WindowStateEvent(
            event_id,
            window_id,
            event_index,
            previous_state,
            new_state,
            authority,
            source_artifact_sha256,
            recorded_at,
            payload_sha,
        )

    def window_state_events(self, window_id: str) -> tuple[WindowStateEvent, ...]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT event_id, window_id, event_index, previous_state, new_state, "
                "authority, source_artifact_sha256, recorded_at, payload_sha256 "
                "FROM window_state_events WHERE window_id = ? ORDER BY event_index",
                (window_id,),
            ).fetchall()
        return tuple(
            WindowStateEvent(
                str(row[0]),
                str(row[1]),
                int(row[2]),
                WindowState(str(row[3])),
                WindowState(str(row[4])),
                str(row[5]),
                str(row[6]),
                str(row[7]),
                str(row[8]),
            )
            for row in rows
        )


def _action_for(failures: tuple[FailureNode, ...], threshold: int) -> tuple[SearchAction, str]:
    codes = {node.code for node in failures}
    independent_validation_codes = {
        FailureCode.TEMPORAL_NON_GENERALIZATION,
        FailureCode.PLACEBO_FAILURE_OOS,
        FailureCode.RETURN_CONCENTRATION,
        FailureCode.DSR_FAILURE,
        FailureCode.POLICY_OVERFIT_RISK,
    }
    if any(
        node.stage == "independent_validation" and node.code in independent_validation_codes
        for node in failures
    ):
        return SearchAction.STOP_FAMILY, "VALIDATION_FAIL_STOP"
    if len(failures) >= threshold or FailureCode.BUDGET_EXHAUSTED in codes:
        return SearchAction.STOP_FAMILY, "FAMILY_EXHAUSTED"
    if len(codes) >= 2:
        return SearchAction.RECOMBINE, "MULTI_FAILURE_RECOMBINATION"
    if codes & {FailureCode.NO_MARGINAL_VALUE, FailureCode.HIGH_COST, FailureCode.DUPLICATE}:
        return SearchAction.MUTATE, "TARGETED_SINGLE_DIMENSION_REVISION"
    if codes & {FailureCode.CPCV_FAIL, FailureCode.PLACEBO_FAIL}:
        return SearchAction.EXPLORE, "NEW_MECHANISM_REQUIRED"
    if codes & {FailureCode.LOW_COVERAGE, FailureCode.STALE_SIGNAL}:
        return SearchAction.STOP_FAMILY, "DATA_NOT_RESEARCH_READY"
    return SearchAction.EXPLOIT, "NO_RECORDED_FAILURE"


def plan_next_epoch(
    store: FailureStore,
    *,
    previous_epoch_id: str,
    next_epoch_id: str,
    next_epoch_index: int,
    families: tuple[str, ...],
    base_family_budget: int,
    next_policy: EpochPolicy | None = None,
) -> tuple[EpochBudget, tuple[EpochDecision, ...]]:
    if not store.is_closed(previous_epoch_id):
        raise ValueError("cannot adapt policy before previous epoch is closed")
    previous_policy = store.epoch_policy(previous_epoch_id)
    policy = next_policy or previous_policy
    policy.validate()
    decisions: list[EpochDecision] = []
    family_budgets: list[tuple[str, int]] = []
    for family in sorted(set(families)):
        failures = store.failures_for_family(previous_epoch_id, family)
        action, reason = _action_for(failures, previous_policy.exhaustion_threshold)
        if action not in policy.permitted_actions:
            action, reason = SearchAction.STOP_FAMILY, "ACTION_NOT_PERMITTED"
        allocated = 0 if action == SearchAction.STOP_FAMILY else base_family_budget
        family_budgets.append((family, allocated))
        decisions.append(
            EpochDecision(
                next_epoch_id,
                family,
                action,
                allocated,
                reason,
                tuple(node.node_id for node in failures),
            )
        )
    total = sum(value for _, value in family_budgets)
    budget = EpochBudget(tuple(family_budgets), total, total, total * 100, total)
    store.start_epoch(
        next_epoch_id, next_epoch_index, policy, budget, parent_epoch_id=previous_epoch_id
    )
    for decision in decisions:
        store.record_decision(decision)
    return budget, tuple(decisions)
