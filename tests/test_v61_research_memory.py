from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.discovery.research_memory_v2 import (
    ResearchMemoryEvent,
    append_memory_event,
    replay_memory_ledger,
    summarize_research_memory,
)
from stephen_quant.workflows.v61_research_memory import run_v61_research_memory


def _event(index: int, **overrides) -> ResearchMemoryEvent:
    values = {
        "semantic_identity": f"{index:064x}",
        "proposal_id": f"proposal-{index}",
        "family": "price",
        "stage": "training",
        "outcome": "REJECTED",
        "failure_code": "training_rank_ic",
        "trial_delta": 1,
        "cumulative_trials": index,
        "evidence_snapshot_sha256": f"{1000 + index:064x}",
        "available_at": "2026-08-19T00:00:00Z",
    }
    values.update(overrides)
    return ResearchMemoryEvent(**values)


def test_v61_append_and_replay_hash_chain(tmp_path) -> None:
    path = tmp_path / "memory.jsonl"
    first = append_memory_event(path, _event(1))
    second = append_memory_event(path, _event(2))
    rows = replay_memory_ledger(path)
    assert rows == (first, second)
    assert second.previous_hash == first.entry_hash


def test_v61_renaming_cannot_duplicate_same_semantic_evidence(tmp_path) -> None:
    path = tmp_path / "memory.jsonl"
    event = _event(1)
    append_memory_event(path, event)
    renamed = replace(event, proposal_id="renamed-proposal")
    assert renamed.event_identity == event.event_identity
    with pytest.raises(ValueError, match="already recorded"):
        append_memory_event(path, renamed)


def test_v61_tampering_breaks_replay(tmp_path) -> None:
    path = tmp_path / "memory.jsonl"
    append_memory_event(path, _event(1))
    path.write_text(path.read_text(encoding="utf-8").replace("training_rank_ic", "cost_stress"), encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        replay_memory_ledger(path)


def test_v61_final_test_feedback_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="research-only"):
        append_memory_event(tmp_path / "memory.jsonl", _event(1, evidence_scope="final_test"))


def test_v61_repeated_failure_recommends_repair_then_stop(tmp_path) -> None:
    path = tmp_path / "memory.jsonl"
    for index in range(1, 4):
        append_memory_event(path, _event(index))
    assert summarize_research_memory(path).recommended_action == "REPAIR"
    for index in range(4, 9):
        append_memory_event(path, _event(index))
    assert summarize_research_memory(path).recommended_action == "STOP_FAMILY"


def test_v61_empty_memory_recommends_exploration(tmp_path) -> None:
    summary = summarize_research_memory(tmp_path / "missing.jsonl")
    assert summary.entries == 0
    assert summary.recommended_action == "EXPLORE"


def test_v61_planning_report_is_deterministic_and_trial_free(tmp_path) -> None:
    first = run_v61_research_memory(tmp_path / "first")
    second = run_v61_research_memory(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_RESEARCH_EXPERIENCES"
    assert not first.validation_or_test_feedback_accepted
    assert first.inferential_trial_delta == 0
