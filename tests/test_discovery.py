from __future__ import annotations

from pathlib import Path

import pytest

from stephen_quant.discovery import (
    CampaignBudget,
    CampaignSpec,
    FactorSchema,
    FactorTemplate,
    GenerationPlan,
    SearchCampaign,
    generate_candidates,
)
from stephen_quant.factors.engine import compute_factor
from stephen_quant.factors.registry import FactorRegistry
from stephen_quant.integrity.models import ExperimentSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_snapshot_manifest


def _schema(formula: str = "period_return(close, 2)") -> FactorSchema:
    return FactorSchema(
        schema_id="price_momentum_2",
        version="1.0.0",
        name="Two-session momentum",
        event="price",
        context="all_market",
        quality="complete_daily_bars",
        direction=1,
        output="cross_sectional_score",
        horizon="5d",
        formula=formula,
        data_sources=("qd_daily",),
        required_fields=("close",),
        availability_lag_days=0,
        economic_rationale="Short price persistence may survive after risk controls.",
    )


def _experiment(tmp_path: Path) -> tuple[ExperimentRegistry, str]:
    data = tmp_path / "data"
    data.mkdir()
    (data / "bars.csv").write_text("date,close\n2024-01-01,1\n", encoding="utf-8")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot_id = registry.register_snapshot(build_snapshot_manifest(data))
    experiment_id = registry.create_experiment(
        ExperimentSpec(
            name="v1.8.16 discovery",
            hypothesis="Bounded structured search can find falsifiable candidates.",
            dataset_snapshot_id=snapshot_id,
            code_version="test",
        )
    )
    return registry, experiment_id


def test_schema_compiles_deterministically_and_runs_safe_dsl() -> None:
    schema = _schema()
    first = schema.compile()
    second = schema.compile()
    assert first == second
    assert schema.fingerprint == _schema(" period_return( close , 2 ) ").fingerprint

    registry = FactorRegistry((first,))
    definition = registry.get("price_momentum_2")
    result = compute_factor(
        definition,
        {"close": [100.0, 110.0, 121.0]},
        {
            "close": [
                "2024-01-01T16:00:00+08:00",
                "2024-01-02T16:00:00+08:00",
                "2024-01-03T16:00:00+08:00",
            ]
        },
        as_of_index=2,
        observation_times=("2024-01-01", "2024-01-02", "2024-01-03"),
        decision_at="2024-01-04T09:00:00+08:00",
    )
    assert result.value == pytest.approx(0.21)


def test_schema_rejects_field_mismatch_and_unsafe_formula() -> None:
    invalid = _schema("period_return(volume, 2)")
    with pytest.raises(ValueError, match="required_fields"):
        invalid.validate()
    with pytest.raises(ValueError):
        FactorSchema(**{**invalid.__dict__, "formula": "__import__('os')"}).validate()


def test_campaign_records_duplicates_and_enforces_frozen_budget(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    campaign = SearchCampaign(
        registry,
        CampaignSpec(
            name="bounded-search",
            experiment_id=experiment_id,
            budget=CampaignBudget(schema=2, cpcv=1, execution=0),
            horizons=("5d",),
            ranking_metric="training_fold_rank_ic",
            stopping_rule="stop after two proposals",
            sealed_windows=("2025", "2026"),
        ),
    )

    first_unique, _, first_number = campaign.propose(_schema())
    second_unique, _, second_number = campaign.propose(_schema(" period_return(close, 2) "))
    assert first_unique is True
    assert second_unique is False
    assert (first_number, second_number) == (1, 2)
    assert campaign.summary()["decisions"] == {"duplicate": 1, "generated": 1}

    with pytest.raises(ValueError, match="budget exhausted"):
        campaign.propose(_schema())


def test_campaign_rejects_invalid_budget_before_database_write(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    with pytest.raises(ValueError, match="budgets"):
        SearchCampaign(
            registry,
            CampaignSpec(
                name="invalid",
                experiment_id=experiment_id,
                budget=CampaignBudget(schema=2, cpcv=3, execution=0),
                horizons=("5d",),
                ranking_metric="rank_ic",
                stopping_rule="fixed",
                sealed_windows=("2025",),
            ),
        )


def test_generator_is_deterministic_and_campaign_can_resume(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    spec = CampaignSpec(
        name="automatic-search",
        experiment_id=experiment_id,
        budget=CampaignBudget(schema=4, cpcv=2, execution=1),
        horizons=("5d", "20d"),
        ranking_metric="training_fold_rank_ic",
        stopping_rule="fixed four proposals",
        sealed_windows=("2025", "2026"),
    )
    campaign = SearchCampaign(registry, spec)
    plan = GenerationPlan(
        templates=(
            FactorTemplate(
                template_id="momentum",
                name="Momentum",
                event="price",
                context="all_market",
                quality="complete_bars",
                output="score",
                formula_template="period_return(close, {window})",
                required_fields=("close",),
                data_sources=("qd_daily",),
                direction=1,
                economic_rationale="Underreaction may persist.",
            ),
        ),
        windows=(5, 20),
        horizons=("20d", "5d"),
    )
    generated = generate_candidates(campaign, plan)
    assert [item.schema.schema_id for item in generated] == [
        "momentum_5_20d",
        "momentum_5_5d",
        "momentum_20_20d",
        "momentum_20_5d",
    ]
    assert all(item.unique for item in generated)

    resumed = SearchCampaign(registry, spec, campaign_id=campaign.campaign_id)
    assert resumed.summary()["proposal_count"] == 4
    with pytest.raises(ValueError, match="budget exhausted"):
        resumed.propose(generated[0].schema)
