from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.baseline import BaselineObservation
from stephen_quant.discovery import (
    CampaignBudget,
    CampaignSpec,
    DiscoveryCpcvConfig,
    DiscoveryCpcvReport,
    DiscoveryCpcvScore,
    DiscoveryExecutionConfig,
    FactorSchema,
    FactorTemplate,
    GeneratedCandidate,
    GenerationPlan,
    ScreeningConfig,
    ScreeningWindow,
    SearchCampaign,
    generate_candidates,
    run_discovery_cpcv,
    run_discovery_execution,
    run_training_screen,
)
from stephen_quant.factors.engine import compute_factor
from stephen_quant.factors.registry import FactorRegistry
from stephen_quant.falsification import PBOResult
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
    with pytest.raises(ValueError, match="not provided"):
        FactorSchema(
            **{
                **_schema().__dict__,
                "data_sources": ("qd_auction",),
            }
        ).validate()


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


def _screen_rows(*, reverse: bool = False) -> tuple[BaselineObservation, ...]:
    rows: list[BaselineObservation] = []
    for day in range(2, 5):
        for instrument_index, instrument in enumerate(("000001.SZ", "000002.SZ", "600000.SH")):
            signal = float(3 - instrument_index if reverse else instrument_index + 1)
            rows.append(
                BaselineObservation(
                    instrument=instrument,
                    signal=signal,
                    signal_at=f"2024-01-0{day - 1}T15:00:00+08:00",
                    signal_available_at=f"2024-01-0{day - 1}T15:01:00+08:00",
                    average_daily_value=1_000_000.0,
                    liquidity_available_at=f"2024-01-0{day - 1}T15:01:00+08:00",
                    execution_at=f"2024-01-0{day}T09:30:00+08:00",
                    return_end_at=f"2024-01-0{day + 1}T09:30:00+08:00",
                    forward_return=(instrument_index + 1) / 100,
                )
            )
    return tuple(rows)


def test_training_screen_counts_every_measurement_and_applies_shortlist(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    spec = CampaignSpec(
        name="screen",
        experiment_id=experiment_id,
        budget=CampaignBudget(schema=3, cpcv=1, execution=1),
        horizons=("5d",),
        ranking_metric="training_fold_rank_ic",
        stopping_rule="three proposals",
        sealed_windows=("2025", "2026"),
    )
    campaign = SearchCampaign(registry, spec)
    schemas = (
        _schema("period_return(close, 2)"),
        FactorSchema(
            **{
                **_schema("period_return(close, 3)").__dict__,
                "schema_id": "price_momentum_3",
            }
        ),
        FactorSchema(
            **{
                **_schema("volatility(close, 2)").__dict__,
                "schema_id": "price_volatility_2",
            }
        ),
    )
    generated: list[GeneratedCandidate] = []
    for schema in schemas:
        unique, proposal_id, number = campaign.propose(schema)
        generated.append(GeneratedCandidate(schema, proposal_id, number, unique))
    panels = {
        schemas[0].fingerprint: _screen_rows(),
        schemas[1].fingerprint: _screen_rows(),
        schemas[2].fingerprint: _screen_rows(reverse=True),
    }
    report = run_training_screen(
        registry,
        campaign,
        tuple(generated),
        panels,
        window=ScreeningWindow(
            research_start="2024-01-01",
            research_end="2024-01-31",
            validation_start="2025-01-01",
            validation_end="2025-12-31",
            test_start="2026-01-01",
            test_end="2026-12-31",
        ),
        config=ScreeningConfig(minimum_mean_rank_ic=0.01),
    )
    assert len(report.shortlisted_fingerprints) == 1
    assert registry.trial_count(experiment_id) == 3
    decisions = campaign.summary()["decisions"]
    assert decisions == {"screened_out": 2, "shortlisted": 1}


def test_training_screen_rejects_reserved_window_observations(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    spec = CampaignSpec(
        name="sealed",
        experiment_id=experiment_id,
        budget=CampaignBudget(schema=1, cpcv=1, execution=0),
        horizons=("5d",),
        ranking_metric="rank_ic",
        stopping_rule="one",
        sealed_windows=("2025", "2026"),
    )
    campaign = SearchCampaign(registry, spec)
    schema = _schema()
    unique, proposal_id, number = campaign.propose(schema)
    generated = (GeneratedCandidate(schema, proposal_id, number, unique),)
    leaked = tuple(
        BaselineObservation(
            **{
                **row.__dict__,
                "execution_at": "2025-01-02T09:30:00+08:00",
                "return_end_at": "2025-01-03T09:30:00+08:00",
            }
        )
        for row in _screen_rows()
    )
    with pytest.raises(ValueError, match="sealed"):
        run_training_screen(
            registry,
            campaign,
            generated,
            {schema.fingerprint: leaked},
            window=ScreeningWindow(
                research_start="2024-01-01",
                research_end="2024-12-31",
                validation_start="2025-01-01",
                validation_end="2025-12-31",
                test_start="2026-01-01",
                test_end="2026-12-31",
            ),
            config=ScreeningConfig(),
        )
    assert registry.trial_count(experiment_id) == 0


def _cpcv_rows(*, variant: bool = False) -> tuple[BaselineObservation, ...]:
    rows: list[BaselineObservation] = []
    instruments = ("000001.SZ", "000002.SZ", "600000.SH", "600001.SH")
    signals = (1.0, 3.0, 2.0, 4.0) if variant else (1.0, 2.0, 3.0, 4.0)
    for day in range(2, 26):
        for index, instrument in enumerate(instruments):
            rows.append(
                BaselineObservation(
                    instrument=instrument,
                    signal=signals[index],
                    signal_at=f"2024-01-{day - 1:02d}T15:00:00+08:00",
                    signal_available_at=f"2024-01-{day - 1:02d}T15:01:00+08:00",
                    average_daily_value=1_000_000.0,
                    liquidity_available_at=f"2024-01-{day - 1:02d}T15:01:00+08:00",
                    execution_at=f"2024-01-{day:02d}T09:30:00+08:00",
                    return_end_at=f"2024-01-{day + 1:02d}T09:30:00+08:00",
                    forward_return=(index + 1) / 100,
                )
            )
    return tuple(rows)


def test_shortlist_runs_audited_cpcv_and_registers_new_trials(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    spec = CampaignSpec(
        name="cpcv",
        experiment_id=experiment_id,
        budget=CampaignBudget(schema=2, cpcv=2, execution=1),
        horizons=("5d",),
        ranking_metric="mean_path_rank_ic",
        stopping_rule="two CPCV candidates",
        sealed_windows=("2025", "2026"),
    )
    campaign = SearchCampaign(registry, spec)
    schemas = (
        _schema("period_return(close, 2)"),
        FactorSchema(
            **{
                **_schema("period_return(close, 3)").__dict__,
                "schema_id": "price_momentum_3",
            }
        ),
    )
    generated: list[GeneratedCandidate] = []
    for schema in schemas:
        unique, proposal_id, number = campaign.propose(schema)
        generated.append(GeneratedCandidate(schema, proposal_id, number, unique))
    panels = {
        schemas[0].fingerprint: _cpcv_rows(),
        schemas[1].fingerprint: _cpcv_rows(variant=True),
    }
    window = ScreeningWindow(
        research_start="2024-01-01",
        research_end="2024-01-31",
        validation_start="2025-01-01",
        validation_end="2025-12-31",
        test_start="2026-01-01",
        test_end="2026-12-31",
    )
    screening = run_training_screen(
        registry,
        campaign,
        tuple(generated),
        panels,
        window=window,
        config=ScreeningConfig(
            minimum_mean_rank_ic=0.01,
            maximum_peer_rank_correlation=1.0,
        ),
    )
    cpcv_panels = dict(panels)
    cpcv_panels[schemas[0].fingerprint] = panels[schemas[0].fingerprint] + (
        replace(
            panels[schemas[0].fingerprint][0],
            execution_at="2024-01-30T09:30:00+08:00",
            return_end_at="2024-01-31T09:30:00+08:00",
            eligible=False,
        ),
    )
    report = run_discovery_cpcv(
        registry,
        campaign,
        screening,
        tuple(generated),
        cpcv_panels,
        snapshot_id=registry.experiment_snapshot_id(experiment_id),
        code_version="test",
        window=window,
        config=DiscoveryCpcvConfig(groups=6, test_groups=3, embargo_days=0),
    )
    assert report.hygiene_passed is True
    assert report.signal_gate_passed is False
    assert report.decision == "REJECT_DEGENERATE_CPCV_PATHS"
    assert report.validation_window_opened is False
    assert report.pbo.paths == 20
    assert registry.trial_count(experiment_id) == 4
    assert "Validation window opened: no" in report.to_markdown(language="en")
    assert "是否打开验证期: 否" in report.to_markdown(language="zh")


def test_cpcv_uses_only_dates_with_valid_ic_for_every_candidate(tmp_path: Path) -> None:
    registry, experiment_id = _experiment(tmp_path)
    campaign = SearchCampaign(
        registry,
        CampaignSpec(
            name="constant-day-cpcv",
            experiment_id=experiment_id,
            budget=CampaignBudget(schema=2, cpcv=2, execution=1),
            horizons=("5d",),
            ranking_metric="mean_path_rank_ic",
            stopping_rule="two candidates",
            sealed_windows=("2025", "2026"),
        ),
    )
    schemas = (
        _schema("period_return(close, 2)"),
        FactorSchema(
            **{**_schema("period_return(close, 3)").__dict__, "schema_id": "constant_day_peer"}
        ),
    )
    generated = []
    for schema in schemas:
        unique, proposal_id, number = campaign.propose(schema)
        generated.append(GeneratedCandidate(schema, proposal_id, number, unique))
    first = _cpcv_rows()
    second = tuple(
        replace(row, signal=1.0) if row.execution_at.startswith("2024-01-05") else row
        for row in _cpcv_rows(variant=True)
    )
    panels = {schemas[0].fingerprint: first, schemas[1].fingerprint: second}
    window = ScreeningWindow(
        research_start="2024-01-01",
        research_end="2024-01-31",
        validation_start="2025-01-01",
        validation_end="2025-12-31",
        test_start="2026-01-01",
        test_end="2026-12-31",
    )
    screening = run_training_screen(
        registry,
        campaign,
        tuple(generated),
        panels,
        window=window,
        config=ScreeningConfig(minimum_mean_rank_ic=-1.0, maximum_peer_rank_correlation=1.0),
    )
    report = run_discovery_cpcv(
        registry,
        campaign,
        screening,
        tuple(generated),
        panels,
        snapshot_id=registry.experiment_snapshot_id(experiment_id),
        code_version="test",
        window=window,
        config=DiscoveryCpcvConfig(groups=6, test_groups=3, embargo_days=0),
    )
    assert report.hygiene_passed is True


def test_cpcv_rejects_an_impossible_positive_path_threshold() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        DiscoveryCpcvConfig(
            groups=5, test_groups=2, minimum_positive_paths=5
        ).validate()


@pytest.mark.parametrize("all_candidate_court", [False, True])
def test_execution_tournament_counts_trials_and_builds_alpha_court(
    tmp_path: Path,
    all_candidate_court: bool,
) -> None:
    registry, experiment_id = _experiment(tmp_path)
    campaign = SearchCampaign(
        registry,
        CampaignSpec(
            name="execution",
            experiment_id=experiment_id,
            budget=CampaignBudget(schema=2, cpcv=2, execution=2),
            horizons=("1d",),
            ranking_metric="cost_adjusted_sharpe",
            stopping_rule="two execution candidates",
            sealed_windows=("2025", "2026"),
        ),
    )
    schemas = (
        FactorSchema(**{**_schema().__dict__, "schema_id": "execution_good", "horizon": "1d"}),
        FactorSchema(
            **{
                **_schema("period_return(close, 3)").__dict__,
                "schema_id": "execution_weak",
                "horizon": "1d",
            }
        ),
    )
    generated = []
    for schema in schemas:
        unique, proposal_id, number = campaign.propose(schema)
        generated.append(GeneratedCandidate(schema, proposal_id, number, unique))

    panels: dict[str, tuple[BaselineObservation, ...]] = {}
    for candidate_index, schema in enumerate(schemas):
        rows = []
        for day in range(2, 22):
            for instrument_index in range(10):
                signal = float(
                    instrument_index
                    if candidate_index == 0
                    else -instrument_index
                )
                market_noise = ((day + instrument_index * 2) % 5 - 2) * 0.0007
                rows.append(
                    BaselineObservation(
                        instrument=f"asset_{instrument_index:02d}",
                        signal=signal,
                        signal_at=f"2024-02-{day - 1:02d}T15:00:00+08:00",
                        signal_available_at=f"2024-02-{day - 1:02d}T15:01:00+08:00",
                        average_daily_value=10_000_000.0,
                        liquidity_available_at=f"2024-02-{day - 1:02d}T15:01:00+08:00",
                        execution_at=f"2024-02-{day:02d}T09:30:00+08:00",
                        return_end_at=f"2024-02-{day + 1:02d}T09:30:00+08:00",
                        forward_return=(instrument_index - 4.5) * 0.002 + market_noise,
                    )
                )
        panels[schema.fingerprint] = tuple(rows)

    configurations = tuple(
        DiscoveryCpcvScore(
            schema_id=schema.schema_id,
            fingerprint=schema.fingerprint,
            trial_id=f"prior_{index}",
            trial_number=index,
            mean_path_rank_ic=0.05 - index * 0.01,
            positive_paths=10,
            path_scores={f"path_{path}": 0.05 - index * 0.01 for path in range(10)},
        )
        for index, schema in enumerate(schemas, start=1)
    )
    cpcv = DiscoveryCpcvReport(
        method_version="test",
        campaign_id=campaign.campaign_id,
        experiment_id=experiment_id,
        cpcv_manifest_sha256="manifest",
        hygiene_passed=True,
        configurations=configurations,
        selected_fingerprint=schemas[0].fingerprint,
        pbo=PBOResult("test", 0.0, (), 10, 10, 2, "manifest"),
        signal_gate_passed=True,
        validation_window_opened=False,
        decision="PASS_SIGNAL_GATE",
    )
    report, baselines = run_discovery_execution(
        registry,
        campaign,
        cpcv,
        tuple(generated),
        panels,
        snapshot_id=registry.experiment_snapshot_id(experiment_id),
        code_version="test",
        window=ScreeningWindow(
            "2024-01-01",
            "2024-12-31",
            "2025-01-01",
            "2025-12-31",
            "2026-01-01",
            "2026-12-31",
        ),
        horizon_sessions=1,
        config=DiscoveryExecutionConfig(
            top_k=3,
            placebo_repetitions=19,
            all_candidate_court=all_candidate_court,
            minimum_annualized_sharpe=1_000.0,
            maximum_drawdown=0.01,
        ),
        prior_inferential_trials=52,
    )
    assert len(report.configurations) == 2
    assert len(baselines) == (5 if all_candidate_court else 3)
    assert len(report.candidate_courts) == (2 if all_candidate_court else 1)
    assert all(
        bool(score.doubled_cost_trial_id) is all_candidate_court
        for score in report.configurations
    )
    assert all(
        (score.doubled_cost_net_total_return is not None) is all_candidate_court
        for score in report.configurations
    )
    if all_candidate_court:
        assert any(
            abs(score.empirical_skewness) > 0
            for score in report.candidate_courts
        )
    else:
        assert report.candidate_courts[0].empirical_skewness == 0
        assert report.candidate_courts[0].empirical_excess_kurtosis == 0
    assert report.walk_forward.blocks
    assert report.walk_forward.periods > 0
    assert report.walk_forward.passed is False
    assert report.alpha_court.recorded_trial_count == (56 if all_candidate_court else 54)
    assert registry.trial_count(experiment_id) == (4 if all_candidate_court else 2)
