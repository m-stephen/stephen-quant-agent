from __future__ import annotations

from stephen_quant.discovery import (
    v30_continuous_generation_plan,
    v30_epoch_five_generation_plan,
    v30_epoch_four_generation_plan,
    v30_epoch_three_generation_plan,
    v30_epoch_two_generation_plan,
)
from stephen_quant.workflows import load_automated_discovery_config
from stephen_quant.workflows.automated_discovery import AutomatedDiscoveryConfig


def test_epoch_one_generation_plan_is_frozen_and_unique() -> None:
    plan = v30_continuous_generation_plan()
    plan.validate()
    assert plan.windows == (20,)
    assert plan.horizons == ("20d",)
    assert tuple(item.template_id for item in plan.templates) == (
        "margin_demand_acceleration_5_20",
        "leveraged_informed_acceleration_5_20",
        "auction_price_absorption_5",
    )
    schemas = tuple(item.render(window=20, horizon="20d") for item in plan.templates)
    assert len({item.fingerprint for item in schemas}) == 3
    assert all("2025" not in item.to_json() and "2026" not in item.to_json() for item in schemas)


def test_epoch_one_config_carries_historical_multiplicity() -> None:
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-1.json")
    assert config.search_profile == "v3.0"
    assert config.mechanism_epoch == 1
    assert config.prior_inferential_trials == 52
    assert config.maximum_pbo == 0.05
    assert config.min_dsr_probability == 0.95
    assert config.research_end == "2024-12-31"


def test_negative_historical_trial_offset_is_rejected() -> None:
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-1.json")
    payload = {**config.__dict__, "prior_inferential_trials": -1}
    try:
        AutomatedDiscoveryConfig(**payload).validate()
    except ValueError as exc:
        assert "prior_inferential_trials" in str(exc)
    else:
        raise AssertionError("negative prior trial count must fail closed")


def test_epoch_two_is_a_distinct_preregistered_mechanism_set() -> None:
    first = v30_continuous_generation_plan()
    second = v30_epoch_two_generation_plan()
    first_schemas = {
        item.render(window=20, horizon="20d").fingerprint for item in first.templates
    }
    second_schemas = {
        item.render(window=20, horizon="20d").fingerprint for item in second.templates
    }
    assert len(second_schemas) == 3
    assert first_schemas.isdisjoint(second_schemas)
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-2.json")
    assert config.mechanism_epoch == 2


def test_epoch_three_uses_new_chip_distribution_fields() -> None:
    first_two = {
        item.render(window=20, horizon="20d").fingerprint
        for plan in (v30_continuous_generation_plan(), v30_epoch_two_generation_plan())
        for item in plan.templates
    }
    third = v30_epoch_three_generation_plan()
    schemas = tuple(item.render(window=20, horizon="20d") for item in third.templates)
    assert len(schemas) == 3
    assert all("qd_chip" in schema.data_sources for schema in schemas)
    assert first_two.isdisjoint(schema.fingerprint for schema in schemas)
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-3.json")
    assert config.mechanism_epoch == 3


def test_v30_requires_frozen_economic_court_thresholds() -> None:
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-1.json")
    payload = {
        **config.__dict__,
        "court_minimum_annualized_sharpe": None,
        "court_maximum_drawdown": None,
    }
    try:
        AutomatedDiscoveryConfig(**payload).validate()
    except ValueError as exc:
        assert "Sharpe and drawdown" in str(exc)
    else:
        raise AssertionError("v3.0 economic court thresholds must fail closed")


def test_epoch_four_is_distinct_chip_dynamics() -> None:
    earlier = {
        item.render(window=20, horizon="20d").fingerprint
        for plan in (
            v30_continuous_generation_plan(),
            v30_epoch_two_generation_plan(),
            v30_epoch_three_generation_plan(),
        )
        for item in plan.templates
    }
    fourth = v30_epoch_four_generation_plan()
    schemas = tuple(item.render(window=20, horizon="20d") for item in fourth.templates)
    assert len(schemas) == 3
    assert all("qd_chip" in schema.data_sources for schema in schemas)
    assert earlier.isdisjoint(schema.fingerprint for schema in schemas)
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-4.json")
    assert config.mechanism_epoch == 4


def test_epoch_five_uses_dense_limit_event_fields() -> None:
    fifth = v30_epoch_five_generation_plan()
    schemas = tuple(item.render(window=20, horizon="20d") for item in fifth.templates)
    assert len(schemas) == 3
    assert all("qd_limit_event" in schema.data_sources for schema in schemas)
    assert {schema.direction for schema in schemas} == {1}
    config = load_automated_discovery_config("configs/v3.0-continuous-epoch-5.json")
    assert config.mechanism_epoch == 5
