from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from stephen_quant.v2 import (
    FAILURE_QUERY_VERSION,
    EpochBudget,
    EpochPolicy,
    FailureCode,
    FailureStore,
    SearchAction,
    plan_next_epoch,
)


def _policy(threshold: int = 3) -> EpochPolicy:
    return EpochPolicy("epoch-policy-1.0.0", threshold)


def _budget() -> EpochBudget:
    return EpochBudget(
        (("exhausted", 3), ("costly", 3), ("mixed", 3), ("clean", 3)),
        candidate_budget=12,
        compute_budget=12,
        token_budget=1200,
        statistical_trial_budget=12,
    )


def _seed(path: Path, *, close: bool = True) -> FailureStore:
    store = FailureStore(path)
    store.start_epoch("epoch_1", 1, _policy(), _budget())
    exhausted_nodes = [
        store.add_failure(
            epoch_id="epoch_1",
            family_id="exhausted",
            candidate_id=f"candidate_{index}",
            stage="cheap_diagnostics",
            code=FailureCode.NO_MARGINAL_VALUE,
            payload={"attempt": index},
        )
        for index in range(3)
    ]
    costly = store.add_failure(
        epoch_id="epoch_1",
        family_id="costly",
        candidate_id="candidate_cost",
        stage="execution",
        code=FailureCode.HIGH_COST,
        payload={"net_spread": -0.001},
    )
    mixed_a = store.add_failure(
        epoch_id="epoch_1",
        family_id="mixed",
        candidate_id="candidate_mixed_a",
        stage="novelty",
        code=FailureCode.DUPLICATE,
        payload={"peer": "reference"},
    )
    mixed_b = store.add_failure(
        epoch_id="epoch_1",
        family_id="mixed",
        candidate_id="candidate_mixed_b",
        stage="cpcv",
        code=FailureCode.CPCV_FAIL,
        payload={"folds": 6},
    )
    store.add_edge(exhausted_nodes[0].node_id, exhausted_nodes[1].node_id, "CAUSED_BY")
    store.add_edge(mixed_a.node_id, mixed_b.node_id, "DERIVED_FROM")
    store.record_event("epoch_1", "FAILURE_RECORDED", costly.node_id, {"code": "HIGH_COST"})
    if close:
        store.close_epoch("epoch_1", {"status": "closed", "sealed_accesses": 0})
    return store


def test_closed_epoch_produces_explainable_deterministic_next_actions(tmp_path: Path) -> None:
    store = _seed(tmp_path / "failure.sqlite3")
    budget, decisions = plan_next_epoch(
        store,
        previous_epoch_id="epoch_1",
        next_epoch_id="epoch_2",
        next_epoch_index=2,
        families=("mixed", "clean", "costly", "exhausted"),
        base_family_budget=4,
    )
    by_family = {decision.family_id: decision for decision in decisions}
    assert by_family["exhausted"].action == SearchAction.STOP_FAMILY
    assert by_family["exhausted"].allocated_budget == 0
    assert by_family["exhausted"].reason_code == "FAMILY_EXHAUSTED"
    assert by_family["costly"].action == SearchAction.MUTATE
    assert by_family["mixed"].action == SearchAction.RECOMBINE
    assert by_family["clean"].action == SearchAction.EXPLOIT
    assert dict(budget.family_budgets)["exhausted"] == 0

    replay_store = _seed(tmp_path / "replay.sqlite3")
    replay_budget, replay_decisions = plan_next_epoch(
        replay_store,
        previous_epoch_id="epoch_1",
        next_epoch_id="epoch_2",
        next_epoch_index=2,
        families=("exhausted", "costly", "clean", "mixed"),
        base_family_budget=4,
    )
    assert replay_budget == budget
    assert replay_decisions == decisions


def test_policy_cannot_adapt_inside_open_epoch(tmp_path: Path) -> None:
    store = _seed(tmp_path / "open.sqlite3", close=False)
    store.assert_epoch_policy("epoch_1", _policy())
    with pytest.raises(ValueError, match="policy is frozen"):
        store.assert_epoch_policy("epoch_1", EpochPolicy("changed", 1))
    with pytest.raises(ValueError, match="before previous epoch is closed"):
        plan_next_epoch(
            store,
            previous_epoch_id="epoch_1",
            next_epoch_id="epoch_2",
            next_epoch_index=2,
            families=("exhausted",),
            base_family_budget=1,
        )


def test_failure_graph_and_decisions_are_append_only(tmp_path: Path) -> None:
    store = _seed(tmp_path / "append.sqlite3")
    plan_next_epoch(
        store,
        previous_epoch_id="epoch_1",
        next_epoch_id="epoch_2",
        next_epoch_index=2,
        families=("exhausted",),
        base_family_budget=1,
    )
    statements = (
        "UPDATE failure_nodes SET code = 'CPCV_FAIL'",
        "DELETE FROM failure_nodes",
        "UPDATE research_epochs SET policy_sha256 = 'changed'",
        "DELETE FROM epoch_decisions",
    )
    for statement in statements:
        with store.connect() as conn, pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(statement)


def test_versioned_failure_query_rejects_unknown_interface(tmp_path: Path) -> None:
    store = _seed(tmp_path / "query.sqlite3")
    failures = store.failures_for_family(
        "epoch_1", "exhausted", query_version=FAILURE_QUERY_VERSION
    )
    assert len(failures) == 3
    assert tuple(node.node_id for node in failures) == tuple(
        sorted(node.node_id for node in failures)
    )
    with pytest.raises(ValueError, match="unsupported failure query version"):
        store.failures_for_family("epoch_1", "exhausted", query_version="future")
