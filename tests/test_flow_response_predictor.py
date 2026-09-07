import copy
import json
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.flow_response_predictor import (
    INPUTS,
    POLICIES,
    fit_and_bind_predictor,
    fit_predictor,
    guarded_predict,
    pairs_for_year,
    predict,
    ranked_rows,
    stages,
    vector,
)
from stephen_quant.integrity.fit_lineage import UnsupervisedFitStage
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def calendar():
    # Synthetic global sessions, not a representation of the exchange calendar.
    return [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(380)]


def matrix_row(rng, cell=0):
    return {
        "cell": cell,
        "ranks": dict(zip(INPUTS, rng.uniform(-1, 1, len(INPUTS)), strict=True)),
        "vol": 0.02,
    }


def sample_pairs(mode="planted"):
    rng, dates = np.random.default_rng(184), calendar()
    pairs = []
    for i in range(0, 335, 5):
        for j in range(1 + i % 4):
            left, right = matrix_row(rng), matrix_row(rng)

            def outcome(row):
                if mode == "zero":
                    return 0.0
                if mode == "null":
                    return float(rng.normal(0, 0.02))
                return (
                    0.08 * row["ranks"]["flow_surprise"] * row["ranks"]["price_response_residual"]
                )

            pairs.append(
                {
                    "date": dates[i],
                    "entry_date": dates[i + 1],
                    "label_end": dates[i + 21],
                    "cell": 0,
                    "left": f"s{2 * j}",
                    "right": f"s{2 * j + 1}",
                    "left_row": left,
                    "right_row": right,
                    "supported": True,
                    "left_label": {"entry_valid": True, "return": outcome(left)},
                    "right_label": {"entry_valid": True, "return": outcome(right)},
                }
            )
    return pairs, dates


def test_planted_interaction_has_predictive_representation_and_independent_fit():
    pairs, dates = sample_pairs()
    model = fit_predictor(pairs, dates, 2023, "response_interaction")
    standard = fit_predictor(pairs, dates, 2023, "standardized_flow_return")
    risk = fit_predictor(pairs, dates, 2023, "risk")
    rng = np.random.default_rng(185)
    holdout = {str(i): matrix_row(rng) for i in range(500)}
    expected = np.asarray(
        [
            0.08 * r["ranks"]["flow_surprise"] * r["ranks"]["price_response_residual"]
            for r in holdout.values()
        ]
    )
    errors = [
        float(np.mean((np.asarray(list(predict(m, holdout).values())) - expected) ** 2))
        for m in (model, standard, risk)
    ]
    assert errors[0] < 0.25 * min(errors[1:])
    assert not model["validated_alpha"] and model["training_signal_dates"] == 67
    # Independently accumulate normal equations one observation at a time.
    counts = {d: sum(r["date"] == d for r in pairs) for d in {r["date"] for r in pairs}}
    gram, rhs = np.eye(6) * 0.01, np.zeros(6)
    for r in pairs:
        z = np.asarray(vector(r["left_row"], "response_interaction")) - np.asarray(
            vector(r["right_row"], "response_interaction")
        )
        w = 1 / (len(counts) * counts[r["date"]])
        gram += w * np.outer(z, z)
        rhs += w * z * (r["left_label"]["return"] - r["right_label"]["return"])
    assert model["weights"] == pytest.approx(np.linalg.solve(gram, rhs))


@pytest.mark.parametrize("policy", POLICIES)
def test_zero_null_and_frozen_shuffle_are_deterministic(policy):
    pairs, dates = sample_pairs("zero")
    model = fit_predictor(pairs, dates, 2023, policy)
    assert model == fit_predictor(copy.deepcopy(pairs), dates, 2023, policy)
    assert model["weights"] == [0.0] * model["parameter_count"]


def test_random_null_does_not_predict_independent_null():
    pairs, dates = sample_pairs("null")
    model = fit_predictor(pairs, dates, 2023, "response_interaction")
    rng = np.random.default_rng(185)
    rows = {str(i): matrix_row(rng) for i in range(2000)}
    truth = rng.normal(0, 0.02, len(rows))
    predictions = np.asarray(list(predict(model, rows).values()))
    assert abs(float(np.corrcoef(predictions, truth)[0, 1])) < 0.1
    # This fixed synthetic fixture is not a market placebo p-value.


def test_shuffle_changes_only_design_not_training_support_and_sparse_fit_fails():
    pairs, dates = sample_pairs()
    original = fit_predictor(pairs, dates, 2023, "response_interaction")
    shuffled = fit_predictor(pairs, dates, 2023, "shuffle")
    assert original["training_rows_sha256"] == shuffled["training_rows_sha256"]
    assert original["training_signal_sessions"] == shuffled["training_signal_sessions"]
    assert original["training_pairs"] == shuffled["training_pairs"]
    assert original["training_design_sha256"] != shuffled["training_design_sha256"]
    assert predict(original, {}) == {}
    with pytest.raises(ValueError, match="minimum30"):
        fit_predictor(pairs[:20], dates, 2023, "response")


def test_future_values_are_excluded_before_inspection():
    pairs, dates = sample_pairs()
    before = fit_predictor(pairs, dates, 2023, "response")
    poisoned = {
        "date": "2023-01-02",
        "entry_date": "2023-01-03",
        "label_end": "2023-01-25",
        "supported": object(),
        "left_row": object(),
        "left_label": object(),
    }
    assert fit_predictor(pairs + [poisoned], dates, 2023, "response") == before
    immature = copy.deepcopy(pairs[-1])
    immature["label_end"] = "2022-12-31"
    immature["left_label"] = object()
    assert fit_predictor(pairs + [immature], dates, 2023, "response") == before


@pytest.mark.parametrize(
    "kind",
    [
        "horizon",
        "entry",
        "stride",
        "duplicate",
        "same_asset",
        "bad_cell",
        "future_calendar",
        "nonfinite",
        "unavailable_entry",
    ],
)
def test_corrupt_training_rows_rejected(kind):
    pairs, dates = sample_pairs()
    row = pairs[0]
    if kind == "horizon":
        row["label_end"] = dates[20]
    elif kind == "entry":
        row["entry_date"] = row["date"]
    elif kind == "stride":
        row.update(date=dates[1], entry_date=dates[2], label_end=dates[22])
    elif kind == "duplicate":
        pairs.insert(0, copy.deepcopy(row))
    elif kind == "same_asset":
        row["right"] = row["left"]
    elif kind == "bad_cell":
        row["left_row"]["cell"] = 1
    elif kind == "future_calendar":
        dates[-1] = "2026-01-01"
    elif kind == "nonfinite":
        row["left_row"]["ranks"]["flow_ratio"] = float("nan")
    else:
        row["left_label"]["entry_valid"] = False
    with pytest.raises(ValueError):
        fit_predictor(pairs, dates, 2023, "response")


def test_same_support_and_fixed_finite_model_forms():
    rng = np.random.default_rng(184)
    features = {
        f"s{i}": dict(zip(INPUTS, rng.uniform(0, 1, len(INPUTS)), strict=True)) for i in range(300)
    }
    features["s1"].pop("price_response_residual")
    rows = ranked_rows(features)
    assert len(rows) == 299 and "s1" not in rows
    assert ranked_rows({}) == {}
    assert {r["cell"] for r in rows.values()} == set(range(20))
    for policy, width in zip(POLICIES, (5, 6, 3, 5, 5, 4, 6), strict=True):
        assert {n for n in rows if len(vector(rows[n], policy)) == width} == set(rows)
    with pytest.raises(ValueError):
        vector(next(iter(rows.values())), "new-sign")


def test_pair_labels_read_prefix_only_and_keep_missing_endpoint():
    dates = calendar()
    rng = np.random.default_rng(184)
    features, bars = {}, {}
    for d in dates:
        if d >= "2023-01-01":
            features[d] = bars[d] = object()  # Will fail if any future value is accessed.
        else:
            features[d] = {n: matrix_row(rng) for n in ("a", "b")}
            bars[d] = {
                n: StatefulBar(d, n, 10.0, 10.0, 1e6, f"{d}T08:00:00+08:00") for n in ("a", "b")
            }
    bars[dates[21]].pop("a")
    result = pairs_for_year(dates, features, bars, 2023)
    assert result[0]["supported"]
    missing = result[0]["left_label"] if result[0]["left"] == "a" else result[0]["right_label"]
    assert not missing["fresh_end"] and missing["return"] == 0 and missing["mark_date"] == dates[20]
    assert all(r["label_end"] < "2023-01-01" for r in result)


@pytest.fixture
def native(tmp_path):
    registry = ExperimentRegistry(tmp_path / "native.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = registry.create_experiment(ExperimentSpec("response", "synthetic", sid, "synthetic-code"))
    spec = TrialSpec(
        eid,
        "predictor",
        "liquidity-impact",
        json.dumps({"response_policy": "response_interaction"}),
        184,
        "2022-01-01",
        "2022-12-31",
        "2023-01-01",
        "2023-12-31",
        "unused",
        "unused",
        fit_stages=stages()[:1],
    )
    provider, _ = registry.create_trial(
        replace(
            spec,
            model_name="provider",
            fit_stages=(
                UnsupervisedFitStage(
                    "feature", "2022-01-01", "2022-01-02", "2022-01-03", "2022-12-31"
                ),
            ),
        )
    )
    registry.declare_feature_sources(provider, ())
    consumer, _ = registry.create_trial(spec)
    registry.declare_feature_sources(consumer, (provider,))
    source_model = {
        "fit_kind": "unsupervised",
        "year": 2022,
        "fit_cutoff": "2022-01-02",
        "maximum_observation_at": "2022-01-02",
        "training_observation_sessions": ["2022-01-01", "2022-01-02"],
        "training_observation_dates": 2,
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source_model), encoding="utf-8")
    registry.record_model_fit(provider, "feature", model=source_model, artifact_path=path)
    registry.record_trial_result(
        provider,
        json.dumps(
            {
                "feature_provider_ready": True,
                "native_fit_lineage_sha256": registry.fit_lineage(provider)["sha256"],
            }
        ),
    )
    return registry, provider, consumer


def test_native_fit_and_prediction_guards_precede_numeric_access(native, tmp_path):
    registry, provider, consumer = native

    class Poison:
        def __iter__(self):
            raise AssertionError("must guard before pairs")

        def items(self):
            raise AssertionError("must guard before current rows")

    path = tmp_path / "predictor.json"
    kwargs = {
        "pairs": Poison(),
        "calendar": calendar(),
        "year": 2023,
        "policy": "response_interaction",
        "artifact_path": path,
    }
    with pytest.raises(ValueError, match="incomplete"):
        fit_and_bind_predictor(registry, consumer, provider, **kwargs)
    assert not path.exists()
    registry.bind_feature_source(consumer, provider)
    with pytest.raises(ValueError, match="predeclared"):
        fit_and_bind_predictor(registry, consumer, provider, **(kwargs | {"policy": "risk"}))
    pairs, _dates = sample_pairs()
    model = fit_and_bind_predictor(registry, consumer, provider, **(kwargs | {"pairs": pairs}))
    with pytest.raises(ValueError, match="predeclared"):
        fit_and_bind_predictor(registry, consumer, provider, **kwargs)
    assert (
        registry.fit_lineage(consumer)["fits"][0]["training_signal_sessions"]
        == model["training_signal_sessions"]
    )
    good = {
        "model": model,
        "path": path,
        "signal_date": "2023-01-02",
        "execution_date": "2023-01-03",
        "rows": {"a": pairs[0]["left_row"]},
    }
    assert guarded_predict(registry, consumer, **good) == predict(model, good["rows"])
    with pytest.raises(ValueError):
        guarded_predict(
            registry, consumer, **(good | {"signal_date": "2022-12-26", "rows": Poison()})
        )
    changed = copy.deepcopy(model)
    changed["weights"][0] += 1
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError):
        guarded_predict(registry, consumer, **(good | {"rows": Poison()}))
