"""Generated sources and evaluator truth, never QD/warehouse input.

The source generator knows the causal equation. Search receives only PublicPanel;
case identity, random seed and oracle remain with the coordinator/evaluator.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from .contracts import FIELDS, SCENARIOS, Candidate, digest


@dataclass(frozen=True)
class PublicPanel:
    dates: tuple[str, ...]
    instruments: tuple[str, ...]
    features: np.ndarray
    available: np.ndarray
    opening: np.ndarray
    closing: np.ndarray
    groups: np.ndarray
    can_buy: np.ndarray
    can_sell: np.ndarray
    capacity: np.ndarray
    source_kind: str = "generated_synthetic_only"

    def fingerprint(self):
        values = {
            "dates": self.dates,
            "instruments": self.instruments,
            "source_kind": self.source_kind,
        }
        for name in (
            "features",
            "available",
            "opening",
            "closing",
            "groups",
            "can_buy",
            "can_sell",
            "capacity",
        ):
            a = np.ascontiguousarray(getattr(self, name))
            values[name] = {
                "dtype": a.dtype.str,
                "shape": a.shape,
                "sha256": hashlib.sha256(a.tobytes()).hexdigest(),
            }
        return digest(values)

    def validate(self):
        t, n = len(self.dates), len(self.instruments)
        if self.source_kind != "generated_synthetic_only" or (t, n) != (220, 24):
            raise ValueError("only the generated V12 panel is accepted")
        if self.features.shape != (t, n, 4) or self.available.shape != self.features.shape:
            raise ValueError("feature/timing shape mismatch")
        if not np.isfinite(self.features).all():
            raise ValueError("nonfinite source feature")
        for a in (self.opening, self.closing, self.capacity, self.can_buy, self.can_sell):
            if a.shape != (t, n) or not np.isfinite(a).all():
                raise ValueError("bar shape/value mismatch")
        if (self.opening <= 0).any() or (self.closing <= 0).any() or (self.capacity < 0).any():
            raise ValueError("invalid source prices/capacity")
        if self.groups.shape != (n,) or set(self.groups.tolist()) != set(range(6)):
            raise ValueError("six predeclared groups required")
        if any(sum(self.groups == g) != 4 for g in range(6)):
            raise ValueError("four synthetic names per group required")
        if len(set(self.instruments)) != n or any(
            not x.startswith("SYN") for x in self.instruments
        ):
            raise ValueError("unique fictional instrument namespace required")
        if tuple(sorted(set(self.dates))) != self.dates:
            raise ValueError("unique ordered source dates required")
        return self


@dataclass(frozen=True)
class Oracle:
    scenario: str
    expression: str | None
    direction: int | None
    economic_strength: float
    signal: np.ndarray


def generator_contract():
    return {
        "version": "v12-generated-source-1",
        "assets": 24,
        "sessions": 220,
        "fields": FIELDS,
        "feature_ar": 0.92,
        "feature_noise_scale": 0.4,
        "linear_strength": 0.004,
        "interaction_strength": 0.012,
        "noise": "common + six group shocks + independent name shocks; regime-dependent scale",
        "return": "clipped log-return at t uses observable feature at t-1 only",
        "timing": "features available at own EOD; delayed masks excluded before ranking",
        "execution": "next open equals previous close; fixed synthetic capacity and rare open blocks",
        "oracle": "withheld from search; known benchmark families, held-out random seeds",
        "null": "zero predictive injection; all exogenous cross-sectional/regime structure retained",
        "real_data_reads": 0,
    }


def generate(seed, scenario, spec):
    spec.validate()
    if scenario not in SCENARIOS or type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("bounded generated scenario and integer seed required")
    rng = np.random.default_rng(seed)
    t, n = spec.sessions, spec.assets
    dates, day = [], date(2010, 1, 4)
    while len(dates) < t:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    x = np.zeros((t, n, 4))
    x[0] = rng.normal(size=(n, 4))
    for i in range(1, t):
        x[i] = 0.92 * x[i - 1] + 0.4 * rng.normal(size=(n, 4))
    groups = np.repeat(np.arange(6), 4)
    # Field identity is randomized before any search, not chosen from results.
    fields = rng.choice(4, 2, replace=False)
    signal = np.tanh(x[:, :, fields[0]])
    operator, strength = "rank", 0.004
    used_fields = (FIELDS[int(fields[0])],)
    if scenario == "interaction":
        operator, strength = "interaction", 0.012
        signal *= np.tanh(x[:, :, fields[1]])
        used_fields = tuple(FIELDS[int(i)] for i in fields)
    if scenario.endswith("null"):
        strength = 0.0
    available = rng.random((t, n, 4)) > 0.01
    # A delayed feature's predictive effect may still exist but it must not be read.
    common = rng.normal(0, 0.004, t)
    group_noise = rng.normal(0, 0.003, (t, 6))
    specific = rng.normal(0, 0.009, (t, n))
    regime = np.where(np.arange(t) < t // 2, 0.8, 1.5)
    if scenario != "regime_null":
        regime[:] = 1.0
    returns = (common[:, None] + group_noise[:, groups] + specific) * regime[:, None]
    returns[1:] += strength * signal[:-1]
    returns = np.clip(returns, -0.09, 0.09)
    close = 10 * np.exp(np.cumsum(returns, axis=0))
    opening = np.vstack((np.full(n, 10.0), close[:-1]))
    buy = rng.random((t, n)) > 0.003
    sell = rng.random((t, n)) > 0.003
    capacity = np.full((t, n), 2_000_000.0)
    arrays = (x, available, opening, close, groups, buy, sell, capacity)
    for a in arrays:
        a.setflags(write=False)
    signal.setflags(write=False)
    panel = PublicPanel(tuple(dates), tuple(f"SYN{i:03d}" for i in range(n)), *arrays).validate()
    expression = Candidate(operator, used_fields, 1, 5).expression if strength else None
    return panel, Oracle(scenario, expression, 1 if strength else None, strength, signal)
