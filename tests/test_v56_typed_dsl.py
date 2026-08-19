from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.discovery.semantic_catalog import route_factor_schema
from stephen_quant.discovery.typed_dsl import type_check_schema
from stephen_quant.research_agent.models import ResearchAgentError
from stephen_quant.workflows.v43_domain_breadth import _schemas, generation_plans
from stephen_quant.workflows.v54_alpha_conversion import constrained_schemas
from stephen_quant.workflows.v56_typed_dsl import run_v56_typed_dsl


def _schema(fragment: str):
    return next(schema for _, schema in constrained_schemas() if fragment in schema.schema_id)


def test_v56_infers_normalized_margin_formula() -> None:
    result = type_check_schema(_schema("margin_net_demand_intensity_5_positive"))
    assert result.output.unit == "ratio"
    assert result.output.frequency == "daily"
    assert "after_prior_session_publication" in result.output.availability


def test_v56_sparse_binary_mean_becomes_ratio() -> None:
    schema = next(
        item for item in _schemas(generation_plans()) if item.schema_id.startswith("limit_up_persistence")
    )
    result = type_check_schema(schema)
    assert result.output.unit == "ratio"
    assert result.output.value_type == "ratio"
    assert result.research_form == "event_study"


def test_v56_rejects_incompatible_addition() -> None:
    schema = _schema("margin_net_demand_intensity_5_positive")
    invalid = replace(
        schema,
        formula="mean(margin_financing_buy, 5) + mean(close, 5)",
        required_fields=("close", "margin_financing_buy"),
    )
    with pytest.raises(ResearchAgentError, match="incompatible units"):
        type_check_schema(invalid)


def test_v56_rejects_excessive_automatic_lookback() -> None:
    schema = next(item for item in _schemas(generation_plans()) if item.schema_id.startswith("price_reversal"))
    invalid = replace(schema, formula="period_return(close, 253)")
    with pytest.raises(ResearchAgentError, match="exceeds automatic limit"):
        type_check_schema(invalid)


def test_v56_identity_is_name_independent() -> None:
    schema = _schema("auction_liquidity_pressure_5_positive")
    renamed = replace(schema, schema_id="renamed_auction", name="Renamed")
    assert type_check_schema(schema).semantic_identity == type_check_schema(renamed).semantic_identity


def test_v56_rejects_route_bound_to_another_schema() -> None:
    schema = _schema("auction_liquidity_pressure_5_positive")
    other_route = route_factor_schema(_schema("margin_net_demand_intensity_5_positive"))
    with pytest.raises(ResearchAgentError, match="not bound"):
        type_check_schema(schema, route=other_route)


def test_v56_report_is_deterministic_and_filters_before_trials(tmp_path) -> None:
    first = run_v56_typed_dsl(tmp_path / "first")
    second = run_v56_typed_dsl(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_AUTOMATIC_PROPOSALS"
    assert first.accepted_candidates > 0
    assert first.accepted_candidates + first.rejected_candidates == first.unique_semantic_candidates
    assert first.inferential_trial_delta == 0
