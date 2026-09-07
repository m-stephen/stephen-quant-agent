"""Prefix-invariant generated panels, separated exogenous random streams."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from ..research_reset.contracts import FIELDS, SCENARIOS, Candidate, digest
from ..research_reset.sources import Oracle, PublicPanel


@dataclass(frozen=True)
class PowerPanel(PublicPanel):
    def validate(self):
        t, n = len(self.dates), len(self.instruments)
        if self.source_kind != "generated_synthetic_only" or n != 24 or t not in (220, 460, 820):
            raise ValueError("only predeclared generated V12.1 panels accepted")
        # Reuse all existing validation rules on a real prefix, not a mutable proxy.
        PublicPanel(
            self.dates[:220],
            self.instruments,
            self.features[:220],
            self.available[:220],
            self.opening[:220],
            self.closing[:220],
            self.groups,
            self.can_buy[:220],
            self.can_sell[:220],
            self.capacity[:220],
            self.source_kind,
        ).validate()
        if tuple(sorted(set(self.dates))) != self.dates:
            raise ValueError("full calendar must be ordered and unique")
        for name in (
            "features",
            "available",
            "opening",
            "closing",
            "can_buy",
            "can_sell",
            "capacity",
        ):
            a = getattr(self, name)
            shape = (t, n, 4) if name in ("features", "available") else (t, n)
            if a.shape != shape or not np.isfinite(a).all():
                raise ValueError("full generated shape/value mismatch")
        if (self.opening <= 0).any() or (self.closing <= 0).any() or (self.capacity < 0).any():
            raise ValueError("invalid full generated price/capacity")
        for a in (self.available, self.can_buy, self.can_sell):
            if a.dtype != np.dtype(bool):
                raise ValueError("boolean source masks required")
        return self


def generator_contract():
    return {
        "version": "v12.1-prefix-streams-1",
        "assets": 24,
        "groups": 6,
        "feature_ar": 0.92,
        "feature_innovation_sd": 0.4,
        "linear_strength": 0.004,
        "interaction_strength": 0.012,
        "fixed_regime_break": 110,
        "regime_before_after": [0.8, 1.5],
        "streams": [
            "identity",
            "features",
            "availability",
            "common",
            "groups",
            "specific",
            "buy",
            "sell",
        ],
        "timing": "close(t) depends on feature(t-1); decision as of prior EOD",
        "interpretation": "known synthetic families; new streams, not original V12.0 samples",
        "real_data_reads": 0,
    }


def generate(seed, scenario, spec):
    spec.validate()
    if scenario not in SCENARIOS or type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("named synthetic scenario and bounded integer seed required")

    def rng(name):
        key = int(digest({"seed": seed, "stream": name})[:15], 16)
        return np.random.default_rng(key)

    t, n = spec.sessions, spec.assets
    dates, day = [], date(2010, 1, 4)
    while len(dates) < t:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += timedelta(days=1)
    x = np.zeros((t, n, 4))
    feature_rng = rng("features")
    x[0] = feature_rng.normal(size=(n, 4))
    for i in range(1, t):
        x[i] = 0.92 * x[i - 1] + 0.4 * feature_rng.normal(size=(n, 4))
    groups = np.repeat(np.arange(6), 4)
    fields = rng("identity").choice(4, 2, replace=False)
    signal = np.tanh(x[:, :, fields[0]])
    operator, strength = "rank", 0.004
    used = (FIELDS[int(fields[0])],)
    if scenario == "interaction":
        operator, strength = "interaction", 0.012
        signal *= np.tanh(x[:, :, fields[1]])
        used = tuple(FIELDS[int(i)] for i in fields)
    strength *= spec.strength_multiplier
    if scenario.endswith("null"):
        strength = 0.0
    available = rng("availability").random((t, n, 4)) > 0.01
    common = rng("common").normal(0, 0.004, t)
    group_noise = rng("groups").normal(0, 0.003, (t, 6))
    specific = rng("specific").normal(0, 0.009, (t, n))
    regime = np.where(np.arange(t) < 110, 0.8, 1.5) if scenario == "regime_null" else np.ones(t)
    returns = (common[:, None] + group_noise[:, groups] + specific) * regime[:, None]
    returns[1:] += strength * signal[:-1]
    closing = 10 * np.exp(np.cumsum(np.clip(returns, -0.09, 0.09), axis=0))
    opening = np.vstack((np.full(n, 10.0), closing[:-1]))
    buy = rng("buy").random((t, n)) > 0.003
    sell = rng("sell").random((t, n)) > 0.003
    capacity = np.full((t, n), 2_000_000.0)
    arrays = (x, available, opening, closing, groups, buy, sell, capacity)
    for a in arrays:
        a.setflags(write=False)
    signal.setflags(write=False)
    panel = PowerPanel(tuple(dates), tuple(f"SYN{i:03d}" for i in range(n)), *arrays).validate()
    expression = Candidate(operator, used, 1, 5).expression if strength else None
    return panel, Oracle(scenario, expression, 1 if strength else None, strength, signal)
