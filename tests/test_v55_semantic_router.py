from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.discovery.models import SOURCE_FIELDS, FactorSchema
from stephen_quant.discovery.semantic_catalog import (
    build_semantic_catalog,
    failure_memory_identity,
    route_factor_schema,
)
from stephen_quant.workflows.v43_domain_breadth import _schemas, generation_plans
from stephen_quant.workflows.v54_alpha_conversion import constrained_schemas
from stephen_quant.workflows.v55_semantic_router import run_v55_semantic_router


def _schema(fragment: str) -> FactorSchema:
    return next(schema for _, schema in constrained_schemas() if fragment in schema.schema_id)


def test_v55_catalog_covers_every_declared_source_field() -> None:
    catalog = build_semantic_catalog()
    assert {(item.source, item.field) for item in catalog} == {
        (source, field) for source, fields in SOURCE_FIELDS.items() for field in fields
    }


def test_v55_routes_sparse_events_and_margin_roles() -> None:
    limit_route = route_factor_schema(_schema("limit_seal_retention_5_positive"))
    auction_route = route_factor_schema(_schema("auction_liquidity_pressure_5_positive"))
    margin_route = route_factor_schema(_schema("margin_net_demand_intensity_5_positive"))
    assert limit_route.primary_form == "event_study"
    assert auction_route.primary_form == "event_study"
    assert margin_route.primary_form == "continuous_ranking"
    assert {"continuous_ranking", "portfolio_filter"} <= set(margin_route.allowed_forms)
    assert (
        route_factor_schema(
            _schema("margin_net_demand_intensity_5_positive"),
            requested_form="portfolio_filter",
        ).primary_form
        == "portfolio_filter"
    )


def test_v55_daily_fields_can_be_routed_as_regime_context() -> None:
    schema = next(item for item in _schemas(generation_plans()) if item.schema_id.startswith("price_reversal"))
    route = route_factor_schema(
        schema,
        requested_form="regime_switch",
    )
    assert route.primary_form == "regime_switch"


def test_v55_missing_is_not_silently_zero() -> None:
    catalog = {(item.source, item.field): item for item in build_semantic_catalog()}
    assert catalog[("qd_limit_event", "kpl_limit_up_flag")].missing_meaning == "structural_zero"
    assert catalog[("qd_limit_event", "kpl_close_seal_amount")].missing_meaning == "not_applicable"
    assert catalog[("qd_auction", "auction_return")].missing_meaning == "unknown"


def test_v55_renaming_does_not_change_semantic_or_failure_identity() -> None:
    schema = _schema("margin_net_demand_intensity_5_positive")
    renamed = replace(schema, schema_id="renamed_margin_hypothesis", name="Renamed hypothesis")
    original_route = route_factor_schema(schema)
    renamed_route = route_factor_schema(renamed)
    assert original_route.schema_fingerprint == renamed_route.schema_fingerprint
    assert original_route.semantic_identity == renamed_route.semantic_identity
    assert failure_memory_identity(original_route, "negative_net_return") == failure_memory_identity(
        renamed_route, "negative_net_return"
    )


def test_v55_rejects_incompatible_form_override() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        route_factor_schema(_schema("limit_seal_retention_5_positive"), requested_form="continuous_ranking")


def test_v55_report_is_deterministic(tmp_path) -> None:
    first = run_v55_semantic_router(tmp_path / "first")
    second = run_v55_semantic_router(tmp_path / "second")
    assert first.to_json() == second.to_json()
    assert first.decision == "READY_FOR_TYPED_DSL"
