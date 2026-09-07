from dataclasses import replace
from datetime import datetime, timedelta, timezone
from statistics import fmean

import numpy as np
import pytest

from stephen_quant.discovery.flow_response import (
    LOOKBACK,
    RIDGE,
    ResponseObservation,
    fit_response_prefix,
    response_features,
)

SNAPSHOT = "a" * 64


def stamp(i, hour=16):
    return (datetime(2022, 1, 1, hour, tzinfo=timezone.utc) + timedelta(days=i)).isoformat()


def rows(count=60, sign=1):
    # Orthogonal deterministic X and error; no market observations or future labels.
    x = np.tile([-2.0, -1.0, 1.0, 2.0], count // 4 + 1)[:count]
    noise = np.tile([-1.0, 1.0, 1.0, -1.0], count // 4 + 1)[:count]
    return [
        ResponseObservation(
            "synthetic-stock",
            i,
            stamp(i),
            stamp(i, 17),
            float(a * 0.01),
            float(sign * 0.003 * a + 0.002 * b),
        )
        for i, (a, b) in enumerate(zip(x, noise))
    ]


def fit(source=None, session=60, **kwargs):
    return fit_response_prefix(
        rows() if source is None else source,
        cutoff=stamp(session, 9),
        prediction_session=session,
        snapshot_sha256=SNAPSHOT,
        **kwargs,
    )


def current(i=60):
    return ResponseObservation("synthetic-stock", i, stamp(i), stamp(i, 17), 0.03, 0.01)


def features(model, observation=None, **kwargs):
    return response_features(
        model,
        current() if observation is None else observation,
        decision_at=stamp(60, 18),
        expected_model_sha256=model.sha256,
        **kwargs,
    )


def test_closed_form_independent_linalg_and_replay():
    source, model = rows(), fit()
    x = np.array([o.flow_ratio for o in source])
    y = np.array([o.close_return for o in source])
    x, y = (x - x.mean()) / x.std(), (y - y.mean()) / y.std()
    beta = np.linalg.solve(np.array([[x @ x + LOOKBACK * RIDGE]]), np.array([x @ y]))[0]
    assert model.slope == pytest.approx(beta, abs=1e-14)
    assert fit() == model
    assert fit().sha256 == model.sha256
    assert model.first_session == 0 and model.last_session == 59
    assert model.prediction_session == 60 and model.observations == 60
    result = features(model)
    assert result["price_response_residual"] == pytest.approx(
        (0.01 - model.return_mean) / model.return_std
        - beta * (0.03 - model.flow_mean) / model.flow_std
    )
    assert not result["validated_alpha"] and result["not_causal"]


def test_units_do_not_change_standardized_features():
    source = rows()
    scaled = [
        replace(o, flow_ratio=o.flow_ratio * 1000, close_return=o.close_return * 2) for o in source
    ]
    a, b = (
        features(fit()),
        features(fit(scaled), replace(current(), flow_ratio=30, close_return=0.02)),
    )
    for name in ("flow_surprise", "price_response_residual", "standardized_own_return"):
        assert a[name] == pytest.approx(b[name], abs=1e-12)


def test_future_poison_never_enters_past_fit():
    future = [replace(o, flow_ratio=float("nan"), close_return=float("inf")) for o in rows(68)[60:]]
    assert fit(rows() + future) == fit()
    changed = rows()
    changed[0] = replace(changed[0], flow_ratio=0.2)
    assert fit(changed).observation_sha256 != fit().observation_sha256
    assert fit(changed).sha256 != fit().sha256


def test_response_not_algebraically_old_flow_price_rank_product():
    positive, negative = rows(sign=1), rows(sign=-1)
    # Exact same flow history, current flow and current return, and 20-day return product.
    # Products match because the two periodic return vectors are permutations.
    for source in (positive, negative):
        assert fmean(o.flow_ratio for o in source[-20:]) == 0
    assert np.prod([1 + o.close_return for o in positive[-20:]]) == pytest.approx(
        np.prod([1 + o.close_return for o in negative[-20:]]), rel=0, abs=1e-14
    )
    a, b = features(fit(positive)), features(fit(negative))
    assert a["flow_surprise"] == pytest.approx(b["flow_surprise"])
    assert a["standardized_own_return"] == pytest.approx(b["standardized_own_return"])
    assert abs(a["price_response_residual"] - b["price_response_residual"]) > 1
    # Representational distinctness, not a predictive or causal discovery.
    assert not a["validated_alpha"] and not b["validated_alpha"]


@pytest.mark.parametrize(
    "case",
    [
        "short",
        "gap",
        "duplicate",
        "unordered",
        "future_available",
        "constant_flow",
        "constant_return",
        "nan",
        "loss",
        "before_observed",
        "naive",
    ],
)
def test_invalid_prefix_fails_closed(case):
    source = rows()
    if case == "short":
        source.pop()
    elif case == "gap":
        source.pop(20)
    elif case == "duplicate":
        source.insert(20, source[20])
    elif case == "unordered":
        source[20], source[21] = source[21], source[20]
    elif case == "future_available":
        source[-1] = replace(source[-1], available_at=stamp(60, 20), flow_ratio=float("nan"))
    elif case.startswith("constant"):
        source = [
            replace(o, **{"flow_ratio" if case == "constant_flow" else "close_return": 0.01})
            for o in source
        ]
    else:
        changes = {
            "nan": {"flow_ratio": float("nan")},
            "loss": {"close_return": -1.0},
            "before_observed": {"available_at": stamp(10, 15)},
            "naive": {"observed_at": stamp(10)[:-6]},
        }
        source[10] = replace(source[10], **changes[case])
    with pytest.raises(ValueError):
        fit(source)


def test_stale_prefix_and_unavailable_last_day_cannot_silently_fallback():
    with pytest.raises(ValueError, match="stale"):
        fit(rows(), session=61)
    delayed = rows(61)
    delayed[-1] = replace(delayed[-1], available_at=stamp(61, 20), flow_ratio=float("nan"))
    with pytest.raises(ValueError, match="stale"):
        fit(delayed, session=61)
    complete = fit(rows(61), session=61)
    assert complete.first_session == 1 and complete.last_session == 60


def test_bad_numeric_row_can_roll_off_after_sixty_clean_sessions():
    source = rows(61)
    source[0] = replace(source[0], flow_ratio=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        fit(source[:60])
    assert fit(source, session=61) == fit(rows(61), session=61)


def test_within_stock_model_cannot_be_reused_for_a_different_stock():
    with pytest.raises(ValueError, match="different asset"):
        features(fit(), replace(current(), asset="other-stock"))
    source = rows()
    source[20] = replace(source[20], asset="other-stock")
    with pytest.raises(ValueError, match="mixed asset"):
        fit(source)
    source = [replace(o, asset=" ") for o in rows()]
    with pytest.raises(ValueError, match="single asset"):
        fit(source)


@pytest.mark.parametrize("case", ["training", "gap", "late", "early", "nan", "loss"])
def test_prediction_timing_and_numeric_guards(case):
    observation = {
        "training": current(59),
        "gap": current(61),
        "late": replace(current(), available_at=stamp(60, 19)),
        "early": replace(current(), available_at=stamp(60, 15)),
        "nan": replace(current(), flow_ratio=float("nan")),
        "loss": replace(current(), close_return=-1.0),
    }[case]
    with pytest.raises(ValueError):
        features(fit(), observation)


def test_model_identity_and_invalid_fit_guard():
    model = fit()
    with pytest.raises(ValueError, match="identity"):
        response_features(
            replace(model, slope=0.2),
            current(),
            decision_at=stamp(60, 18),
            expected_model_sha256=model.sha256,
        )
    with pytest.raises(ValueError, match="statistics"):
        features(replace(model, flow_std=0))
    with pytest.raises(ValueError, match="snapshot"):
        fit_response_prefix(
            rows(), cutoff=stamp(60, 9), prediction_session=60, snapshot_sha256="bad"
        )
    with pytest.raises(ValueError, match="prediction session"):
        fit(rows(), session=True)
