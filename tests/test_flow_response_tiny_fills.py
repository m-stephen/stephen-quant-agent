"""Synthetic share/notional dimensional edge cases; no market data or Trial."""

import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from stephen_quant.baseline.stateful import StatefulBar, TargetAllocation, run_stateful_execution
from stephen_quant.discovery.flow_response_accounts import execute_response_account
from stephen_quant.discovery.flow_response_replay import audit_response_account
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import _finish_account


def tiny_account(*, liquidation, cost=82, mode="target_changes"):
    prices = (0.15, 0.07, 0.01) if liquidation else (0.01, 0.01, 0.01)
    sessions, targets = [], []
    for i, price in enumerate(prices):
        day = f"2023-01-0{i + 3}"
        clock = day + "T08:00:00+08:00"
        sessions.append(
            (
                StatefulBar(
                    day,
                    "SYNTHETIC",
                    price,
                    price,
                    1e6 if liquidation else 1e-13,
                    clock,
                    forced_exit=liquidation and i == 2,
                ),
            )
        )
        targets.append(TargetAllocation(day, clock, {"SYNTHETIC": 0.025} if i == 0 else {}, True))
    sessions, targets = tuple(sessions), tuple(targets)
    report = execute_response_account(sessions, targets, roundtrip_bps=cost)
    if mode == "full_target":
        report = run_stateful_execution(
            sessions,
            targets,
            replace(report.config, rebalance_mode=mode),
            initial_nav=3_000_000,
            retain_details=True,
        )
    return sessions, targets, report


@pytest.mark.parametrize("cost", [82, 164])
@pytest.mark.parametrize("mode", ["target_changes", "full_target"])
@pytest.mark.parametrize("liquidation", [False, True])
def test_nonzero_subpicoyuan_fill_must_update_shares(liquidation, mode, cost):
    sessions, targets, report = tiny_account(liquidation=liquidation, cost=cost, mode=mode)
    if liquidation:
        assert report.periods[1].marks[0].shares > 1e-12
        assert 0 < abs(report.periods[2].orders[0].executed_notional) < 1e-12
        assert report.periods[2].marks == ()
    else:
        assert 0 < report.periods[0].orders[0].executed_notional < 1e-12
        assert report.periods[0].marks[0].shares > 1e-12
    assert audit_response_account(report, sessions, targets, roundtrip_bps=cost, mode=mode)["pass"]


@pytest.mark.parametrize("kind", ["missing_mark", "duplicate_mark", "restricted", "missing_bar"])
def test_tiny_fill_is_not_a_license_to_ignore_held_names_or_source(kind):
    sessions, targets, report = tiny_account(liquidation=False)
    periods = list(report.periods)
    if kind == "missing_mark":
        periods[0] = replace(periods[0], marks=())
    elif kind == "duplicate_mark":
        periods[0] = replace(periods[0], marks=periods[0].marks * 2)
    elif kind == "restricted":
        sessions = ((replace(sessions[0][0], can_buy_open=False),),) + sessions[1:]
    else:
        sessions = ((),) + sessions[1:]
    with pytest.raises(ValueError):
        audit_response_account(
            replace(report, periods=tuple(periods)), sessions, targets, roundtrip_bps=82
        )


def test_failed_account_is_preserved_but_never_recorded_as_complete(tmp_path, monkeypatch):
    sessions, targets, report = tiny_account(liquidation=True)

    def fail(*args, **kwargs):
        raise ValueError("synthetic account audit failure")

    def forbidden(*args, **kwargs):
        raise AssertionError("Failed account cannot become a native completed result")

    monkeypatch.setattr("stephen_quant.workflows.flow_response_epoch.audit_response_account", fail)
    registry = SimpleNamespace(record_trial_result=forbidden)
    with pytest.raises(ValueError, match="synthetic account audit failure"):
        _finish_account(
            registry,
            "synthetic-trial",
            tmp_path,
            "risk-82",
            report,
            sessions,
            targets,
            82,
            "a" * 64,
        )
    saved = tmp_path / "unverified_account_reports/risk-82.json"
    assert json.loads(saved.read_bytes()) == json.loads(json.dumps(asdict(report)))
    receipt = json.loads((tmp_path / "ACCOUNT_AUDIT_FAILURE.json").read_bytes())
    assert receipt["account_sha256"] == file_sha(saved)
    assert receipt["target_sha256"] == "a" * 64
    assert receipt["key"] == "risk-82" and receipt["trial_id"] == "synthetic-trial"
    assert not receipt["completed_result"] and not receipt["validated_alpha"]
    assert not (tmp_path / "account_reports").exists()
    assert not (tmp_path / "RESULT.json").exists()
