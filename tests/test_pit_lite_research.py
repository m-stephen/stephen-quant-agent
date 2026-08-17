from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.workflows.pit_lite_research import (
    PitLiteReport,
    VariantResult,
    _cluster,
    _fit_clusters,
    _fit_pc,
    _pc_score,
    load_pit_lite_config,
)
from stephen_quant.workflows.v27_risk_controls import (
    PRICE_CONTROL_SCHEMA,
    NormalizedRiskExposure,
)


def _rows() -> tuple[NormalizedRiskExposure, ...]:
    return tuple(
        NormalizedRiskExposure(
            instrument=f"{index:06d}.SZ",
            decision_at="2022-12-30T15:01:00+08:00",
            feature_names=PRICE_CONTROL_SCHEMA,
            values=(
                float(index % 5),
                float((index * 2) % 7),
                float(index) / 10,
                float(index % 3),
                -float(index % 4),
            ),
            fit_state_sha256="a" * 64,
        )
        for index in range(40)
    )


def test_pca_and_clusters_are_deterministic() -> None:
    rows = _rows()
    first_pc = _fit_pc(rows, 50)
    second_pc = _fit_pc(rows, 50)
    first_clusters = _fit_clusters(rows, 4, 20)
    second_clusters = _fit_clusters(rows, 4, 20)
    assert first_pc == second_pc
    assert first_clusters == second_clusters
    assert _pc_score(first_pc, rows[0]) == _pc_score(second_pc, rows[0])
    assert _cluster(first_clusters, rows[-1]) == _cluster(second_clusters, rows[-1])


def test_config_freezes_candidate_window_trials_and_industry_evidence(tmp_path: Path) -> None:
    source = Path("configs/v2.9-pit-lite-research.json")
    config = load_pit_lite_config(source)
    assert config.issue_number == 98
    assert config.prior_inferential_trials == 51
    assert config.missing_holding_policy == "stale_zero_return"
    assert config.evaluation_years == (2023, 2024)
    assert config.industry_classification == "B_CURRENT_LABEL_BACKFILL"

    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["candidate_id"] = "post_result_mutation"
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate formula/horizon changed"):
        load_pit_lite_config(changed)


def test_cli_exposes_only_local_configured_pit_lite_entrypoint() -> None:
    args = build_parser().parse_args(
        [
            "pit-lite-research",
            "--paths-config",
            "configs/qd-paths.local.json",
            "--ingested-at",
            "2024-12-31T23:59:59+08:00",
        ]
    )
    assert args.config == "configs/v2.9-pit-lite-research.json"
    assert not hasattr(args, "daily_dir")


def test_report_with_variant_dataclasses_is_json_serializable() -> None:
    variant = VariantResult(
        name="RAW",
        observations=100,
        periods=10,
        mean_rank_ic=0.01,
        yearly_rank_ic={"2023": 0.01, "2024": 0.02},
        net_total_return_3m=0.1,
        annualized_net_sharpe_3m=0.5,
        max_drawdown_3m=-0.1,
        total_cost_3m=100.0,
        net_total_return_20m=0.08,
        annualized_net_sharpe_20m=0.4,
        max_drawdown_20m=-0.12,
        capacity_clipped_notional_20m=0.0,
        signal_placebo_p_value=0.005,
        return_placebo_p_value=0.005,
        dsr_probability=0.96,
    )
    report = PitLiteReport(
        method_version="test",
        decision="NO_ROBUST_ALPHA_POPULATION",
        candidate_status="NO_ROBUST_ALPHA_POPULATION",
        experiment_id="exp_test",
        trial_id="trial_test",
        local_trial_number=1,
        cumulative_inferential_trials=52,
        config_sha256="a" * 64,
        source_snapshot_sha256="b" * 64,
        industry_audit_result_sha256="c" * 64,
        industry_classification="B_CURRENT_LABEL_BACKFILL",
        industry_proxy_used_for_signal=False,
        evaluation_years=(2023, 2024),
        walk_forward_states={},
        variants=(variant,),
        inherited_pbo=0.0,
        inherited_pbo_scope="test",
        inferential_trial_delta=1,
        validation_2025_accesses=0,
        final_2026_accesses=0,
        checks=(("TEST", False, "test"),),
        result_sha256="d" * 64,
    )
    payload = json.loads(report.to_json())
    assert payload["variants"][0]["name"] == "RAW"
