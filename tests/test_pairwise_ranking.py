import copy
import json
from dataclasses import replace
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.pairwise_ranking import (
    BASES,
    KINDS,
    basis_vector,
    design_matrix,
    fit_model,
    name_hash,
    objective,
    optimize,
    pair_names,
    plans,
    prepare,
    ranked_rows,
    score,
    select,
    stages,
    targets_for,
    training_pairs,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def labels(seed=184, kind="interaction", count=50, per_day=12):
    rng = np.random.default_rng(seed)
    calendar = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(730)]
    rows = []
    for i in range(count):
        for j in range(per_day):
            a, b = rng.uniform(-1, 1, (2, 6)).tolist()

            def payoff(x):
                if kind == "interaction":
                    return 0.04 * x[3] * x[4]
                if kind == "style":
                    return 0.04 * x[0]
                if kind == "noise":
                    return float(rng.normal(0, 0.03))
                return 0.0

            rows.append(
                {
                    "date": calendar[5 * i],
                    "entry_date": calendar[5 * i + 1],
                    "label_end": calendar[5 * i + 21],
                    "cell": j // 4,
                    "left": f"L{j}",
                    "right": f"R{j}",
                    "left_x": a,
                    "right_x": b,
                    "left_label": {"return": payoff(a)},
                    "right_label": {"return": payoff(b)},
                    "supported": True,
                }
            )
    return rows, calendar


def days(count=55, names=100):
    result = []
    for i in range(count):
        dt = str(date(2022, 1, 1) + timedelta(days=i))
        features = {
            f"n{j:03}": {
                "volatility_20": 0.01 + j * 0.0001,
                "ret_20": j * 0.0002,
                "liquidity": 1e8 + (j % 17) * 1e6,
                "net_inflow_ratio": 0.001 * (j % 11),
                "auction_return": 0.001 * (j % 7 - 3),
                "concentration": 0.1 + i * 0.0001,
            }
            for j in range(names)
        }
        bars = tuple(
            StatefulBar(dt, n, 10 + i * 0.01, 10 + i * 0.01, 1e8, dt + "T08:00:00+08:00")
            for n in features
        )
        result.append(ResearchDay(dt, features, bars))
    return tuple(result)


def test_exact_budget_and_model_dimensions():
    p = plans()
    assert len(p) == len({r["key"] for r in p}) == 24
    assert sum(r["policy"] in KINDS for r in p) == 16
    assert sum(r["policy"] == "full" for r in p) == 4
    for basis, full, risk in [("linear", 6, 3), ("quadratic", 27, 9)]:
        assert len(basis_vector([0.1] * 6, basis, "full")) == full
        assert len(basis_vector([0.1] * 6, basis, "risk")) == risk


def test_prefix_missing_and_no_future_pool():
    source = days()
    prepared, _ = prepare(source)
    poisoned = list(source)
    poisoned[-1] = replace(poisoned[-1], features={})
    assert prepare(poisoned)[0][:-1] == prepared[:-1]
    assert not prepared[18].features and len(prepared[19].features) == 100
    missing = list(source)
    missing[25] = replace(missing[25], features={})
    rebuilt, _ = prepare(missing)
    assert not rebuilt[44].features and len(rebuilt[45].features) == 100


def test_cells_disjoint_bounded_ranks_and_ties():
    prepared, _ = prepare(days())
    rows = ranked_rows(prepared[-1].features)
    assert len(rows) == 100 and {r["cell"] for r in rows.values()} == set(range(20))
    assert all(-1 <= v <= 1 for r in rows.values() for v in r["x"])
    assert ranked_rows({}) == {}
    assert len(select(rows, {n: 1.0 for n in rows}, ())) == 40
    bad = copy.deepcopy(prepared[-1].features)
    bad["n000"]["ret_20"] = float("nan")
    with pytest.raises(ValueError):
        ranked_rows(bad)


def test_pairs_are_disjoint_fixed_hash_and_pre_outcome():
    rows = {f"n{i:03}": {"cell": 0} for i in range(100)}
    pairs = pair_names(rows)
    expected = sorted(rows, key=lambda n: (name_hash(n), n))[:64]
    assert [n for _, a, b in pairs for n in (a, b)] == expected
    assert len(pairs) == 32
    assert pairs == pair_names(dict(reversed(list(rows.items()))))


def test_pairs_label_window_and_missing_endpoint_mark():
    source, _ = prepare(days(70))
    rows = training_pairs(source, {})
    first = rows[0]
    assert first["entry_date"] == source[21].date and first["label_end"] == source[41].date
    n = first["left"]
    modified = list(source)
    modified[41] = replace(
        modified[41], bars=tuple(b for b in modified[41].bars if b.instrument != n)
    )
    target = training_pairs(modified, {})[0]
    assert target["supported"] and not target["left_label"]["fresh_end"]
    assert target["left_label"]["mark_date"] == source[40].date
    modified[21] = replace(
        modified[21], bars=tuple(b for b in modified[21].bars if b.instrument != n)
    )
    target = training_pairs(modified, {})[0]
    assert not target["supported"] and target["left_label"]["return"] is None


def test_labels_stop_before_final_training_boundary():
    source, _ = prepare(days(750, 4))
    rows = training_pairs(source, {})
    assert all(r["label_end"] < "2024-01-01" for r in rows)
    changed = [replace(d, bars=()) if d.date >= "2024-01-01" else d for d in source]
    assert training_pairs(changed, {}) == rows


def test_date_weights_not_pair_count_weights():
    rows, _ = labels(count=2, per_day=4)
    rows = rows[:4] + rows[4:] + copy.deepcopy(rows[4:]) * 7
    x, y, w = design_matrix(rows, "linear", "full")
    assert w[:4].sum() == pytest.approx(0.5)
    assert w[4:].sum() == pytest.approx(0.5)
    beta, _ = optimize(x, y, w)
    base = design_matrix(rows[:8], "linear", "full")
    assert beta == pytest.approx(optimize(*base)[0], abs=1e-10)


@pytest.mark.parametrize("regression", [False, True])
def test_gradient_and_hessian_finite_difference(regression):
    rows, _ = labels(count=3)
    x, y, w = design_matrix(rows, "quadratic", "regression" if regression else "full")
    beta = np.linspace(-0.1, 0.1, x.shape[1])
    _, grad, hess = objective(beta, x, y, w, regression)
    for i in range(len(beta)):
        delta = np.eye(len(beta))[i] * 1e-5
        left = objective(beta - delta, x, y, w, regression)
        right = objective(beta + delta, x, y, w, regression)
        assert grad[i] == pytest.approx((right[0] - left[0]) / 2e-5, abs=1e-8)
        assert hess[:, i] == pytest.approx((right[1] - left[1]) / 2e-5, abs=1e-8)


def test_quadratic_is_difference_of_stock_bases_not_basis_of_difference():
    rows, _ = labels(count=1, per_day=1)
    x, _, _ = design_matrix(rows, "quadratic", "full")
    a, b = rows[0]["left_x"], rows[0]["right_x"]
    assert x[0, 6] == pytest.approx(a[0] ** 2 - b[0] ** 2)
    swapped = copy.deepcopy(rows)
    swapped[0]["left_x"], swapped[0]["right_x"] = b, a
    assert design_matrix(swapped, "quadratic", "full")[0] == pytest.approx(-x)


def test_planted_interaction_heldout_recovery_and_shuffled_control():
    rows, calendar = labels()
    full = fit_model(rows, calendar, 2023, "quadratic", "full")
    shuffled = fit_model(rows, calendar, 2023, "quadratic", "shuffle")
    linear = fit_model(rows, calendar, 2023, "linear", "full")
    check, _ = labels(5184)

    def accuracy(model):
        return sum(
            (score(model, r["left_x"]) > score(model, r["right_x"]))
            == (r["left_label"]["return"] > r["right_label"]["return"])
            for r in check
        ) / len(check)

    assert accuracy(full) > 0.9
    assert accuracy(linear) < 0.65
    assert accuracy(shuffled) < 0.65


def test_pure_style_has_risk_control_explanation():
    rows, calendar = labels(kind="style")
    a = fit_model(rows, calendar, 2023, "linear", "full")
    b = fit_model(rows, calendar, 2023, "linear", "risk")
    check, _ = labels(5184, kind="style")
    for model in (a, b):
        accuracy = sum(
            (score(model, r["left_x"]) > score(model, r["right_x"]))
            == (r["left_label"]["return"] > r["right_label"]["return"])
            for r in check
        ) / len(check)
        assert accuracy > 0.95


def test_noise_does_not_create_heldout_ranking_power():
    rows, calendar = labels(kind="noise")
    model = fit_model(rows, calendar, 2023, "quadratic", "full")
    check, _ = labels(5184, kind="noise")
    accuracy = sum(
        (score(model, r["left_x"]) > score(model, r["right_x"]))
        == (r["left_label"]["return"] > r["right_label"]["return"])
        for r in check
    ) / len(check)
    assert 0.4 < accuracy < 0.6


def test_tie_targets_have_zero_model():
    rows, calendar = labels(kind="tie")
    model = fit_model(rows, calendar, 2023, "quadratic", "full")
    assert model["weights"] == [0.0] * 27


def test_training_prefix_maturity_and_actual_dates():
    rows, calendar = labels()
    model = fit_model(rows, calendar, 2023, "linear", "full")
    future = copy.deepcopy(rows[0])
    future.update(date="2023-01-01", entry_date="2023-01-02", label_end="2023-02-01")
    future["left_x"] = [1e100] * 6
    assert fit_model(rows + [future], calendar, 2023, "linear", "full") == model
    assert model["maximum_label_end"] <= model["fit_cutoff"]
    assert model["training_signal_dates"] == 50
    with pytest.raises(ValueError):
        fit_model(rows[:12], calendar, 2023, "linear", "full")
    with pytest.raises(ValueError):
        fit_model(rows + [rows[-1]], calendar, 2023, "linear", "full")


def test_shuffle_is_date_cell_local_and_label_order_only():
    rows, _ = labels(count=3)
    x, y, w = design_matrix(rows, "linear", "full")
    sx, sy, sw = design_matrix(rows, "linear", "shuffle")
    assert x == pytest.approx(sx) and w == pytest.approx(sw)
    assert not np.array_equal(y, sy)
    changed = copy.deepcopy(rows)
    for r in changed[12:]:
        r["left_label"]["return"] = 100
    assert design_matrix(changed, "linear", "shuffle")[1][:12] == pytest.approx(sy[:12])


def test_top3_buffer_and_cell_shortfall_do_not_rescale():
    rows = {f"n{i}": {"cell": 0} for i in range(4)}
    values = {"n0": 4.0, "n1": 3.0, "n2": 2.0, "n3": 1.0}
    assert select(rows, values, ("n2", "n3")) == ("n0", "n2")
    assert select({"n0": {"cell": 0}}, {"n0": 1.0}, ()) == ("n0",)
    with pytest.raises(ValueError):
        select(rows, {}, ())


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 2.0])
def test_bad_rank_value_rejected(bad):
    with pytest.raises(ValueError):
        basis_vector([bad] * 6, "linear", "full")


def registry_trial(tmp_path, fitted):
    reg = ExperimentRegistry(tmp_path / "registry.sqlite3")
    sid = reg.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = reg.create_experiment(ExperimentSpec("synthetic", "test", sid, "code"))
    tid, _ = reg.create_trial(
        TrialSpec(
            eid,
            "test",
            "f",
            "{}",
            184,
            "2022-01-01",
            "2023-12-31",
            "2023-01-01",
            "2024-12-31",
            "unused",
            "unused",
            fit_stages=stages() if fitted else (),
        )
    )
    return reg, tid


def test_native_fit_required_and_predictions_bind_bytes(tmp_path):
    rows, calendar = labels()
    reg, tid = registry_trial(tmp_path, True)
    models, paths = {}, {}
    for year in (2023, 2024):
        model = fit_model(rows, calendar, year, "linear", "full")
        path = tmp_path / f"{year}.json"
        path.write_text(json.dumps(model), encoding="utf-8")
        reg.record_model_fit(tid, str(year), model=model, artifact_path=path)
        models[year], paths[year] = model, path
    source, _ = prepare(days(70))
    window = tuple(
        replace(d, date=str(date(2023, 1, 1) + timedelta(days=i)))
        for i, d in enumerate(source[-30:])
    )
    targets, details = targets_for(reg, tid, window, "full", {}, models, paths)
    assert len(targets) == 30 and details
    assert all(sum(t.weights.values()) <= 1 + 1e-12 for t in targets)
    assert all(t.decided_at < t.trade_date + "T09:30:00+08:00" for t in targets)
    models[2023]["weights"][0] += 0.1
    with pytest.raises(ValueError):
        targets_for(reg, tid, window, "full", {}, models, paths)


def test_controls_explicit_no_fit_and_prefix_targets(tmp_path):
    reg, tid = registry_trial(tmp_path, False)
    prepared, _ = prepare(days(85))
    target, _ = targets_for(reg, tid, prepared, "hash", {})
    prefix, _ = targets_for(reg, tid, prepared[:-10], "hash", {})
    assert target[:-10] == prefix
    assert all(len(t.weights) <= 160 for t in target)


def test_all_registered_objectives_converge():
    rows, calendar = labels()
    for basis in BASES:
        for kind in KINDS:
            m = fit_model(rows, calendar, 2023, basis, kind)
            assert m["optimizer"]["gradient_max"] <= 1e-9
            trace = m["optimizer"]["loss_trace"]
            assert all(b <= a + 1e-14 for a, b in pairwise(trace))
