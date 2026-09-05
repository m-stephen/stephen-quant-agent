from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.discovery.search_power_dsl import (
    generate_static_catalog,
    score_vector,
    select_label_budget,
    validate_candidate,
)
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.workflows import v113_search_power_lab as lab


def _spec(tmp_path: Path) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(
        json.dumps({"version": "11.3.0", "real_label_budget": 1000}),
        encoding="utf-8",
    )
    return path


def test_static_catalog_and_real_label_budget_are_deterministic() -> None:
    first = generate_static_catalog()
    second = generate_static_catalog()
    assert first.unique_count >= 10_000
    assert first.catalog_sha256 == second.catalog_sha256
    selected = select_label_budget(first)
    assert len(selected) == 1_000
    assert len({item.candidate_id for item in selected}) == 1_000
    assert {item.domain for item in selected} == {
        "price_liquidity_state",
        "industry_relative_flow",
        "auction_close_chip_gate",
    }


def test_complete_candidate_identity_rejects_mapping_mutation() -> None:
    candidate = select_label_budget(generate_static_catalog(), 1)[0]
    validate_candidate(candidate)
    with pytest.raises(ValueError, match="identity"):
        validate_candidate(replace(candidate, portfolio_mapping="POST_RESULT_TOP20"))


def test_score_vector_supports_canonical_operator() -> None:
    candidate = next(
        item
        for item in generate_static_catalog().candidates
        if item.operator == "centered_interaction" and item.direction == 1
    )
    ranks = {field.name: [0.25, 0.75] for field in candidate.fields}
    assert score_vector(candidate, ranks) == [0.25, 0.25]


def test_one_time_state_rejects_second_consumption(tmp_path: Path) -> None:
    path = tmp_path / "consumed.json"
    lab._exclusive_json(path, {"state": "CONSUMED"})
    with pytest.raises(ValueError, match="already consumed"):
        lab._exclusive_json(path, {"state": "CONSUMED"})


def test_calibration_audit_is_fail_closed_and_one_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidates = select_label_budget(generate_static_catalog())
    failing = {
        "semantic_top10_recovery": 0.0,
        "direction_recovery": 0.0,
        "horizon_recovery": 0.0,
        "median_signal_rank_correlation": 0.0,
        "median_exposure_overlap": 0.0,
        "path_fwer": 1.0,
        "null_paths": 100,
    }
    monkeypatch.setattr(lab, "_calibration_payload", lambda *args, **kwargs: (failing, ()))
    result = lab.run_calibration_audit(candidates, state_root=tmp_path, spec_sha256="0" * 64)
    assert result.decision == "SEARCH_ENGINE_NOT_READY"
    with pytest.raises(ValueError, match="already consumed"):
        lab.run_calibration_audit(candidates, state_root=tmp_path, spec_sha256="0" * 64)


def test_failed_audit_never_reads_real_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calibration = lab.CalibrationResult(
        "SEARCH_ENGINE_NOT_READY", 24, 0, 0, 0, 0, 0, 100, 1, 1, 0,
        "a" * 64, "b" * 64, False, ("NULL_FWER",),
    )
    monkeypatch.setattr(lab, "run_calibration_audit", lambda *args, **kwargs: calibration)
    monkeypatch.setattr(
        lab,
        "_cross_source_panel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("label read")),
    )
    report = lab.run_v113_search_power_lab(
        tmp_path,
        registry=ExperimentRegistry(tmp_path / "registry.sqlite3"),
        state_root=tmp_path / "state",
        output_dir=tmp_path / "output",
        code_version="test",
        spec_path=_spec(tmp_path),
    )
    assert not report.real_label_authorized
    assert report.label_evaluated_trials == 0
    assert report.diagnostic_holdout_state == "UNOPENED"


def test_portfolio_evaluation_respects_industry_cap() -> None:
    candidate = next(
        item
        for item in generate_static_catalog().candidates
        if item.domain == "industry_relative_flow" and item.operator == "rank"
    )
    fields = {field.name: tuple(index / 100 for index in range(80)) for field in candidate.fields}
    day = lab._PreparedDay(
        "2022-01-03",
        "2022-01-04",
        tuple(f"S{index:03d}" for index in range(80)),
        tuple(f"I{index // 10}" for index in range(80)),
        fields,
        tuple(0.001 * (index % 5) for index in range(80)),
        tuple(100_000_000.0 for _ in range(80)),
        0.002,
    )
    holdings = lab._select_holdings(
        day,
        score_vector(candidate, day.ranks),
        candidate,
        (),
        universe_variant=0,
    )
    counts = {}
    industry = dict(zip(day.instruments, day.industries, strict=True))
    for name in holdings:
        counts[industry[name]] = counts.get(industry[name], 0) + 1
    assert len(holdings) == 40
    assert max(counts.values()) <= 5


def test_cli_exposes_v113_command() -> None:
    args = build_parser().parse_args(
        [
            "v11.3-search-power",
            "--warehouse-root",
            "warehouse",
            "--state-root",
            "state",
        ]
    )
    assert args.command == "v11.3-search-power"
