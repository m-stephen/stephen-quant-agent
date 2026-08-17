from __future__ import annotations

from stephen_quant.discovery import (
    CandidateScreenScore,
    FactorSchema,
    GeneratedCandidate,
    ScreeningReport,
    build_research_memory,
    mutate_schema,
)


def _schema() -> FactorSchema:
    return FactorSchema(
        schema_id="price_momentum_20_5d",
        version="1.0.0",
        name="Price momentum",
        event="price",
        context="all_market",
        quality="complete_daily_bars",
        direction=1,
        output="cross_sectional_score",
        horizon="5d",
        formula="period_return(close, 20)",
        data_sources=("qd_daily",),
        required_fields=("close",),
        availability_lag_days=0,
        economic_rationale="Underreaction may create continuation.",
    )


def test_research_memory_records_failure_duplicate_and_research_only_policy() -> None:
    schema = _schema()
    candidates = (
        GeneratedCandidate(schema, "proposal_1", 1, True),
        GeneratedCandidate(schema, "proposal_2", 2, False),
    )
    score = CandidateScreenScore(
        schema_id=schema.schema_id,
        fingerprint=schema.fingerprint,
        proposal_id="proposal_1",
        trial_id="trial_1",
        trial_number=1,
        coverage=0.5,
        dates=10,
        observations=100,
        mean_rank_ic=None,
        maximum_selected_correlation=None,
        decision="screened_out",
        reason="coverage below threshold",
    )
    memory = build_research_memory(
        candidates,
        ScreeningReport("campaign_1", 20, (score,), ()),
        None,
        None,
        experiment_id="exp_1",
    )
    assert memory.feedback_partition == "research_only"
    assert [item.outcome for item in memory.experiences] == ["screened_out", "duplicate"]
    assert {item.family for item in memory.experiences} == {"price_momentum"}
    assert memory.recommendations[0].operation == "explore"
    assert "Research Memory" in memory.to_markdown("en")
    assert "研究记忆" in memory.to_markdown("zh")


def test_schema_mutation_preserves_parent_lineage() -> None:
    parent = _schema()
    child = mutate_schema(
        parent,
        schema_id="price_momentum_40_5d",
        formula="period_return(close, 40)",
    )
    assert child.parent_fingerprints == (parent.fingerprint,)
    assert child.fingerprint != parent.fingerprint
