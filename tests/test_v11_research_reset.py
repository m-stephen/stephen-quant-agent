from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.discovery.portfolio_native import PortfolioObservation, PortfolioPolicy
from stephen_quant.workflows.v11_research_reset import (
    RAW_GLOBAL_TRIALS_AT_FREEZE,
    assert_historical_search_frozen,
    assess_pbo_identifiability,
    build_forward_protocol,
    build_window_ledger,
    forward_status,
    null_placebo,
    run_statistical_contract,
    universe_robustness,
    write_forward_protocol,
)


def _rows(count: int = 80) -> tuple[PortfolioObservation, ...]:
    return tuple(
        PortfolioObservation(
            "2026-09-08",
            f"{index:06d}.SZ",
            index / count,
            index / 1000,
            0.0,
            1_000_000.0 + index * 10_000,
            "2026-09-07T18:00:00+08:00",
            "2026-09-08T09:30:00+08:00",
        )
        for index in range(count)
    )


def test_v11_legacy_historical_search_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="historical V10"):
        assert_historical_search_frozen()


def test_v11_cli_exposes_contract_forward_and_bounded_epoch() -> None:
    parser = build_parser()
    assert parser.parse_args(["v11-statistical-contract"]).command == "v11-statistical-contract"
    forward = parser.parse_args(
        [
            "v11-freeze-forward",
            "--frozen-at",
            "2026-09-05T09:00:00+08:00",
            "--maximum-data-date-at-freeze",
            "2026-08-16",
            "--source-snapshot",
            "a" * 64,
        ]
    )
    assert forward.command == "v11-freeze-forward"
    epoch = parser.parse_args(
        [
            "v11-bounded-epoch",
            "--warehouse-root",
            "warehouse",
            "--feature-snapshot",
            "a" * 64,
            "--contract-result",
            "contract.json",
        ]
    )
    assert epoch.command == "v11-bounded-epoch"


def test_v11_window_ledger_reclassifies_development_and_seals_labels() -> None:
    records = build_window_ledger("2026-08-16")
    assert records[0].state == "DEVELOPMENT_ONLY"
    assert records[0].label_reads == RAW_GLOBAL_TRIALS_AT_FREEZE
    assert records[1].state == "SEALED"
    assert records[1].label_reads == 0
    assert records[2].state == "FORWARD_APPEND_ONLY"


def test_v11_forward_protocol_uses_later_freeze_boundary_and_exact_direction() -> None:
    protocol = build_forward_protocol(
        frozen_at="2026-09-05T09:00:00+08:00",
        maximum_data_date_at_freeze="2026-08-16",
        source_snapshot_id="a" * 64,
        code_version="b" * 40,
    )
    assert protocol.first_eligible_date_exclusive == "2026-09-05"
    assert tuple(item.direction for item in protocol.candidates) == (1, 1)
    assert tuple(item.candidate_id for item in protocol.candidates) == (
        "ec9faf313b03bd78dd999158c994d9a8464149c220c256abca6fa2c96009c1f2",
        "25023e50365dc75cf614bc025ef36296193ac0447e06cc98feb18d4ff4340f7a",
    )
    assert len(protocol.protocol_sha256) == 64


def test_v11_forward_protocol_accepts_powershell_seven_digit_timestamp() -> None:
    protocol = build_forward_protocol(
        frozen_at="2026-09-05T02:20:14.6623815+08:00",
        maximum_data_date_at_freeze="2026-08-16",
        source_snapshot_id="a" * 64,
        code_version="b" * 40,
    )
    assert protocol.frozen_at == "2026-09-05T02:20:14.662381+08:00"
    assert protocol.first_eligible_date_exclusive == "2026-09-05"


def test_v11_forward_status_never_emits_performance_conclusion() -> None:
    protocol = build_forward_protocol(
        frozen_at="2026-09-05T09:00:00+08:00",
        maximum_data_date_at_freeze="2026-08-16",
        source_snapshot_id="a" * 64,
        code_version="b" * 40,
    )
    dates = [f"2026-10-{day:02d}" for day in range(1, 26)]
    status = forward_status(protocol, dates)
    assert status.checkpoint == "RUNTIME_DAY_25"
    assert status.performance_conclusion is None


def test_v11_forward_protocol_is_immutable(tmp_path: Path) -> None:
    protocol = build_forward_protocol(
        frozen_at="2026-09-05T09:00:00+08:00",
        maximum_data_date_at_freeze="2026-08-16",
        source_snapshot_id="a" * 64,
        code_version="b" * 40,
    )
    write_forward_protocol(protocol, tmp_path)
    write_forward_protocol(protocol, tmp_path)
    with pytest.raises(ValueError, match="immutable"):
        write_forward_protocol(replace(protocol, code_version="c" * 40), tmp_path)


def test_v11_universe_robustness_is_not_a_placebo_p_value() -> None:
    report = universe_robustness(_rows(), PortfolioPolicy(top_k=20), samples=19)
    assert report.samples == 19
    assert report.q05_return <= report.q25_return <= report.median_return
    assert not hasattr(report, "p_value")


def test_v11_null_fails_closed_when_exchangeable_pool_is_too_small() -> None:
    result = null_placebo(
        _rows(20),
        PortfolioPolicy(top_k=20),
        mode="universe_construction",
    )
    assert result.status == "NOT_IDENTIFIABLE"
    assert result.p_value is None


def test_v11_pbo_identifiability_rejects_repeated_rankings() -> None:
    repeated = assess_pbo_identifiability(
        {"a": {"f1": 2.0, "f2": 2.0}, "b": {"f1": 1.0, "f2": 1.0}},
        {"a": {"f1": 1.0, "f2": 1.0}, "b": {"f1": 0.0, "f2": 0.0}},
    )
    assert repeated.status == "NOT_IDENTIFIABLE"
    changed = assess_pbo_identifiability(
        {"a": {"f1": 2.0, "f2": 0.0}, "b": {"f1": 0.0, "f2": 2.0}},
        {"a": {"f1": 1.0, "f2": 0.0}, "b": {"f1": 0.0, "f2": 1.0}},
    )
    assert changed.status == "IDENTIFIABLE"


def test_v11_contract_calibration_is_deterministic_and_machine_readable(tmp_path: Path) -> None:
    first = run_statistical_contract(tmp_path / "first")
    second = run_statistical_contract(tmp_path / "second")
    assert first == second
    assert first.decision == "READY_FOR_BOUNDED_EPOCH"
    assert first.raw_global_trial_count == 743
    assert first.planted_signal_null.p_value is not None
    assert first.planted_signal_null.p_value <= 0.05
    assert first.noise_signal_null.p_value is not None
    assert first.noise_signal_null.p_value > 0.05
    payload = json.loads(
        (tmp_path / "first" / "STATISTICAL_CONTRACT_RESULT.json").read_text()
    )
    assert payload["report_sha256"] == first.report_sha256
