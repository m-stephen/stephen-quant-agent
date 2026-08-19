from __future__ import annotations

import json

import pytest

from stephen_quant.discovery.proposal_generator import (
    compile_proposal,
    generate_symbolic_proposals,
    load_llm_proposals,
    merge_proposals,
)
from stephen_quant.workflows.v57_proposal_generator import run_v57_proposal_generator


def test_v57_symbolic_generation_is_deterministic_and_bounded() -> None:
    first = generate_symbolic_proposals(budget=40)
    second = generate_symbolic_proposals(budget=40)
    assert [item.proposal_id for item in first] == [item.proposal_id for item in second]
    assert len(first) == 40
    assert all(item.typed.lookback_periods <= 252 for item in first)


def test_v57_symbolic_generation_has_ranking_and_event_proposals() -> None:
    proposals = generate_symbolic_proposals(budget=256)
    assert {item.typed.research_form for item in proposals} >= {"continuous_ranking", "event_study"}
    assert {item.proposal.origin for item in proposals} == {"symbolic"}


def test_v70_direction_complete_generation_pairs_each_formula() -> None:
    one_sided = generate_symbolic_proposals(budget=512)
    proposals = generate_symbolic_proposals(budget=512, include_inverse=True)
    by_formula = {}
    for item in proposals:
        by_formula.setdefault(item.schema.formula, set()).add(item.schema.direction)
    assert len(proposals) == 2 * len(one_sided)
    assert all(directions == {-1, 1} for directions in by_formula.values())
    assert {item.proposal.provider_id for item in proposals} >= {
        "symbolic:price-return",
        "symbolic:price-risk",
    }


def test_v57_llm_packet_is_untrusted_and_typed(tmp_path) -> None:
    path = tmp_path / "llm.json"
    path.write_text(
        json.dumps(
            [
                {
                    "formula": "mean(margin_financing_buy, 5) / (mean(amount, 5) + 1)",
                    "hypothesis": "Leverage demand normalized by traded amount may proxy pressure.",
                    "research_form": "continuous_ranking",
                    "horizon": "5d",
                    "direction": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    proposals = load_llm_proposals(path, provider_id="llm:test-provider")
    assert len(proposals) == 1
    assert proposals[0].proposal.origin == "llm"
    assert proposals[0].typed.output.unit == "ratio"


def test_v57_llm_packet_rejects_extra_control_fields(tmp_path) -> None:
    path = tmp_path / "unsafe.json"
    path.write_text(
        json.dumps(
            [
                {
                    "formula": "mean(close, 5)",
                    "hypothesis": "x",
                    "research_form": "continuous_ranking",
                    "horizon": "5d",
                    "direction": 1,
                    "python": "open('secret')",
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly"):
        load_llm_proposals(path, provider_id="llm:test-provider")


def test_v57_merge_deduplicates_across_origins(tmp_path) -> None:
    symbolic = generate_symbolic_proposals(budget=10)
    merged = merge_proposals(symbolic, symbolic, budget=20)
    assert merged == symbolic


def test_v57_rejects_wrong_llm_provider_prefix() -> None:
    with pytest.raises(ValueError, match="prefixed"):
        compile_proposal(
            generate_symbolic_proposals(budget=1)[0].proposal.__class__(
                "mean(close, 5)", "hypothesis", "continuous_ranking", "5d", 1, "llm", "unknown"
            )
        )


def test_v57_report_is_deterministic_and_label_free(tmp_path) -> None:
    first = run_v57_proposal_generator(tmp_path / "first")
    second = run_v57_proposal_generator(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_STAGED_SCREENING"
    assert not first.label_access
    assert first.inferential_trial_delta == 0
