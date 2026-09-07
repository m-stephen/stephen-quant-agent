from dataclasses import replace

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.incremental_alpha import IncrementalHypothesis, audit_account, execute
from stephen_quant.discovery.lead_challenge import (
    CHALLENGES,
    Challenge,
    challenge_execute,
    delayed_targets,
    lowvol_attribution,
    next_action,
    summarize_account,
    tail_sensitivity,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.workflows.v118_lead_challenge import planned_trials, verify_parent


def sample_days():
    features = {f"S{i}": {"volatility_20": i + 1, "concentration": 80 - i} for i in range(80)}
    return tuple(
        ResearchDay(
            f"2023-01-{d:02d}",
            features,
            tuple(
                StatefulBar(
                    f"2023-01-{d:02d}", n, 10, 10, 100_000, f"2023-01-{d:02d}T08:00:00+08:00"
                )
                for n in features
            ),
        )
        for d in (2, 3, 4, 5)
    )


def hypothesis():
    return IncrementalHypothesis("concentration", 1, "blend", 20)


def test_reservations_include_controls_and_continuous_exclude_exact_replay():
    pack = (hypothesis(), IncrementalHypothesis("late_30_return", -1, "blend", 20))
    plans = planned_trials(pack)
    assert len(plans) == len({p["identity"] for p in plans}) == 30
    assert sum(p["challenge"]["continuous"] for p in plans) == 6
    assert not any(p["challenge"]["name"] == "baseline_82" for p in plans)


def test_baseline_identical_to_frozen_execution():
    report, targets, _ = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[0])
    assert report == execute(sample_days(), targets, 2)
    assert audit_account(report)["pass"]


def test_extra_cost_is_real_account_rerun_not_subtraction():
    reports = [
        challenge_execute(sample_days(), hypothesis(), "candidate", c)[0] for c in CHALLENGES[:3]
    ]
    assert (
        reports[0].metrics.final_nav > reports[1].metrics.final_nav > reports[2].metrics.final_nav
    )
    assert reports[0].periods[1].marks != reports[1].periods[1].marks
    assert all(audit_account(r)["pass"] for r in reports)


def test_capacity_reduction_applied_to_orders():
    base = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[0])[0]
    tight = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[3])[0]
    assert tight.periods[1].traded_notional_cny < base.periods[1].traded_notional_cny
    assert all(abs(o.executed_notional) <= 25_000 for o in tight.periods[1].orders)


def test_delay_preserves_old_information_and_schedule():
    base, targets, _ = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[0])
    delayed, later, _ = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[4])
    assert not delayed.periods[1].marks and base.periods[1].marks
    assert later[2].weights == targets[1].weights
    assert later[2].decided_at == targets[1].decided_at
    altered = tuple(replace(d, bars=()) for d in sample_days())
    # Targets' date shifting does not inspect execution-day prices or future features.
    assert delayed_targets(targets, 1) == later
    assert len(altered) == len(later)


@pytest.mark.parametrize("lag", [-1, 2, True])
def test_unregistered_delay_rejected(lag):
    with pytest.raises(ValueError):
        delayed_targets((), lag)


def test_unregistered_challenge_rejected():
    with pytest.raises(ValueError):
        challenge_execute(sample_days(), hypothesis(), "candidate", Challenge("favorable", -30))


def test_ols_recovers_known_beta_and_intercept():
    x = [0.01, -0.01, 0.005, -0.005] * 100
    result = lowvol_attribution([0.0002 + 0.7 * v for v in x], x)
    assert result["beta_to_lowvol"] == pytest.approx(0.7)
    assert result["annualized_intercept"] == pytest.approx(0.0504)
    assert result["r_squared"] == pytest.approx(1)
    assert result["causal_alpha"] is False


def test_identical_control_has_no_alpha():
    x = [0.01, -0.01, 0.005, -0.005] * 30
    result = lowvol_attribution(x, x)
    assert result["annualized_intercept"] == pytest.approx(0)
    assert result["beta_to_lowvol"] == pytest.approx(1)


def test_constant_control_not_identifiable():
    assert lowvol_attribution([0.01] * 4, [0.0] * 4)["status"] == "NOT_IDENTIFIABLE"


@pytest.mark.parametrize(
    "a,b",
    [
        ([1, 2], [1, 2]),
        ([0, 0, 0], [0, 0]),
        ([0, float("nan"), 0], [0, 0, 0]),
        ([-1, 0, 0], [0, 0, 0]),
    ],
)
def test_invalid_returns_rejected(a, b):
    for fn in (lowvol_attribution, tail_sensitivity):
        with pytest.raises(ValueError):
            fn(a, b)


def test_tail_counterfactual_not_deleted_days():
    result = tail_sensitivity([0.1, -0.01, 0.02, 0.03], [0, 0, 0, 0], top=1)
    assert result["top_positive_active_days"] == [0]
    assert result["observations_retained"] == 4
    assert result["net_return_if_top_active_days_equal_control"] == pytest.approx(
        0.99 * 1.02 * 1.03 - 1
    )
    assert result["status"].startswith("NONTRADABLE")


def test_history_cannot_produce_pass_or_stop_research_as_success():
    assert next_action(["lead"]) == "FROZEN_BROKERAGE_AND_STYLE_CHALLENGE"
    assert next_action([]) == "PREREGISTER_NEXT_BOUNDED_MECHANISM_EPOCH"
    assert next_action(["lead"], engineering_pass=False) == "REPAIR_ENGINEERING_BEFORE_RESEARCH"


def test_summary_cash_profit_and_costs():
    report = challenge_execute(sample_days(), hypothesis(), "candidate", CHALLENGES[0])[0]
    result = summarize_account(report)
    assert result["profit_cny"] == pytest.approx(-report.metrics.total_cost)
    assert result["fixed_fill_extra_one_way_bps_to_zero_profit"] < 0


def test_tampered_parent_refused_before_source_read(tmp_path):
    import json

    (tmp_path / "RESULT.json").write_text("{}")
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps({"source_result_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="parent result"):
        verify_parent({"parent_operation_dir": str(tmp_path), "frozen_leads_file": str(path)})


def test_source_failure_retains_all_reservations_before_price_read(tmp_path, monkeypatch):
    import json
    import sqlite3

    from stephen_quant.workflows import v118_lead_challenge as workflow

    parent = tmp_path / "parent"
    parent.mkdir()
    for name in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json"):
        (parent / name).write_text("{}")
    frozen = tmp_path / "frozen.json"
    frozen.write_text("{}")
    inputs = tmp_path / "inputs"
    output = tmp_path / "output"
    pack = (hypothesis(), IncrementalHypothesis("late_30_return", -1, "blend", 20))
    monkeypatch.setattr(
        workflow,
        "verify_parent",
        lambda config: (
            parent,
            frozen,
            {"snapshot_sha256": "a" * 64},
            {"raw_global_trial_lower_bound": 3058},
            pack,
            inputs,
        ),
    )

    def fail_at_read(folder):
        reservations = json.loads((output / "first_read_reservations.json").read_text())
        assert len(reservations["trials"]) == 30
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("SELECT count(*) FROM trials").fetchone()[0] == 30
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(workflow, "load_frozen_days", fail_at_read)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_dir": str(output), "protected_paths": []}))
    with pytest.raises(ValueError, match="synthetic source failure"):
        workflow.run_challenge(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    assert not (output / "RESULT.json").exists()
    with pytest.raises(FileExistsError):
        workflow.run_challenge(config)
