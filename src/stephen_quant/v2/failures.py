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
"""


class FailureStore:
    def __init__(self, path: Path) -> None:
        self.path = path
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


def _action_for(failures: tuple[FailureNode, ...], threshold: int) -> tuple[SearchAction, str]:
    codes = {node.code for node in failures}
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
