import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.residual_mechanisms import (
    FIELDS,
    HURDLE,
    MECHANISMS,
    ResidualFit,
    fit_year,
    plans,
    predict,
    ranked_rows,
    select,
    targets_for,
)


def synthetic_fit(kind):
    rng = random.Random(184)
    fit = ResidualFit()
    heldout = []
    for i in range(4000):
        x = [1.0] + [rng.uniform(-1, 1) for _ in range(3)]
        independent = rng.uniform(-1, 1)
        z = 0.4 * x[1] + independent
        residual = 0.2 * independent if kind == "planted" else 0.0
        # Pure-style null is exact, plus a separately fixed stochastic null.
        noise = rng.gauss(0, 0.01) if kind == "noise" else 0
        y = 0.1 - 0.3 * x[1] + 0.2 * x[2] + residual + noise
        if i < 2000:
            fit.add(x, z, y)
        else:
            heldout.append((x, z, independent))
    return fit.finish(), heldout


def test_planted_increment_survives_style_removal_and_cost_hurdle():
    model, rows = synthetic_fit("planted")
    assert 0.18 < model["slope"] < 0.21
    scores = [
        (predict({"x": x, "z": {MECHANISMS[0]: z}}, model, MECHANISMS[0]), signal)
        for x, z, signal in rows
    ]
    scores.sort()
    assert sum(s for _, s in scores[-100:]) / 100 > 0.8
    assert scores[-100][0] - scores[100][0] > HURDLE


@pytest.mark.parametrize("kind", ["style", "noise"])
def test_style_only_and_fixed_noise_null_do_not_create_large_edge(kind):
    model, rows = synthetic_fit(kind)
    values = [predict({"x": x, "z": {MECHANISMS[0]: z}}, model, MECHANISMS[0]) for x, z, _ in rows]
    assert max(values) - min(values) < HURDLE
    # A fixed synthetic seed is an engineering check, not calibrated false-positive probability.


def fixture_days(n=320):
    result = []
    for i in range(n):
        dt = (date(2022, 3, 1) + timedelta(days=i)).isoformat()
        features = {
            f"S{j:03d}": {f: ((j * (k + 1) + i) % 97) + 1.0 for k, f in enumerate(FIELDS)}
            for j in range(100)
        }
        bars = tuple(
            StatefulBar(dt, n, 10 + i * 0.01, 10 + i * 0.01, 1e7, f"{dt}T08:00:00+08:00")
            for n in features
        )
        result.append(ResearchDay(dt, features, bars))
    return tuple(result)


def test_future_mutation_cannot_change_training_or_earlier_targets():
    days = fixture_days(400)
    model = fit_year(days, 2023)
    mutated = tuple(replace(d, features={}, bars=()) if d.date >= "2023-01-01" else d for d in days)
    assert fit_year(mutated, 2023) == model
    assert model["maximum_label_end"] <= model["fit_cutoff"] < "2023-01-01"
    window = tuple(d for d in days if d.date >= "2023-01-01")
    a, _ = targets_for(window, {2023: model}, MECHANISMS[0])
    b, _ = targets_for(
        window[:30] + tuple(replace(d, features={}) for d in window[30:]),
        {2023: model},
        MECHANISMS[0],
    )
    assert a[:31] == b[:31]
    assert all(t.decided_at[:10] < t.trade_date for t in a if t.rebalance)


def test_missing_exit_is_not_silently_dropped():
    d = fixture_days()
    changed = list(d)
    changed[21] = replace(d[21], bars=d[21].bars[1:])
    fit = fit_year(tuple(changed), 2023)
    assert fit["missing_exit_imputed_loss"] == 1
    # This same session is also an entry for another sampled label. Only that
    # missing ENTRY is excluded; the missing EXIT stays as the conservative loss.
    assert fit["missing_entry_excluded"] == 1
    assert (
        fit["models"][MECHANISMS[0]]["samples"] + fit["missing_entry_excluded"]
        == fit_year(d, 2023)["models"][MECHANISMS[0]]["samples"]
    )


def test_actual_training_sessions_exclude_dates_with_no_accepted_samples():
    days = fixture_days()
    changed = (replace(days[0], features={}), *days[1:])
    original, model = fit_year(days, 2023), fit_year(changed, 2023)
    assert days[0].date not in model["training_signal_sessions"]
    assert model["training_signal_dates"] == len(model["training_signal_sessions"])
    assert model["training_signal_dates"] == original["training_signal_dates"] - 1
    assert (
        model["models"][MECHANISMS[0]]["samples"]
        == original["models"][MECHANISMS[0]]["samples"] - 100
    )


def test_immature_model_refused():
    d = fixture_days()
    model = fit_year(d, 2023)
    model["fit_cutoff"] = "2024-01-01"
    with pytest.raises(ValueError, match="strictly before"):
        targets_for(d[:40], {2022: model}, MECHANISMS[0])


def test_common_coverage_and_cell_cash_not_future_fill():
    d = fixture_days()[0]
    features = dict(d.features)
    features["missing"] = {"ret_20": 1}
    features["nan"] = {f: float("nan") for f in FIELDS}
    rows = ranked_rows(features)
    assert "missing" not in rows and "nan" not in rows
    chosen, _ = select(rows, (), "risk_hash")
    assert len(chosen) <= 40
    assert all(
        sum(rows[n]["cell"] == c for n in chosen) <= 2 for c in {r["cell"] for r in rows.values()}
    )
    assert select({}, (), "risk_hash") == ((), 0)


def test_hurdle_prevents_null_churn_and_detects_large_edge():
    rows = {
        f"S{i}": {"x": [1, 0, 0, 0], "z": {MECHANISMS[0]: i}, "cell": (0, 0), "vol": 0.1}
        for i in range(20)
    }
    base, _ = select(rows, (), "risk_hash")
    zero = {"slope": 0.0, "nuisance_z": [0] * 4}
    assert select(rows, base, MECHANISMS[0], zero) == (base, 0)
    picked, _ = select(rows, base, MECHANISMS[0], {**zero, "slope": 0.1})
    assert set(picked) == {"S18", "S19"}


def test_all_model_and_account_attempts_counted():
    assert len(plans()) == 21
    assert sum(p["kind"] == "fit" for p in plans()) == 6
    assert sum(p["kind"] == "account" for p in plans()) == 15


def test_nonfinite_and_unknown_inputs_rejected():
    with pytest.raises(ValueError, match="finite"):
        ResidualFit().add([1, 2, 3, 4], float("nan"), 1)
    with pytest.raises(ValueError, match="unregistered"):
        select({}, (), "best_phase")
    with pytest.raises(ValueError, match="insufficient"):
        fit_year((), 2023)
