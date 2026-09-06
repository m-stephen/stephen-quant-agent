import copy
import json
from dataclasses import asdict, replace
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pytest

from stephen_quant.baseline.stateful import StatefulBar, TargetAllocation
from stephen_quant.discovery.conditional_risk import (
    daily_predictions,
    fit_model,
    market_states,
    overlay_targets,
    plans,
    predict,
    proxy_labels,
    quantize,
    stages,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def days(count=35):
    result = []
    for i in range(count):
        dt = str(date(2022, 1, 1) + timedelta(days=i))
        features = {
            f"n{j:03}": {
                "ret_20": 0.001 * (j - 100),
                "volatility_20": 0.01 + j * 0.00001,
                "liquidity": 1e8,
            }
            for j in range(205)
        }
        bars = tuple(
            StatefulBar(dt, n, 10 + i * 0.1, 10 + i * 0.1, 1e8, dt + "T08:00:00+08:00")
            for n in features
        )
        result.append(ResearchDay(dt, features, bars))
    return tuple(result)


def labels():
    calendar = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(365)]
    rng = np.random.default_rng(184)
    rows = []
    for i in range(0, 355, 5):
        x = rng.normal(size=4).tolist()
        rows.append(
            {
                "date": calendar[i],
                "entry_date": calendar[i + 1],
                "label_end": calendar[i + 6],
                "x": x,
                "return": 0.003 + 0.01 * x[0] - 0.002 * x[1],
                "entries": 200,
                "fresh": 200,
                "supported": True,
            }
        )
    return rows, calendar


def test_frozen_budget_and_no_duplicate_accounts():
    p = plans()
    assert len(p) == len({x["key"] for x in p}) == 44
    assert sum(x["policy"] == "model" for x in p) == 8
    assert sum(x["policy"] in ("original", "unscaled") for x in p) == 8


def test_market_state_prefix_and_disappearance():
    source = days()
    states = market_states(source)
    assert not states[0]["available"] and states[1]["available"]
    assert states[1]["basket"] == [f"n{j:03}" for j in range(200)]
    poisoned = list(source)
    poisoned[-1] = replace(poisoned[-1], features={})
    assert market_states(poisoned)[:-1] == states[:-1]
    assert market_states(poisoned)[-1]["available"] is False
    missing = list(source)
    missing[5] = replace(missing[5], features={})
    assert not market_states(missing)[6]["available"]


def test_proxy_uses_future_only_for_matured_labels_and_fixed_denominator():
    source = list(days())
    states = market_states(source)
    source[6] = replace(source[6], bars=tuple(b for b in source[6].bars if b.instrument != "n000"))
    source[11] = replace(
        source[11], bars=tuple(b for b in source[11].bars if b.instrument != "n001")
    )
    evidence = []
    rows = proxy_labels(source, states, evidence.append)
    first = rows[0]
    assert first["date"] == source[5].date and first["label_end"] == source[11].date
    assert first["entries"] == 199 and first["fresh"] == 198 and first["supported"]
    components = [e for e in evidence if e["signal_date"] == first["date"]]
    assert len(components) == 200
    assert components[0]["return"] == 0 and components[0]["entry_price"] is None
    assert components[1]["mark_date"] == source[10].date
    assert first["return"] == pytest.approx(sum(c["return"] for c in components) / 200)
    assert all(a["label_end"] == b["entry_date"] for a, b in pairwise(rows))


def test_proxy_missing_bars_does_not_select_survivors_or_renormalize():
    source = list(days())
    states = market_states(source)
    source[6] = replace(source[6], bars=source[6].bars[15:])
    first = proxy_labels(source, states)[0]
    assert first["entries"] == 185 and not first["supported"]


def test_training_prefix_maturity_ridge_and_future_poisoning():
    rows, calendar = labels()
    m = fit_model(rows, calendar, 2023)
    assert m["fit_cutoff"] == calendar[-6]
    assert m["maximum_label_end"] <= m["fit_cutoff"]
    future = {
        **rows[0],
        "date": "2023-01-02",
        "entry_date": "2023-01-03",
        "label_end": "2023-01-08",
        "x": [float("nan")] * 4,
        "return": float("nan"),
    }
    assert fit_model(rows + [future], calendar + ["2023-01-02"], 2023) == m
    x = np.asarray([r["x"] for r in rows])
    y = np.asarray([r["return"] for r in rows])
    z = (x - x.mean(axis=0)) / x.std(axis=0)
    expected = np.linalg.inv(z.T @ z / len(x) + np.eye(4)) @ (z.T @ (y - y.mean()) / len(x))
    assert m["beta_return"] == pytest.approx(expected, abs=1e-12)


def test_shuffled_targets_preserve_pairs_and_training_distribution():
    rows, calendar = labels()
    direct, shuffled = (fit_model(rows, calendar, 2023, s) for s in (False, True))
    assert direct["mean_return"] == pytest.approx(shuffled["mean_return"])
    assert direct["mean_second"] == pytest.approx(shuffled["mean_second"])
    assert direct["center"] == shuffled["center"]
    assert direct["beta_return"] != shuffled["beta_return"]
    assert set(shuffled["assigned_label_dates"]) == set(direct["training_signal_sessions"])


@pytest.mark.parametrize("fault", ["short", "duplicate", "overlap", "nan", "year"])
def test_bad_training_is_rejected(fault):
    rows, calendar = labels()
    year = 2023
    if fault == "short":
        rows = rows[:20]
    elif fault == "duplicate":
        rows.append(rows[-1])
    elif fault == "overlap":
        rows[0]["label_end"] = rows[2]["entry_date"]
    elif fault == "nan":
        rows[0]["x"][0] = float("nan")
    else:
        year = 2025
    with pytest.raises(ValueError):
        fit_model(rows, calendar, year)


@pytest.mark.parametrize("x,w", [(-10, 0.25), (0.375, 0.5), (0.8, 0.75), (100, 1)])
def test_exposure_quantization(x, w):
    assert quantize(x) == w


def test_constant_training_columns_and_zero_labels_are_finite():
    rows, calendar = labels()
    for row in rows:
        row.update(x=[0.0] * 4, return_=0.0)
        row["return"] = 0.0
    m = fit_model(rows, calendar, 2023)
    assert m["scale"] == [1.0] * 4
    assert predict(m, [0.0] * 4, "mean_second") == 0.25
    with pytest.raises(ValueError):
        quantize(float("nan"))


def fixture_targets():
    ds = [str(date(2023, 12, 1) + timedelta(days=i)) for i in range(45)]
    base = tuple(
        TargetAllocation(
            d,
            (ds[i - 1] if i else d) + "T08:00:00+08:00",
            {"x": 0.025} if i in (1, 21, 41) else {},
            i in (1, 21, 41),
            ("x",) if i == 27 else (),
        )
        for i, d in enumerate(ds)
    )
    p = {
        d: {
            "signal_date": ds[i - 1],
            "mean": 0.25 if i < 10 else 1.0,
            "mean_second": 0.5,
            "risk_only": 0.75,
            "training_mean": {"mean": 0.6},
        }
        for i, d in enumerate(ds)
        if i
    }
    return base, p


def test_exact_global_lag_and_annual_continuity_preserve_base():
    base, p = fixture_targets()
    before = copy.deepcopy(base)
    targets, e = overlay_targets(base, p, "mean", "lag20")
    assert e[1]["allocation"] == 0.6 and e[21]["allocation"] == 0.25
    assert e[31]["allocation"] == 1.0
    assert [i for i, x in enumerate(e) if x["refresh"]] == list(range(1, 45, 5))
    assert targets[27].forced_exits == ("x",) and "x" not in targets[31].weights
    assert targets[41].weights == {"x": 0.025}
    assert base == before


def test_native_supervised_lineage_precedes_predictions(tmp_path):
    rows, calendar = labels()
    models = {}
    paths = {}
    for y in (2023, 2024):
        models[y] = fit_model(rows, calendar, y)
        paths[y] = tmp_path / f"{y}.json"
        paths[y].write_text(json.dumps(models[y]))
    reg = ExperimentRegistry(tmp_path / "r.db")
    sid = reg.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = reg.create_experiment(ExperimentSpec("overlay", "synthetic", sid, "runtime", "{}"))
    tid = reg.create_trial(
        TrialSpec(
            eid,
            "one",
            "a",
            "{}",
            184,
            "2022-01-01",
            "2023-12-31",
            "2023-01-01",
            "2024-12-31",
            "unused",
            "unused",
            fit_stages=stages(),
        )
    )
    if isinstance(tid, tuple):
        tid = tid[0]
    prediction_dates = ["2023-01-02", "2023-01-03", "2024-01-02"]
    states = [{"date": d, "x": [0.0] * 4, "available": True} for d in prediction_dates]
    with pytest.raises(ValueError):
        daily_predictions(reg, tid, states, prediction_dates, models, paths)
    for y, model in models.items():
        reg.record_model_fit(tid, str(y), model=model, artifact_path=paths[y])
    out = daily_predictions(reg, tid, states, prediction_dates, models, paths)
    assert len(out) == 2
    paths[2023].write_text(json.dumps({**models[2023], "beta_return": [9] * 4}))
    with pytest.raises(ValueError):
        daily_predictions(reg, tid, states, prediction_dates, models, paths)


def test_overlay_rejects_future_clock():
    base, p = fixture_targets()
    p[base[1].trade_date]["signal_date"] = base[1].trade_date
    with pytest.raises(ValueError):
        overlay_targets(base, p, "mean", "model")


def test_original_target_serialization_is_not_mutated():
    base, p = fixture_targets()
    before = json.dumps([asdict(t) for t in base], sort_keys=True)
    overlay_targets(base, p, "mean", "fixed")
    assert json.dumps([asdict(t) for t in base], sort_keys=True) == before
