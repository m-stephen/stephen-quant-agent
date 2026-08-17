from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.v2 import (
    MarginalObservation,
    MarginalPolicy,
    ReferenceLibraryRecord,
    evaluate_marginal_candidate,
    rank_marginal_candidates,
)


def _reference() -> ReferenceLibraryRecord:
    return ReferenceLibraryRecord(
        library_id="reference_v1_8_21",
        version="1.0.0",
        portfolio_mapping="exclude_bottom_decile_3m",
        source_experiment_id="exp_v1821",
        source_snapshot_id="snapshot_research_2022_2024",
        config_sha256="a" * 64,
        research_only=True,
        validated_alpha=False,
    )


def _observations(kind: str) -> tuple[MarginalObservation, ...]:
    rows: list[MarginalObservation] = []
    for fold_index in range(2):
        for date_index in range(7):
            phase = "train" if date_index < 3 else "test"
            for instrument_index in range(10):
                reference = float(instrument_index) - 4.5
                orthogonal = (reference * reference - 8.25) / 8
                date_scale = 1 + 0.1 * ((date_index % 3) - 1)
                forward = date_scale * (0.003 * reference + 0.001 * orthogonal)
                noise = 0.01 * (((instrument_index * 3 + date_index) % 5) - 2)
                candidate = reference + noise if kind == "redundant" else orthogonal
                rows.append(
                    MarginalObservation(
                        fold_id=f"fold_{fold_index}",
                        phase=phase,  # type: ignore[arg-type]
                        date=f"202{3 + fold_index}-01-{date_index + 2:02d}",
                        instrument=f"stock_{instrument_index:02d}",
                        candidate_value=candidate,
                        reference_value=reference,
                        forward_return=forward,
                        adv=50_000_000 + instrument_index * 1_000_000,
                    )
                )
    return tuple(rows)


def test_orthogonal_lower_ic_candidate_ranks_above_high_ic_redundant_candidate() -> None:
    policy = MarginalPolicy(residual_blend=0.75)
    redundant = evaluate_marginal_candidate(
        "high_ic_redundant",
        _observations("redundant"),
        _reference(),
        complexity_cost=1,
        data_cost=0,
        policy=policy,
    )
    orthogonal = evaluate_marginal_candidate(
        "lower_ic_orthogonal",
        _observations("orthogonal"),
        _reference(),
        complexity_cost=1,
        data_cost=0,
        policy=policy,
    )
    assert redundant.standalone_ic > orthogonal.standalone_ic
    assert abs(redundant.redundancy_correlation) > 0.99
    assert abs(orthogonal.redundancy_correlation) < 0.05
    assert orthogonal.residual_ic > redundant.residual_ic
    ranked = rank_marginal_candidates((redundant, orthogonal))
    assert ranked[0].candidate_id == "lower_ic_orthogonal"
    assert ranked[0].marginal_utility > ranked[1].marginal_utility


def test_residual_models_are_fit_on_train_rows_only() -> None:
    original_rows = _observations("orthogonal")
    original = evaluate_marginal_candidate(
        "orthogonal",
        original_rows,
        _reference(),
        complexity_cost=1,
        data_cost=0,
    )
    changed_test = tuple(
        replace(row, candidate_value=row.candidate_value + 1000) if row.phase == "test" else row
        for row in original_rows
    )
    changed = evaluate_marginal_candidate(
        "orthogonal",
        changed_test,
        _reference(),
        complexity_cost=1,
        data_cost=0,
    )
    assert changed.fold_models == original.fold_models
    assert all(model.fitted_train_rows == 30 for model in original.fold_models)
    assert all(model.evaluated_test_rows == 40 for model in original.fold_models)


def test_scorecard_contains_replayable_incremental_portfolio_metrics() -> None:
    first = evaluate_marginal_candidate(
        "orthogonal",
        _observations("orthogonal"),
        _reference(),
        complexity_cost=2,
        data_cost=1,
    )
    second = evaluate_marginal_candidate(
        "orthogonal",
        _observations("orthogonal"),
        _reference(),
        complexity_cost=2,
        data_cost=1,
    )
    assert first == second
    assert first.library_status == "reference_only"
    assert first.capacity > 0
    assert first.delta_net_sharpe == (
        first.augmented_long_only.net_sharpe - first.reference_long_only.net_sharpe
    )
    assert first.augmented_long_short.capacity > 0
    assert first.complexity_cost == 2
    assert first.data_cost == 1


def test_research_only_reference_cannot_be_promoted_by_marginal_engine() -> None:
    invalid = replace(_reference(), validated_alpha=True)
    with pytest.raises(ValueError, match="research-only reference"):
        evaluate_marginal_candidate(
            "candidate",
            _observations("orthogonal"),
            invalid,
            complexity_cost=0,
            data_cost=0,
        )
