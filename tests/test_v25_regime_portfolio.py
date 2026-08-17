from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from stephen_quant.baseline import (
    BaselineConfig,
    BaselineLineage,
    BaselineObservation,
    run_momentum_topk,
)
from stephen_quant.cli import build_parser
from stephen_quant.workflows import (
    V25PolicyScore,
    apply_v25_policy,
    classify_v25_regimes,
    load_v25_regime_portfolio_config,
    select_v25_policy,
    strategy_family_pbo,
    verify_v25_regime_portfolio_replay,
)


def _row(
    execution_at: str,
    instrument: str,
    signal: float,
    *,
    eligible: bool = True,
) -> BaselineObservation:
    day = execution_at[:10]
    end_day = "2022-01-20" if day == "2022-01-03" else "2022-02-20"
    return BaselineObservation(
        instrument=instrument,
        signal=signal,
        signal_at=f"{day}T00:00:00+08:00",
        signal_available_at=f"{day}T09:00:00+08:00",
        average_daily_value=100_000_000.0,
        liquidity_available_at=f"{day}T09:00:00+08:00",
        execution_at=execution_at,
        return_end_at=f"{end_day}T15:00:00+08:00",
        forward_return=0.01,
        eligible=eligible,
    )


def _score(
    policy_id: str, sharpe: float, drawdown: float, returns: tuple[float, ...]
) -> V25PolicyScore:
    return V25PolicyScore(
        policy_id,
        "trial",
        1,
        46,
        sharpe / 12**0.5,
        sharpe,
        0.1,
        drawdown,
        1.0,
        100.0,
        0.0,
        returns,
    )


def test_v25_config_freezes_two_policy_epoch() -> None:
    config = load_v25_regime_portfolio_config("configs/v2.5-regime-portfolio.json")

    assert config.prior_trial_count == 45
    assert config.regime_threshold == 0.0
    assert config.prior_evidence_sha256 == config.calculated_evidence_sha256


def test_v25_config_rejects_threshold_or_evidence_tamper(tmp_path: Path) -> None:
    payload = json.loads(Path("configs/v2.5-regime-portfolio.json").read_text())
    payload["regime_threshold"] = 0.1
    threshold = tmp_path / "threshold.json"
    threshold.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen at zero"):
        load_v25_regime_portfolio_config(threshold)

    payload["regime_threshold"] = 0.0
    payload["prior_net_total_return"] = 2.0
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash"):
        load_v25_regime_portfolio_config(evidence)


def test_v25_regime_and_policies_are_point_in_time_and_frozen() -> None:
    dates = ("2022-01-03T09:30:00+08:00", "2022-02-03T09:30:00+08:00")
    residual = tuple(
        _row(date, instrument, signal)
        for date, values in zip(dates, ((0.7, 0.4), (0.5, 0.2)), strict=True)
        for instrument, signal in zip(("000001.SZ", "000002.SZ"), values, strict=True)
    )
    control = tuple(
        _row(date, instrument, signal)
        for date, values in zip(dates, ((0.2, 0.1), (-0.2, -0.1)), strict=True)
        for instrument, signal in zip(("000001.SZ", "000002.SZ"), values, strict=True)
    )

    regimes = classify_v25_regimes(control, direction=1, threshold=0.0)
    cash = apply_v25_policy(
        residual,
        control,
        regimes,
        policy_id="risk_off_cash",
        target_direction=1,
        control_direction=1,
    )
    fallback = apply_v25_policy(
        residual,
        control,
        regimes,
        policy_id="risk_off_momentum_fallback",
        target_direction=1,
        control_direction=1,
    )

    assert tuple(item.regime for item in regimes) == ("RISK_ON", "RISK_OFF")
    assert all(item.point_in_time_visible for item in regimes)
    assert all(not row.eligible for row in cash if row.execution_at == dates[1])
    assert tuple(row.signal for row in fallback if row.execution_at == dates[1]) == (-0.2, -0.1)


def test_baseline_can_liquidate_to_cash_when_explicitly_enabled() -> None:
    first = _row("2022-01-03T09:30:00+08:00", "000001.SZ", 1.0)
    second = replace(
        _row("2022-02-03T09:30:00+08:00", "000001.SZ", 1.0),
        eligible=False,
    )
    report = run_momentum_topk(
        (first, second),
        BaselineLineage("factor", "1", "snapshot", "experiment", "trial", "code"),
        BaselineConfig(top_k=1, periods_per_year=12, allow_empty_selection=True),
        initial_nav=1_000_000.0,
    )

    assert report.periods[1].selected_instruments == ()
    assert report.periods[1].cash_after_execution > 0


def test_v25_selection_and_policy_pbo_are_deterministic() -> None:
    baseline = _score("v23_frozen_baseline", 0.6, -0.2, (0.01, -0.01) * 6)
    cash = _score("risk_off_cash", 0.7, -0.1, (0.02, 0.0, -0.01) * 4)
    fallback = _score("risk_off_momentum_fallback", 0.7, -0.15, (0.01, 0.02, -0.02) * 4)

    assert select_v25_policy((fallback, cash)).policy_id == "risk_off_cash"
    first = strategy_family_pbo((baseline, cash, fallback), blocks=4)
    second = strategy_family_pbo((baseline, cash, fallback), blocks=4)
    assert first == second
    assert first.scope == "PORTFOLIO_POLICY_SELECTION_ONLY"
    assert first.complete_search_coverage is False
    assert 0 <= first.probability <= 1


def test_v25_replay_is_offline_and_fails_on_tamper(tmp_path: Path) -> None:
    artifacts = {
        "json": tmp_path / "v2.5-regime-portfolio.json",
        "markdown_en": tmp_path / "v2.5-regime-portfolio.en.md",
        "markdown_zh": tmp_path / "v2.5-regime-portfolio.zh.md",
    }
    for name, path in artifacts.items():
        path.write_text(name, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in artifacts.items()
    }
    manifest = tmp_path / "v2.5-replay-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "replay_version": "v2.5-regime-portfolio-replay-1.0.0",
                "cumulative_trial_count": 47,
                "pbo_scope": "PORTFOLIO_POLICY_SELECTION_ONLY",
                "validation_window_opened": False,
                "test_window_opened": False,
                "artifacts": hashes,
            }
        ),
        encoding="utf-8",
    )

    assert verify_v25_regime_portfolio_replay(manifest).passed
    artifacts["json"].write_text("tampered", encoding="utf-8")
    assert verify_v25_regime_portfolio_replay(manifest).mismatches == ("json",)


def test_v25_cli_replay_and_kill_need_no_local_paths() -> None:
    parser = build_parser()
    replay = parser.parse_args(
        ["v2-regime-portfolio", "--mode", "replay", "--replay-manifest", "frozen.json"]
    )
    kill = parser.parse_args(["v2-regime-portfolio", "--mode", "kill"])

    assert replay.paths_config is None
    assert kill.paths_config is None
