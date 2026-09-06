from dataclasses import replace

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.incremental_alpha import (
    CRITERIA,
    IncrementalHypothesis,
    audit_account,
    batches,
    execute,
    incremental_targets,
    matched_ranks,
    scores_from_ranks,
    suspected_lead,
)
from stephen_quant.discovery.reliable_research import ResearchDay, temporal_selection
from stephen_quant.workflows.v117_incremental_epoch import inventory


def features(n=80):
    return {
        f"S{i:03d}": {"volatility_20": i + 1, "ret_20": n - i, "net_inflow_ratio": i / n}
        for i in range(n)
    }


def days():
    return tuple(
        ResearchDay(
            f"2023-01-{i:02d}",
            features(),
            tuple(
                StatefulBar(
                    f"2023-01-{i:02d}",
                    name,
                    10.0,
                    10.0 + (i - 1) * 0.05,
                    1e7,
                    f"2023-01-{i:02d}T08:00:00+08:00",
                )
                for name in features()
            ),
        )
        for i in (2, 3, 4)
    )


def example_years():
    return {
        y: {
            "2": {
                "absolute_return": 0.1,
                "benchmark_return": 0.05,
                "hash_control_return": 0.03,
                "max_drawdown": -0.1,
                "daily_returns": [0.001, -0.0001] * 100,
                "audit": {"pass": True},
            }
        }
        for y in ("2023", "2024")
    }


def test_budget_and_identities():
    packs = batches()
    assert [len(p) for p in packs] == [16, 16]
    items = [item for p in packs for item in inventory(p)]
    assert len(items) == 64
    assert len({i["identity"] for i in items}) == 64
    assert len(items) * 3 == 192  # Controls, zero-cost and double-cost attempts count too.
    assert batches() == packs


@pytest.mark.parametrize(
    "kwargs", [{"field": "future"}, {"direction": 0}, {"method": "eval"}, {"horizon": 1}]
)
def test_unknown_proposals_rejected(kwargs):
    config = {"field": "ret_20", "direction": 1, "method": "blend", "horizon": 20}
    config.update(kwargs)
    with pytest.raises(ValueError):
        IncrementalHypothesis(**config)


def test_missing_unused_field_does_not_remove_stock():
    f = features()
    f["S000"]["unrelated"] = float("nan")
    assert len(matched_ranks(f, "ret_20")["ret_20"]) == 80
    del f["S000"]["ret_20"]
    assert len(matched_ranks(f, "ret_20")["ret_20"]) == 79


def test_controls_share_coverage_but_not_signal_direction():
    r = matched_ranks(features(), "ret_20")
    positive = IncrementalHypothesis("ret_20", 1, "conditional", 60)
    negative = replace(positive, direction=-1)
    assert set(scores_from_ranks(r, positive)) == set(scores_from_ranks(r, negative))
    assert max(r["volatility_20"][n] for n in scores_from_ranks(r, negative)) <= 0.3
    for kind in ("hash", "lowvol"):
        assert scores_from_ranks(r, positive, kind) == scores_from_ranks(r, negative, kind)
        assert len(scores_from_ranks(r, positive, kind)) == 80


def test_future_open_not_used_for_target_selection():
    d = days()
    h = IncrementalHypothesis("ret_20", 1, "blend", 20)
    a, _ = incremental_targets(d, h)
    altered = (d[0], replace(d[1], bars=()), d[2])
    b, _ = incremental_targets(altered, h)
    assert a == b
    assert not a[0].weights and len(a[1].weights) == 40
    assert a[1].decided_at == "2023-01-02T23:59:59+08:00"


def test_controls_have_same_position_budget():
    h = IncrementalHypothesis("ret_20", 1, "blend", 20)
    for kind in ("candidate", "lowvol", "hash"):
        t, _ = incremental_targets(days(), h, kind)
        assert len(t[1].weights) == 40
        assert sum(t[1].weights.values()) == pytest.approx(1)


def test_costs_and_cash_are_reconciled():
    h = IncrementalHypothesis("ret_20", 1, "blend", 20)
    t, _ = incremental_targets(days(), h)
    reports = [execute(days(), t, c) for c in (0, 1, 2)]
    assert all(audit_account(r)["pass"] for r in reports)
    assert reports[0].metrics.total_cost == 0
    assert (
        reports[0].metrics.final_nav > reports[1].metrics.final_nav > reports[2].metrics.final_nav
    )


def test_economic_lead_never_certifies_alpha():
    result = suspected_lead(example_years())
    assert result["suspected_lead"]
    assert result["validated_alpha"] is False
    assert CRITERIA["pooled_sharpe_min"] == 0.7


@pytest.mark.parametrize(
    "change,value",
    [
        ("absolute_return", -0.01),
        ("max_drawdown", -0.26),
        ("benchmark_return", 0.2),
        ("hash_control_return", 0.8),
    ],
)
def test_failures_cannot_be_reported_as_leads(change, value):
    years = example_years()
    years["2023"]["2"][change] = value
    assert not suspected_lead(years)["suspected_lead"]


def test_account_failure_blocks_lead():
    years = example_years()
    years["2024"]["2"]["audit"]["pass"] = False
    assert not suspected_lead(years)["suspected_lead"]


def test_restricted_year_not_accepted():
    years = example_years()
    years["2025"] = years.pop("2024")
    with pytest.raises(ValueError):
        suspected_lead(years)


def test_nonpositive_purge_horizon_rejected():
    with pytest.raises(ValueError, match="holding period"):
        temporal_selection([], {}, 3000, holding_period_sessions=0)


def test_trials_registered_before_source_read_and_aborts_retained(tmp_path, monkeypatch):
    import json
    import sqlite3

    from stephen_quant.workflows import v117_incremental_epoch as workflow

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "manifest.json").write_text(json.dumps({"snapshot_sha256": "a" * 64}))
    frozen = tmp_path / "frozen.json"
    frozen.write_text("{}")
    output = tmp_path / "operation"
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "output_dir": str(output),
                "frozen_inputs_dir": str(inputs),
                "legacy_operation_dirs": [],
                "protected_paths": [str(frozen)],
            }
        )
    )
    monkeypatch.setattr(workflow, "historical_debt", lambda _: (2866, []))

    def fail_read(_):
        with sqlite3.connect(output / "registry.sqlite3") as conn:
            assert conn.execute("SELECT count(*) FROM trials").fetchone()[0] == 192
        assert (output / "first_read_reservations.json").exists()
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(workflow, "load_frozen_days", fail_read)
    with pytest.raises(ValueError, match="synthetic source failure"):
        workflow.run_incremental_epoch(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    with pytest.raises(FileExistsError):
        workflow.run_incremental_epoch(config)


@pytest.mark.parametrize("seed", [182001, 182002, 182003, 182004])
def test_planted_increment_recovers_correct_direction(seed):
    from stephen_quant.discovery.reliability_calibration import synthetic_days

    sample, field, direction = synthetic_days(seed, True, size=160)
    sample = tuple(
        replace(d, features={n: {**f, "volatility_20": 0.02} for n, f in d.features.items()})
        for d in sample
    )
    h = IncrementalHypothesis(field, direction, "blend", 20)
    good, _ = incremental_targets(sample, h)
    bad, _ = incremental_targets(sample, replace(h, direction=-direction))
    control, _ = incremental_targets(sample, h, "lowvol")
    a, b, c = (execute(sample, t, 2) for t in (good, bad, control))
    assert a.metrics.net_total_return > c.metrics.net_total_return > b.metrics.net_total_return
    assert all(audit_account(r)["pass"] for r in (a, b, c))


def test_long_horizon_has_at_least_as_much_purging():
    import math
    from datetime import date, timedelta

    dates = [(date(2023, 1, 1) + timedelta(days=i)).isoformat() for i in range(484)]
    matrix = {
        "one": [0.001 * math.sin(i / 11) for i in range(484)],
        "two": [0.002 * math.cos(i / 13) for i in range(484)],
    }
    short = temporal_selection(dates, matrix, 3058, holding_period_sessions=20)
    long = temporal_selection(dates, matrix, 3058, holding_period_sessions=60)
    assert sum(f["purged_n"] for f in long["folds"]) > sum(f["purged_n"] for f in short["folds"])
