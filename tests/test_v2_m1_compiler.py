from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from stephen_quant.research_agent.dsl import analyze_formula
from stephen_quant.research_agent.models import ResearchAgentError
from stephen_quant.v2 import (
    CompilerPolicy,
    ConstrainedProposalQueue,
    ExpressionBlueprint,
    FrozenInteraction,
    V2Hypothesis,
    compile_hypothesis,
    default_blueprints,
    replay_frozen_selection,
)


def _hypothesis(blueprint: ExpressionBlueprint) -> V2Hypothesis:
    inputs = {
        "flow_price_divergence": ("amount", "close", "net_inflow_amount"),
        "large_flow_surprise": ("amount", "large_buy_amount", "large_sell_amount"),
        "margin_financing": ("amount", "margin_financing_buy"),
        "opening_auction": ("auction_return",),
    }[blueprint.event]
    return V2Hypothesis(
        statement=f"Testable mechanism for {blueprint.event}",
        event=blueprint.event,
        contexts=("after_close",),
        mechanism="A point-in-time demand imbalance may precede price adjustment.",
        direction=1,
        expected_horizon="20d",
        universe="dynamic_A_share_research_universe",
        regime="all_preregistered_research_regimes",
        inputs=inputs,
        controls=("price_reversal", "log_adv"),
        falsification_criteria=(
            "residual_ic_disappears_after_controls",
            "net_long_leg_is_not_positive",
        ),
        evidence_refs=("issue_36",),
        economic_complexity_budget=4,
        search_budget=2,
    )


def _policy(**changes: object) -> CompilerPolicy:
    policy = CompilerPolicy(
        dataset_snapshot_id="snapshot_fixture_sha_bound",
        decision_context="after_close",
        field_coverage=(
            ("amount", 0.99),
            ("close", 0.99),
            ("net_inflow_amount", 0.95),
            ("large_buy_amount", 0.94),
            ("large_sell_amount", 0.94),
            ("margin_financing_buy", 0.90),
            ("auction_return", 0.95),
        ),
        maximum_complexity_nodes=64,
    )
    return replace(policy, **changes)


def test_three_hypotheses_compile_to_deterministic_pit_safe_families() -> None:
    compiled = [
        compile_hypothesis(_hypothesis(blueprint), blueprint, _policy())
        for blueprint in default_blueprints()
    ]
    assert len(compiled) == 3
    assert len({item.contract.ids.expression_structure_id for item in compiled}) == 3
    assert all(
        item.contract.dataset_snapshot_id == "snapshot_fixture_sha_bound" for item in compiled
    )
    assert all(all(finding.passed for finding in item.findings) for item in compiled)
    replayed = compile_hypothesis(
        _hypothesis(default_blueprints()[0]), default_blueprints()[0], _policy()
    )
    assert replayed.contract.ids == compiled[0].contract.ids


@pytest.mark.parametrize(
    ("blueprint", "error"),
    [
        (
            ExpressionBlueprint(
                "bad_operator",
                "flow_price_divergence",
                "Bad operator",
                "abs(mean(net_inflow_amount, {lookback}))",
                (("lookback", 20),),
            ),
            "unknown DSL function",
        ),
        (
            ExpressionBlueprint(
                "bad_window",
                "flow_price_divergence",
                "Bad window",
                "mean(net_inflow_amount, {lookback})",
                (("lookback", 500),),
            ),
            "lookback exceeds",
        ),
        (
            ExpressionBlueprint(
                "unsafe_division",
                "flow_price_divergence",
                "Unsafe division",
                "mean(net_inflow_amount, {lookback}) / mean(amount, {lookback})",
                (("lookback", 20),),
            ),
            "positive denominator floor",
        ),
    ],
)
def test_illegal_expression_fails_before_evaluation(
    blueprint: ExpressionBlueprint, error: str
) -> None:
    hypothesis = replace(
        _hypothesis(default_blueprints()[0]),
        inputs=(
            ("net_inflow_amount",)
            if blueprint.blueprint_id == "bad_window"
            else ("amount", "net_inflow_amount")
        ),
    )
    with pytest.raises((ResearchAgentError, ValueError), match=error):
        compile_hypothesis(hypothesis, blueprint, _policy())


def test_type_coverage_and_pit_gates_fail_closed() -> None:
    dimension_error = ExpressionBlueprint(
        "dimension_error",
        "flow_price_divergence",
        "Dimension error",
        "mean(amount, {lookback}) + period_return(close, {lookback})",
        (("lookback", 20),),
    )
    hypothesis = replace(_hypothesis(default_blueprints()[0]), inputs=("amount", "close"))
    with pytest.raises(ResearchAgentError, match="cannot add/subtract"):
        compile_hypothesis(hypothesis, dimension_error, _policy())

    with pytest.raises(ResearchAgentError, match="coverage gate"):
        compile_hypothesis(
            _hypothesis(default_blueprints()[0]),
            default_blueprints()[0],
            _policy(field_coverage=(("amount", 0.99), ("close", 0.99))),
        )

    auction = ExpressionBlueprint(
        "auction_signal",
        "opening_auction",
        "Auction signal",
        "mean(auction_return, {lookback})",
        (("lookback", 5),),
    )
    with pytest.raises(ResearchAgentError, match="PIT context"):
        compile_hypothesis(_hypothesis(auction), auction, _policy(decision_context="prior_close"))


def test_constrained_queue_explores_and_mutates_one_dimension() -> None:
    blueprint = default_blueprints()[0]
    hypothesis = _hypothesis(blueprint)
    first_queue = ConstrainedProposalQueue(default_blueprints(), budget=2)
    explored = first_queue.explore(hypothesis)
    mutated = first_queue.mutate_lookback(explored, parameter="lookback", value=60)
    assert explored.mode == "EXPLORE"
    assert mutated.mode == "MUTATE"
    assert mutated.parent_proposal_id == explored.proposal_id
    assert mutated.mutated_dimension == "parameter:lookback"
    assert dict(mutated.blueprint.parameters)["lookback"] == 60
    with pytest.raises(ValueError, match="budget exhausted"):
        first_queue.explore(hypothesis)

    second_queue = ConstrainedProposalQueue(default_blueprints(), budget=2)
    assert second_queue.explore(hypothesis).proposal_id == explored.proposal_id
    with pytest.raises(ValueError, match="must change exactly one"):
        ConstrainedProposalQueue(default_blueprints(), budget=2).mutate_lookback(
            explored, parameter="lookback", value=20
        )


def test_frozen_selection_replays_recorded_bytes_without_model_callback() -> None:
    raw_output = json.dumps(
        {
            "event": "flow_price_divergence",
            "blueprint_id": "flow_price_divergence",
            "parameters": {"lookback": 20},
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    interaction = FrozenInteraction(
        provider="fixture",
        model="recorded-only",
        model_version="1",
        prompt_version="v2-m1",
        tool_versions=("none",),
        raw_input="frozen hypothesis request",
        raw_output=raw_output,
        tool_calls_json="[]",
        fetched_at="2026-08-17T00:00:00+00:00",
    )
    selection = replay_frozen_selection(interaction)
    assert selection.parameters == (("lookback", 20),)
    assert selection.response_sha256 == hashlib.sha256(raw_output.encode()).hexdigest()


def test_contract_rejects_expression_that_differs_from_embedded_provenance() -> None:
    compiled = compile_hypothesis(
        _hypothesis(default_blueprints()[0]), default_blueprints()[0], _policy()
    )
    altered_formula = "mean(net_inflow_amount, 5)"
    altered = replace(
        compiled.contract,
        formula=altered_formula,
        canonical_ast=analyze_formula(altered_formula).canonical_ast,
    )
    with pytest.raises(ValueError, match="differs from embedded legacy provenance"):
        altered.validate()
