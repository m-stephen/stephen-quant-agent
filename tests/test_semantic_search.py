from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.v2.semantic_search import (
    ChangeLayer,
    ContentAddressedRemoteCache,
    ContextRole,
    ControlKind,
    LabelFreeSearchController,
    PITReadiness,
    RemoteLedgerRecord,
    ResearchContractVersion,
    SearchLedger,
    SemanticContext,
    SemanticPlan,
    StaticDecisionCode,
    build_candidate_identity,
    classify_change,
    reject_sealed_references,
    static_gate,
    validate_transition,
)


def _plan(**changes: object) -> SemanticPlan:
    values: dict[str, object] = {
        "plan_id": "flow_price_divergence",
        "economic_claim": "persistent informed flow is incorporated into price gradually",
        "event": "flow_price_divergence",
        "contexts": (
            SemanticContext("persistent_flow", ContextRole.CONSTITUTIVE),
            SemanticContext("liquid_security", ContextRole.ELIGIBILITY),
        ),
        "data_semantics": ("daily_close", "daily_fund_flow"),
        "information_set": ("after_close_t",),
        "transmission_path": "inventory pressure followed by delayed price response",
        "economic_direction": 1,
        "observable_proxy": (
            "mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) "
            "- period_return(close, 20)"
        ),
        "required_data": ("amount", "close", "net_inflow_amount"),
        "pit_readiness": (
            ("amount", PITReadiness.READY),
            ("close", PITReadiness.READY),
            ("net_inflow_amount", PITReadiness.CONDITIONAL),
        ),
        "falsification": ("signal vanishes when persistence is removed",),
        "primary_horizon": "20d",
        "secondary_horizon": "5d",
        "logic_budget": 2,
        "parameter_budget": 1,
    }
    values.update(changes)
    return SemanticPlan(**values)  # type: ignore[arg-type]


def _identity(**changes: object):
    return build_candidate_identity(_plan(), **changes)


def _remote(**changes: object) -> RemoteLedgerRecord:
    values: dict[str, object] = {
        "request_id": "request-1",
        "provider": "synthetic-provider",
        "advertised_model": "fixture-model",
        "provider_model_version": "fixture-1",
        "prompt_template_version": "prompt-1",
        "rendered_prompt": "propose a flow-price semantic plan from synthetic fields",
        "sampling_config_json": '{"seed":7,"temperature":0}',
        "raw_response": '{"plan_id":"flow_price_divergence"}',
        "tool_calls_json": "[]",
        "parser_version": "parser-1",
        "retry_parent_id": None,
    }
    values.update(changes)
    return RemoteLedgerRecord(**values)  # type: ignore[arg-type]


def test_semantic_plan_and_five_level_identity_are_deterministic() -> None:
    left = _identity(parameters=(("lookback", "20"),))
    right = _identity(parameters=(("lookback", "20"),))
    left.validate()
    assert left.identity_sha256 == right.identity_sha256
    assert left.plan.plan_sha256 != left.plan.family_sha256
    assert len(
        {
            left.plan.family_sha256,
            left.expression.expression_sha256,
            left.parameter.parameter_sha256,
            left.policy.policy_sha256,
            left.contract.contract_sha256,
        }
    ) == 5


def test_context_roles_control_family_identity() -> None:
    base = _plan()
    eligibility_changed = replace(
        base,
        contexts=(
            SemanticContext("persistent_flow", ContextRole.CONSTITUTIVE),
            SemanticContext("large_cap_only", ContextRole.ELIGIBILITY),
        ),
    )
    constitutive_changed = replace(
        base,
        contexts=(SemanticContext("one_day_flow_spike", ContextRole.CONSTITUTIVE),),
    )
    assert base.family_sha256 == eligibility_changed.family_sha256
    assert base.family_sha256 != constitutive_changed.family_sha256


def test_reverse_sign_control_cannot_manufacture_a_new_family() -> None:
    primary = _identity()
    reversed_plan = replace(
        _plan(),
        observable_proxy="-(mean(net_inflow_amount, 20) / (mean(amount, 20) + 1.0) - period_return(close, 20))",
    )
    reverse = build_candidate_identity(reversed_plan, control_kind=ControlKind.REVERSE_SIGN)
    assert primary.plan.family_sha256 == reverse.plan.family_sha256
    assert primary.expression.expression_sha256 != reverse.expression.expression_sha256
    assert classify_change(primary, reverse) == ChangeLayer.EXPRESSION


def test_change_classifier_is_deterministic_by_highest_changed_layer() -> None:
    base = _identity(parameters=(("lookback", "20"),))
    parameter = _identity(parameters=(("lookback", "60"),))
    policy = _identity(parameters=(("lookback", "20"),), top_k=20)
    family = build_candidate_identity(
        replace(_plan(), economic_claim="temporary liquidity demand reverses"),
        parameters=(("lookback", "20"),),
    )
    contract = replace(
        base,
        contract=replace(base.contract, contract_version="label-free-contract-1.0.1"),
    )
    assert classify_change(base, base) == ChangeLayer.NONE
    assert classify_change(base, parameter) == ChangeLayer.PARAMETER
    assert classify_change(base, policy) == ChangeLayer.POLICY
    assert classify_change(base, family) == ChangeLayer.FAMILY
    assert classify_change(base, contract) == ChangeLayer.CONTRACT


def test_transition_rejects_multiple_layer_changes_and_requires_parent_lineage() -> None:
    base = _identity(parameters=(("lookback", "20"),))
    changed_plan = replace(
        _plan(),
        economic_claim="a distinct claim",
        observable_proxy="period_return(close, 5)",
        required_data=("close",),
        pit_readiness=(("close", PITReadiness.READY),),
    )
    multi_layer = build_candidate_identity(changed_plan)
    with pytest.raises(ValueError, match="exactly one identity layer"):
        classify_change(base, multi_layer)

    missing_parent = _identity(parameters=(("lookback", "60"),))
    with pytest.raises(ValueError, match="parent policy"):
        validate_transition(base, missing_parent)
    linked = _identity(
        parameters=(("lookback", "60"),),
        parent_policy_sha256=base.policy.policy_sha256,
    )
    assert validate_transition(base, linked) == ChangeLayer.PARAMETER


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"contexts": ()}, "contexts"),
        ({"economic_direction": 0}, "economic_direction"),
        ({"secondary_horizon": "20d"}, "secondary horizon"),
        ({"logic_budget": 0}, "budgets"),
        ({"required_data": ("close",)}, "PIT readiness"),
    ],
)
def test_semantic_plan_rejects_invalid_contracts(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _plan(**changes).validate()


def test_blocked_data_fails_before_any_empirical_access() -> None:
    plan = replace(
        _plan(),
        pit_readiness=(
            ("amount", PITReadiness.READY),
            ("close", PITReadiness.READY),
            ("net_inflow_amount", PITReadiness.BLOCKED),
        ),
    )
    identity = build_candidate_identity(plan)
    decision = static_gate(identity)
    assert not decision.accepted
    assert decision.code == StaticDecisionCode.DATA_NOT_RESEARCH_READY


def test_semantic_expression_and_tombstone_gates_are_separate() -> None:
    identity = _identity()
    semantic = static_gate(identity, known_family_sha256=(identity.plan.family_sha256,))
    expression = static_gate(
        identity,
        known_expression_sha256=(identity.expression.expression_sha256,),
    )
    tombstone = static_gate(
        identity,
        tombstoned_family_sha256=(identity.plan.family_sha256,),
    )
    assert semantic.code == StaticDecisionCode.SEMANTIC_DUPLICATE
    assert expression.code == StaticDecisionCode.EXPRESSION_DUPLICATE
    assert tombstone.code == StaticDecisionCode.TOMBSTONE_DESCENDANT


def test_controller_enforces_budget_and_writes_deterministic_search_ledger() -> None:
    identity = _identity()
    first = LabelFreeSearchController(1)
    second = LabelFreeSearchController(1)
    assert first.evaluate(identity).accepted
    assert second.evaluate(identity).accepted
    assert first.ledger.events == second.ledger.events
    assert [event.sequence for event in first.ledger.events] == [1, 2]
    with pytest.raises(ValueError, match="budget exhausted"):
        first.evaluate(identity)


def test_search_ledger_rejects_sealed_window_payload() -> None:
    ledger = SearchLedger()
    with pytest.raises(ValueError, match="sealed or consumed"):
        ledger.record("PROPOSAL", "a" * 64, {"window": "final-2026"})


def test_sealed_window_references_are_rejected_recursively() -> None:
    with pytest.raises(ValueError, match="sealed or consumed"):
        reject_sealed_references({"nested": ["validation_2025"]})
    with pytest.raises(ValueError, match="sealed or consumed"):
        _plan(plan_id="factor_2026").validate()


def test_remote_ledger_is_content_addressed_and_offline_only() -> None:
    record = _remote()
    record.validate()
    cache = ContentAddressedRemoteCache((record,))
    replayed = cache.replay(record.request_bytes_sha256)
    assert replayed.response_bytes_sha256 == record.response_bytes_sha256
    assert replayed.ledger_sha256 == record.ledger_sha256
    with pytest.raises(ValueError, match="network fallback is forbidden"):
        cache.replay("f" * 64)


def test_remote_ledger_rejects_bad_json_and_sealed_content() -> None:
    with pytest.raises(ValueError, match="sampling config"):
        _remote(sampling_config_json="not-json").validate()
    with pytest.raises(ValueError, match="sealed or consumed"):
        _remote(raw_response='{"window":"2025"}').validate()


def test_research_contract_forbids_empirical_trial_budget() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="zero empirical"):
        ResearchContractVersion(
            "contract",
            plan.primary_horizon,
            plan.secondary_horizon,
            plan.falsification,
            plan.pit_readiness,
            "synthetic",
            "no-real-window",
            1,
            0,
            1,
        ).validate()
