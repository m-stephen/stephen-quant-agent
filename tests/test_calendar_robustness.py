import json
import sqlite3
from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.calendar_robustness import (
    CALENDARS,
    PHASES,
    account_summary,
    assess_calendars,
    calendar_targets,
    combine_sleeves,
)
from stephen_quant.discovery.incremental_alpha import (
    IncrementalHypothesis,
    execute,
    incremental_targets,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.workflows import v119_calendar_epoch as workflow


def pack():
    return (
        IncrementalHypothesis("concentration", 1, "blend", 20),
        IncrementalHypothesis("late_30_return", -1, "blend", 20),
    )


def days(n=60, start=date(2023, 12, 1)):
    result = []
    for i in range(n):
        day = (start + timedelta(days=i)).isoformat()
        features = {
            f"S{s}": {
                "volatility_20": s + 1,
                "concentration": (s + i) % 80,
                "late_30_return": (s - i) % 80,
            }
            for s in range(80)
        }
        bars = tuple(
            StatefulBar(day, name, 10 + i / 10, 10 + i / 10, 10_000_000, f"{day}T08:00:00+08:00")
            for name in features
        )
        result.append(ResearchDay(day, features, bars))
    return tuple(result)


def test_phase0_is_exact_frozen_target_replay():
    d = days()
    for h in pack():
        for kind in ("candidate", "lowvol", "hash"):
            new, _ = calendar_targets(d, h, kind, "phase_0")
            old, _ = incremental_targets(d, h, kind)
            assert new == old
            assert execute(d, new, 2) == execute(d, old, 2)


@pytest.mark.parametrize("phase", PHASES)
def test_phase_uses_previous_day_and_exact_fixed_cadence(phase):
    targets, _ = calendar_targets(days(), pack()[0], "candidate", f"phase_{phase}")
    assert [i for i, t in enumerate(targets) if t.rebalance] == list(range(phase + 1, 60, 20))
    assert all(not t.weights for t in targets[: phase + 1])
    assert all(t.decided_at[:10] < t.trade_date for t in targets if t.rebalance)


def test_future_features_cannot_change_earlier_targets():
    d = days()
    changed = d[:30] + tuple(replace(t, features={}) for t in d[30:])
    for calendar in CALENDARS:
        a, _ = calendar_targets(d, pack()[0], "candidate", calendar)
        b, _ = calendar_targets(changed, pack()[0], "candidate", calendar)
        assert a[:31] == b[:31]


def test_staggered_ramp_cash_and_netted_target_not_average_nav():
    d = days()
    t, _ = calendar_targets(d, pack()[0], "candidate", "staggered_four")
    for offset, exposure in ((1, 0.25), (6, 0.5), (11, 0.75), (16, 1)):
        assert sum(t[offset].weights.values()) == pytest.approx(exposure)
        assert max(t[offset].weights.values()) <= 0.025 + 1e-10
    report = execute(d, t, 2)
    # One account, one CNY3m endowment; no external flows or NAV averaging.
    assert report.metrics.initial_nav == 3_000_000
    assert len(report.periods) == len(d)
    assert report.periods[1].cash > 2_000_000
    assert report.periods[1].total_cost > 0


def test_annual_calendar_changes_targets_not_capital():
    d = days()
    t, _ = calendar_targets(d, pack()[0], "candidate", "annual_calendar")
    first_new_year = next(i for i, day in enumerate(d) if day.date.startswith("2024"))
    assert not t[first_new_year].rebalance
    assert t[first_new_year + 1].rebalance
    r = execute(d, t, 2)
    assert r.periods[first_new_year].marks
    assert r.periods[first_new_year].end_nav != 3_000_000
    summary = account_summary(r)
    assert (1 + summary["years"]["2023"]) * (1 + summary["years"]["2024"]) - 1 == pytest.approx(
        r.metrics.net_total_return
    )


@pytest.mark.parametrize("name", ["phase_1", "best_phase", "phase_20"])
def test_unknown_calendars_refused(name):
    with pytest.raises(ValueError, match="unregistered"):
        calendar_targets(days(), pack()[0], "candidate", name)


def test_misaligned_sleeves_refused():
    targets, _ = calendar_targets(days(), pack()[0], "candidate", "phase_0")
    with pytest.raises(ValueError, match="aligned"):
        combine_sleeves([targets] * 3)
    with pytest.raises(ValueError, match="dates differ"):
        combine_sleeves(
            [targets] * 3 + [tuple(replace(t, trade_date="2030-01-01") for t in targets)]
        )


def test_no_best_phase_or_statistical_promotion():
    r = account_summary(
        execute(days(), calendar_targets(days(), pack()[0], "candidate", "phase_0")[0], 2)
    )
    r["audit"] = {"pass": True}
    a = {calendar: {kind: r for kind in ("candidate", "lowvol", "hash")} for calendar in CALENDARS}
    verdict = assess_calendars(a)
    assert not verdict["historical_robust_lead"]
    assert not verdict["validated_alpha"]
    assert not verdict["checks"]["lowvol_increment"]
    assert not verdict["checks"]["three_of_four_phases"]
    del a["phase_15"]
    with pytest.raises(ValueError, match="complete"):
        assess_calendars(a)


def test_plans_charge_all72_even_replayed_baseline():
    plans = workflow.plans_for(pack())
    assert len(plans) == len({p["identity"] for p in plans}) == 72
    assert sum(p["item"]["kind"] == "candidate" for p in plans) == 24


def test_predecessor_tamper_rejected(tmp_path):
    (tmp_path / "RESULT.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        workflow.verify_predecessor(
            {"challenge_dir": str(tmp_path), "successor_dir": str(tmp_path)}
        )


def test_all_trials_registered_before_read_abort_and_duplicate_claim(tmp_path, monkeypatch):
    parents = [tmp_path / name for name in ("parent", "challenge", "successor")]
    for folder in parents:
        folder.mkdir()
        for file in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json"):
            (folder / file).write_text("{}")
    frozen = tmp_path / "frozen.json"
    frozen.write_text("{}")
    output = tmp_path / "output"
    monkeypatch.setattr(
        workflow,
        "verify_parent",
        lambda c: (
            parents[0],
            frozen,
            {"snapshot_sha256": "a" * 64},
            {},
            pack(),
            tmp_path / "inputs",
        ),
    )
    monkeypatch.setattr(workflow, "verify_predecessor", lambda c: (*parents[1:], {}))
    monkeypatch.setattr(workflow, "CLAIM_ROOT", tmp_path / "claims")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_dir": str(output), "protected_paths": []}))

    def fail(folder):
        assert (
            len(json.loads((output / "first_read_reservations.json").read_text())["trials"]) == 72
        )
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("select count(*) from trials").fetchone()[0] == 72
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(workflow, "load_frozen_days", fail)
    with pytest.raises(ValueError, match="synthetic source failure"):
        workflow.run(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    config.write_text(
        json.dumps({"output_dir": str(tmp_path / "duplicate"), "protected_paths": []})
    )
    with pytest.raises(FileExistsError):
        workflow.run(config)
    assert not (tmp_path / "duplicate").exists()
