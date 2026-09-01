from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.discovery import (
    PortfolioObservation,
    PortfolioPolicy,
    build_proposal_lineage,
    evaluate_portfolio_native,
    freeze_proposal_packet,
    generate_structural_proposals,
    load_cached_llm_proposals,
    run_search_calibration,
)
from stephen_quant.workflows.v90_alpha_discovery import (
    frozen_v81_proposal,
    load_v90_config,
    run_v90_planning,
)
from stephen_quant.workflows.v90_empirical import _segment_rows


def test_search_calibration_recovers_signal_and_exposes_overfit() -> None:
    first = run_search_calibration()
    second = run_search_calibration()
    assert first == second
    assert first.passed
    assert first.planted_rank == 1
    assert first.planted_holdout_rank_ic > 0
    assert first.leakage_positive_control_detected
    assert first.purge_embargo_overlap_count == 0
    discovery = [item.best_discovery_rank_ic for item in first.overfit_curve]
    assert discovery == sorted(discovery)


def test_structural_grammar_is_direction_and_horizon_complete() -> None:
    proposals = generate_structural_proposals(budget=512)
    v81 = frozen_v81_proposal()
    assert any(item.schema.formula == v81.schema.formula for item in proposals)
    grouped: dict[tuple[str, str], set[int]] = {}
    for item in proposals:
        grouped.setdefault((item.schema.formula, item.schema.horizon), set()).add(
            item.schema.direction
        )
    assert all(directions == {-1, 1} for directions in grouped.values())
    assert {item.schema.horizon for item in proposals} == {"1d", "5d", "20d"}
    assert len({build_proposal_lineage(item).mechanism_family for item in proposals}) >= 8


def test_lineage_packet_is_stable_and_required_candidate_is_first_class() -> None:
    candidate = frozen_v81_proposal()
    duplicate = replace(candidate, proposal=candidate.proposal)
    first = freeze_proposal_packet(
        (candidate, duplicate),
        empirical_budget=1,
        required_proposal_ids=frozenset({candidate.proposal_id}),
    )
    second = freeze_proposal_packet(
        (duplicate, candidate),
        empirical_budget=1,
        required_proposal_ids=frozenset({candidate.proposal_id}),
    )
    assert first.packet_sha256 == second.packet_sha256
    assert first.proposal_ids == (candidate.proposal_id,)


def test_cached_llm_packet_requires_exact_bytes(tmp_path) -> None:
    packet = tmp_path / "packet.json"
    packet.write_text(
        json.dumps(
            [
                {
                    "formula": "period_return(close, 5)",
                    "hypothesis": "A frozen offline hypothesis.",
                    "research_form": "continuous_ranking",
                    "horizon": "5d",
                    "direction": -1,
                }
            ]
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(packet.read_bytes()).hexdigest()
    assert len(
        load_cached_llm_proposals(packet, provider_id="llm:offline-fixture", expected_sha256=digest)
    ) == 1
    with pytest.raises(ValueError, match="hash mismatch"):
        load_cached_llm_proposals(
            packet,
            provider_id="llm:offline-fixture",
            expected_sha256="0" * 64,
        )


def _portfolio_rows() -> tuple[PortfolioObservation, ...]:
    rows = []
    for day, shift in (("2020-01-02", 0), ("2020-01-23", 1), ("2020-02-13", 2)):
        for index in range(6):
            rows.append(
                PortfolioObservation(
                    day,
                    f"S{index}",
                    float(10 - abs(index - shift)),
                    0.02 if index < 4 else -0.01,
                    0.005,
                    100_000_000.0,
                    f"{day}T08:00:00+08:00",
                    f"{day}T09:30:00+08:00",
                )
            )
    return tuple(rows)


def test_portfolio_native_evaluation_applies_buffer_cost_and_capacity() -> None:
    report = evaluate_portfolio_native(
        _portfolio_rows(),
        policy=PortfolioPolicy(top_k=3, rank_buffer=1, periods_per_year=12),
    )
    assert report.periods[0].turnover == pytest.approx(0.5)
    assert report.total_cost > 0
    assert report.capacity_passed
    assert report.capacity_cny >= 3_000_000
    assert report.double_cost_total_return < report.net_excess_total_return
    assert {item.year for item in report.year_attribution} == {"2020"}


def test_portfolio_native_rejects_decision_time_leakage() -> None:
    rows = list(_portfolio_rows())
    rows[0] = replace(rows[0], available_at="2020-01-02T10:00:00+08:00")
    with pytest.raises(ValueError, match="future"):
        evaluate_portfolio_native(
            tuple(rows),
            policy=PortfolioPolicy(top_k=3, rank_buffer=1),
        )


def test_v90_planning_is_label_free_replayable_and_bilingual(tmp_path) -> None:
    first = run_v90_planning(tmp_path / "first")
    second = run_v90_planning(tmp_path / "second")
    assert first.report_sha256 == second.report_sha256
    assert first.readiness == "READY_FOR_CONTROLLED_EMPIRICAL_EPOCH"
    assert not first.labels_read
    assert first.inferential_trial_delta == 0
    assert first.recovered_v81_proposal_id in first.proposal_packet.proposal_ids
    assert (tmp_path / "first" / "v9.0-readiness.zh.md").is_file()
    assert (tmp_path / "first" / "v9.0-readiness.en.md").is_file()
    args = build_parser().parse_args(["v9-alpha-plan"])
    assert args.output == "reports/v9.0-alpha-discovery"
    replay = build_parser().parse_args(["v9-alpha-replay", "--warehouse-root", "warehouse"])
    assert replay.warehouse_root == "warehouse"
    config, daily, multi = load_v90_config("configs/v9.0-alpha-discovery.json")
    assert config.portfolio_policy.initial_nav_cny == 3_000_000
    assert len(daily) == len(multi) == 64


def test_empirical_segment_sampling_is_non_overlapping_and_deterministic() -> None:
    rows = tuple(
        PortfolioObservation(
            f"2020-01-{day:02d}",
            f"S{asset}",
            float(asset),
            0.01,
            0.0,
            100_000_000.0,
            f"2020-01-{day:02d}T08:00:00+08:00",
            f"2020-01-{day:02d}T09:30:00+08:00",
        )
        for day in range(1, 26)
        for asset in range(3)
    )
    selected = _segment_rows(rows, "2020-01-01", "2020-01-25", horizon_sessions=5)
    assert sorted({item.date for item in selected}) == [
        "2020-01-01",
        "2020-01-06",
        "2020-01-11",
        "2020-01-16",
        "2020-01-21",
    ]
