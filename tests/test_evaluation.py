from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from stephen_quant.evaluation import (
    EvaluationError,
    EvaluationLineage,
    EvaluationObservation,
    average_ranks,
    evaluate_alpha,
    pearson_correlation,
    spearman_correlation,
    write_alpha_card,
)
from stephen_quant.factors import build_seed_registry


def _lineage() -> EvaluationLineage:
    return EvaluationLineage(
        factor_id="ret_60",
        factor_version="1.0.0",
        snapshot_id="snap_fixture",
        experiment_id="exp_fixture",
        trial_id="trial_fixture",
        code_version="test-sha",
    )


def _observations() -> list[EvaluationObservation]:
    instruments = ("A", "B", "C", "D")
    factor_values = (1.0, 2.0, 3.0, 4.0)
    five_day_returns = (
        (0.01, 0.02, 0.03, 0.04),
        (0.01, 0.02, 0.04, 0.03),
        (0.01, 0.03, 0.02, 0.04),
        (0.02, 0.01, 0.03, 0.04),
    )
    ten_day_returns = (0.04, 0.03, 0.02, 0.01)
    start = date(2025, 1, 2)
    rows: list[EvaluationObservation] = []
    for date_index in range(4):
        as_of = start + timedelta(days=date_index * 14)
        timestamp = f"{as_of.isoformat()}T15:00:00+08:00"
        available = f"{as_of.isoformat()}T15:01:00+08:00"
        label_start = f"{(as_of + timedelta(days=1)).isoformat()}T09:30:00+08:00"
        for horizon, returns, days in (
            ("5d", five_day_returns[date_index], 5),
            ("10d", ten_day_returns, 10),
        ):
            label_end = f"{(as_of + timedelta(days=days)).isoformat()}T15:00:00+08:00"
            for instrument, factor, forward_return in zip(
                instruments, factor_values, returns, strict=True
            ):
                rows.append(
                    EvaluationObservation(
                        timestamp=timestamp,
                        instrument=instrument,
                        factor_value=factor,
                        factor_available_at=available,
                        label_start_at=label_start,
                        label_end_at=label_end,
                        forward_return=forward_return,
                        horizon=horizon,
                        subperiod="H1" if date_index < 2 else "H2",
                        regime="bull" if date_index % 2 == 0 else "bear",
                    )
                )
    return rows


def test_correlations_and_tied_ranks_are_correct() -> None:
    assert pearson_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert spearman_correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert average_ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]


def test_evaluation_builds_decay_stability_and_redundancy_diagnostics() -> None:
    rows = _observations()
    primary_rows = [row for row in rows if row.horizon == "5d"]
    peer = {(row.timestamp, row.instrument): row.factor_value for row in primary_rows}

    card = evaluate_alpha(
        build_seed_registry().get("ret_60"),
        rows,
        _lineage(),
        peer_factors={"existing_momentum": peer},
    )

    assert card.primary_horizon == "5d"
    assert [metric.horizon for metric in card.horizon_metrics] == ["5d", "10d"]
    assert card.horizon_metrics[0].mean_rank_ic == pytest.approx(0.85)
    assert card.horizon_metrics[0].rank_icir is not None
    assert card.horizon_metrics[0].rank_ic_hit_rate == 1.0
    assert card.horizon_metrics[1].mean_rank_ic == pytest.approx(-1.0)
    assert {item.group for item in card.subperiods} == {"H1", "H2"}
    assert {item.group for item in card.regimes} == {"bear", "bull"}
    assert card.turnover == 0.0
    assert card.correlations[0].mean_rank_correlation == pytest.approx(1.0)


def test_alpha_card_is_deterministic_and_contains_lineage(tmp_path: Path) -> None:
    card = evaluate_alpha(build_seed_registry().get("ret_60"), _observations(), _lineage())

    first = write_alpha_card(card, tmp_path / "first")
    second = write_alpha_card(card, tmp_path / "second")
    payload = json.loads(first.json_path.read_text(encoding="utf-8"))
    markdown = first.markdown_path.read_text(encoding="utf-8")

    assert first.json_sha256 == second.json_sha256
    assert first.markdown_sha256 == second.markdown_sha256
    assert payload["lineage"]["snapshot_id"] == "snap_fixture"
    assert payload["lineage"]["experiment_id"] == "exp_fixture"
    assert payload["lineage"]["trial_id"] == "trial_fixture"
    assert "Alpha Card: ret_60@1.0.0" in markdown


def test_future_information_is_rejected() -> None:
    rows = _observations()
    first = rows[0]
    rows[0] = EvaluationObservation(
        **{
            **first.__dict__,
            "factor_available_at": "2026-12-31T15:00:00+08:00",
        }
    )

    with pytest.raises(EvaluationError, match="future information"):
        evaluate_alpha(build_seed_registry().get("ret_60"), rows, _lineage())


def test_bad_samples_and_lineage_fail_explicitly() -> None:
    rows = _observations()
    too_small = [row for row in rows if row.instrument in {"A", "B"}]
    with pytest.raises(EvaluationError, match="minimum is 3"):
        evaluate_alpha(build_seed_registry().get("ret_60"), too_small, _lineage())

    duplicate = rows + [rows[0]]
    with pytest.raises(EvaluationError, match="duplicate"):
        evaluate_alpha(build_seed_registry().get("ret_60"), duplicate, _lineage())

    bad_lineage = EvaluationLineage(
        factor_id="ret_20",
        factor_version="1.0.0",
        snapshot_id="snap_fixture",
        experiment_id="exp_fixture",
        trial_id="trial_fixture",
        code_version="test-sha",
    )
    with pytest.raises(EvaluationError, match="identity"):
        evaluate_alpha(build_seed_registry().get("ret_60"), rows, bad_lineage)


def test_constant_inputs_are_rejected() -> None:
    with pytest.raises(EvaluationError, match="constant"):
        pearson_correlation([1, 1, 1], [1, 2, 3])
