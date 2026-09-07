"""Past-observation response estimator prototype; not an executable research epoch.

Native unsupervised-fit integration, supervised forecast training and market
preregistration are still required before this is used on research data.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from statistics import fmean

from .search_power_dsl import sha256_json

VERSION = "11.21-response-prototype-1"
LOOKBACK, RIDGE = 60, 0.01


def aware(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware observation/decision required")
    return parsed


@dataclass(frozen=True)
class ResponseObservation:
    asset: str
    session: int
    observed_at: str
    available_at: str
    flow_ratio: float
    close_return: float


@dataclass(frozen=True)
class ResponseFit:
    version: str
    asset: str
    fit_cutoff: str
    observations: int
    prediction_session: int
    first_session: int
    last_session: int
    last_observed_at: str
    last_available_at: str
    flow_mean: float
    flow_std: float
    return_mean: float
    return_std: float
    slope: float
    observation_sha256: str
    snapshot_sha256: str
    ridge: float = RIDGE

    @property
    def sha256(self):
        return sha256_json(asdict(self))


def fit_response_prefix(observations, *, cutoff, prediction_session, snapshot_sha256):
    """60 contiguous past observations; contemporaneous response,not future labels."""
    end = aware(cutoff)
    if type(prediction_session) is not int or prediction_session < LOOKBACK:
        raise ValueError("explicit global prediction session required")
    if len(snapshot_sha256) != 64 or any(c not in "0123456789abcdef" for c in snapshot_sha256):
        raise ValueError("frozen snapshot SHA256 required")
    available = []
    last_session, last_time = -1, None
    asset = None
    for o in observations:
        if not isinstance(o.asset, str) or not o.asset or o.asset != o.asset.strip():
            raise ValueError("explicit single asset identity required")
        if asset is not None and o.asset != asset:
            raise ValueError("mixed asset observations")
        asset = o.asset
        at, visible = aware(o.observed_at), aware(o.available_at)
        if (
            type(o.session) is not int
            or o.session <= last_session
            or (last_time and at <= last_time)
        ):
            raise ValueError("ordered unique global sessions and timestamps required")
        last_session, last_time = o.session, at
        if visible < at:
            raise ValueError("availability precedes observation")
        # Reject look-ahead BEFORE examining potentially poisoned future values.
        if at >= end or visible >= end or o.session >= prediction_session:
            continue
        available.append(o)
    train = available[-LOOKBACK:]
    if len(train) != LOOKBACK or any(b.session != a.session + 1 for a, b in pairwise(train)):
        raise ValueError("60 contiguous jointly available observations required")
    if train[-1].session != prediction_session - 1:
        raise ValueError("stale response prefix: immediately preceding global session required")
    if any(
        not math.isfinite(o.flow_ratio) or not math.isfinite(o.close_return) or o.close_return <= -1
        for o in train
    ):
        raise ValueError("finite valid past flow/return required")
    x, y = [o.flow_ratio for o in train], [o.close_return for o in train]
    mx, my = fmean(x), fmean(y)
    sx, sy = math.sqrt(fmean((v - mx) ** 2 for v in x)), math.sqrt(fmean((v - my) ** 2 for v in y))
    if min(sx, sy) <= 1e-12 or not all(math.isfinite(v) for v in (mx, my, sx, sy)):
        raise ValueError("unidentified/constant response inputs")
    corr = fmean((a - mx) / sx * (b - my) / sy for a, b in zip(x, y))
    slope = corr / (1 + RIDGE)
    if not math.isfinite(slope) or abs(slope) > 1 / (1 + RIDGE) + 1e-12:
        raise ValueError("invalid response slope")
    return ResponseFit(
        VERSION,
        asset,
        cutoff,
        LOOKBACK,
        prediction_session,
        train[0].session,
        train[-1].session,
        train[-1].observed_at,
        max(train, key=lambda o: aware(o.available_at)).available_at,
        mx,
        sx,
        my,
        sy,
        slope,
        sha256_json([asdict(o) for o in train]),
        snapshot_sha256,
    )


def validate_response_fit(model):
    if model.version != VERSION or model.ridge != RIDGE:
        raise ValueError("response model identity changed")
    if not (
        aware(model.last_observed_at) <= aware(model.last_available_at) < aware(model.fit_cutoff)
    ):
        raise ValueError("response model fit chronology failed")
    if (
        model.observations != LOOKBACK
        or model.last_session - model.first_session != LOOKBACK - 1
        or not all(
            math.isfinite(v)
            for v in (
                model.flow_mean,
                model.flow_std,
                model.return_mean,
                model.return_std,
                model.slope,
            )
        )
        or min(model.flow_std, model.return_std) <= 1e-12
        or abs(model.slope) > 1 / (1 + RIDGE) + 1e-12
    ):
        raise ValueError("invalid response fit statistics")
    return model.sha256


def response_features(model, current, *, decision_at, expected_model_sha256):
    if validate_response_fit(model) != expected_model_sha256:
        raise ValueError("response model identity changed")
    if current.asset != model.asset:
        raise ValueError("response model belongs to a different asset")
    decision, at, visible = (
        aware(decision_at),
        aware(current.observed_at),
        aware(current.available_at),
    )
    if not (aware(model.fit_cutoff) <= at <= visible <= decision):
        raise ValueError("response fit/observation/availability chronology failed")
    if (
        type(current.session) is not int
        or current.session != model.prediction_session
        or current.session != model.last_session + 1
    ):
        raise ValueError("fit unavailable or nonadjacent prediction session")
    if (
        not all(math.isfinite(v) for v in (current.flow_ratio, current.close_return))
        or current.close_return <= -1
    ):
        raise ValueError("finite current observation required")
    x = (current.flow_ratio - model.flow_mean) / model.flow_std
    y = (current.close_return - model.return_mean) / model.return_std
    residual = y - model.slope * x
    if not all(math.isfinite(v) for v in (x, y, residual)):
        raise ValueError("nonfinite response features")
    return {
        "flow_surprise": x,
        "price_response_residual": residual,
        "standardized_own_return": y,
        "inherited_family": "liquidity_impact_absorption",
        "model_sha256": model.sha256,
        "available_at": current.available_at,
        "not_causal": True,
        "validated_alpha": False,
    }
