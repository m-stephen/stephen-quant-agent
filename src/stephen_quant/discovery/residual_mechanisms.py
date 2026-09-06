"""Bounded training-only incremental mechanisms, not a statistical certificate."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from itertools import pairwise

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.discovery.calendar_robustness import PHASES, combine_sleeves
from stephen_quant.evaluation import average_ranks

VERSION = "11.10.0"
MECHANISMS = ("flow_reversal", "chip_reversal", "auction_late_disagreement")
FIELDS = (
    "volatility_20",
    "ret_20",
    "liquidity",
    "net_inflow_ratio",
    "concentration",
    "auction_return",
    "late_30_return",
)
HORIZON = 20
EMBARGO_SESSIONS = 5
HURDLE = 0.0122  # 82bps replacement cost + 40bps uncertainty margin, fixed for all costs.
POLICIES = MECHANISMS + ("risk_hash", "lowvol")


def contract():
    return {
        "mechanisms": list(MECHANISMS),
        "fields": list(FIELDS),
        "horizon": HORIZON,
        "label": "next_open_to_open_after20sessions; missing_exit=-100%; missing_entry=excluded",
        "sample_stride": 5,
        "embargo_sessions": EMBARGO_SESSIONS,
        "training": "expanding2022prefix; refit_before2023_and2024; labels_mature_before_cutoff",
        "nuisance": "intercept+asof_cross_sectional_rank(vol20,ret20,ADV60)",
        "signal": "flow*(-ret20);chip_width*(-ret20);auction*(-late30); centered ranks",
        "fit": "OLS nuisance with1e-10 numerical diagonal; residual slope ridge0.01",
        "allocation": "5volatility_x4liquidity_rank_cells;2stocks_per_cell;max40;2.5%each",
        "selection": "retain prior desired names within cell; fill hash; replace only if predicted increment>hurdle",
        "hurdle_return": HURDLE,
        "calendar": "fixed_four_cohort_netting_0_5_10_15",
        "costs_roundtrip_bps": [41, 82, 102],
        "capital_cny": 3_000_000,
        "fit_is_not_brokerage_label": True,
        "hurdle_scope": "discretionary within-cell replacements only; mandatory coverage/cell migration and netting drift still trade",
        "economic_screen": {
            "costs": [82, 102],
            "both_years_positive": True,
            "sharpe_min": 0.7,
            "drawdown_floor": -0.25,
            "total_increment_vs_each_control_min": 0.03,
            "annual_increment_vs_lowvol_floor": -0.05,
        },
        "validated_alpha": False,
    }


def ranked_rows(features):
    names = sorted(
        n for n, f in features.items() if all(k in f and math.isfinite(f[k]) for k in FIELDS)
    )
    ranks = {
        k: dict(
            zip(
                names,
                (r / (len(names) + 1) for r in average_ranks([features[n][k] for n in names])),
                strict=True,
            )
        )
        for k in FIELDS
    }
    rows = {}
    for n in names:
        v = {k: 2 * ranks[k][n] - 1 for k in FIELDS}
        rows[n] = {
            "x": [1.0, v["volatility_20"], v["ret_20"], v["liquidity"]],
            "z": {
                "flow_reversal": -v["net_inflow_ratio"] * v["ret_20"],
                "chip_reversal": -v["concentration"] * v["ret_20"],
                "auction_late_disagreement": -v["auction_return"] * v["late_30_return"],
            },
            "cell": (
                min(4, int(ranks["volatility_20"][n] * 5)),
                min(3, int(ranks["liquidity"][n] * 4)),
            ),
            "vol": ranks["volatility_20"][n],
        }
    return rows


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def solve(matrix, vector):
    a = [list(row) + [v] for row, v in zip(matrix, vector, strict=True)]
    for j in range(len(a)):
        pivot = max(range(j, len(a)), key=lambda i: abs(a[i][j]))
        a[j], a[pivot] = a[pivot], a[j]
        if abs(a[j][j]) < 1e-14:
            raise ValueError("singular nuisance design")
        scale = a[j][j]
        a[j] = [v / scale for v in a[j]]
        for i in range(len(a)):
            if i != j:
                scale = a[i][j]
                a[i] = [v - scale * w for v, w in zip(a[i], a[j], strict=True)]
    return [row[-1] for row in a]


class ResidualFit:
    """Sufficient statistics only. No inference, validation labels or tuning."""

    def __init__(self):
        self.n = 0
        self.xx = [[0.0] * 4 for _ in range(4)]
        self.xy, self.xz = [0.0] * 4, [0.0] * 4
        self.zz = self.zy = 0.0

    def add(self, x, z, y):
        if len(x) != 4 or not all(math.isfinite(v) for v in [*x, z, y]):
            raise ValueError("finite four-column design required")
        self.n += 1
        for i in range(4):
            self.xy[i] += x[i] * y
            self.xz[i] += x[i] * z
            for j in range(4):
                self.xx[i][j] += x[i] * x[j]
        self.zz += z * z
        self.zy += z * y

    def finish(self):
        if self.n < 100:
            raise ValueError("insufficient training rows")
        xx = [[v / self.n for v in row] for row in self.xx]
        stabilized = [
            [v + (1e-10 if i == j else 0) for j, v in enumerate(row)] for i, row in enumerate(xx)
        ]
        xy, xz = ([v / self.n for v in row] for row in (self.xy, self.xz))
        by, bz = solve(stabilized, xy), solve(stabilized, xz)
        variance = max(
            0.0, self.zz / self.n - 2 * dot(bz, xz) + dot(bz, [dot(row, bz) for row in xx])
        )
        covariance = (
            self.zy / self.n - dot(by, xz) - dot(bz, xy) + dot(bz, [dot(row, by) for row in xx])
        )
        slope = covariance / (variance + 0.01) if variance > 1e-6 else 0.0
        return {
            "samples": self.n,
            "nuisance_y": by,
            "nuisance_z": bz,
            "residual_variance": variance,
            "slope": slope,
            "ridge": 0.01,
        }


def predict(row, model, mechanism):
    if mechanism not in MECHANISMS:
        raise ValueError("unregistered mechanism")
    value = model["slope"] * (row["z"][mechanism] - dot(row["x"], model["nuisance_z"]))
    if not math.isfinite(value):
        raise ValueError("nonfinite incremental prediction")
    return value


def fit_year(days, year, cache=None):
    if year not in (2023, 2024) or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("registered year and ordered dates required")
    # Slice by date BEFORE any labels are constructed; embargo entire final five sessions.
    prefix = tuple(d for d in days if "2022-01-01" <= d.date < f"{year}-01-01")
    prefix = prefix[:-EMBARGO_SESSIONS]
    if len(prefix) <= HORIZON + 1:
        raise ValueError("insufficient matured prefix")
    cache = {} if cache is None else cache
    fits = {m: ResidualFit() for m in MECHANISMS}
    missing_entry = missing_exit = 0
    training_sessions = []
    maximum_label_end = ""
    for i in range(0, len(prefix) - HORIZON - 1, 5):
        signal = prefix[i]
        if signal.date not in cache:
            cache[signal.date] = ranked_rows(signal.features)
        rows = cache[signal.date]
        entry = {b.instrument: b.open_price for b in prefix[i + 1].bars}
        exit_prices = {b.instrument: b.open_price for b in prefix[i + HORIZON + 1].bars}
        accepted = 0
        for n, row in rows.items():
            if n not in entry or not math.isfinite(entry[n]) or entry[n] <= 0:
                missing_entry += 1
                continue
            if n not in exit_prices:
                y = -1.0  # Conservative target, not evidence of a real delisting.
                missing_exit += 1
            else:
                y = exit_prices[n] / entry[n] - 1
            for m, fit in fits.items():
                fit.add(row["x"], row["z"][m], y)
            accepted += 1
        if accepted:
            training_sessions.append(signal.date)
            maximum_label_end = prefix[i + HORIZON + 1].date
    return {
        "year": year,
        "fit_cutoff": prefix[-1].date,
        "maximum_label_end": maximum_label_end,
        "training_signal_dates": len(training_sessions),
        "training_signal_sessions": training_sessions,
        "missing_entry_excluded": missing_entry,
        "missing_exit_imputed_loss": missing_exit,
        "models": {m: fit.finish() for m, fit in fits.items()},
    }


def hash_key(n):
    return hashlib.sha256(("issue184-residual-control:" + n).encode()).hexdigest()


def select(rows, previous, kind, model=None):
    if kind not in POLICIES:
        raise ValueError("unregistered policy")
    if kind == "lowvol":
        order = sorted(rows, key=lambda n: (rows[n]["vol"], n))
        kept = [n for n in order[:50] if n in previous][:40]
        return tuple(kept + [n for n in order if n not in kept][: 40 - len(kept)]), 0
    cells = defaultdict(list)
    for n, row in rows.items():
        cells[row["cell"]].append(n)
    chosen, replaced = [], 0
    for cell in sorted(cells):
        names = sorted(cells[cell], key=lambda n: (hash_key(n), n))
        # The same fixed stable-hash fallback when a cohort is new or its names leave a cell.
        current = [n for n in names if n in previous][:2]
        current += [n for n in names if n not in current][: 2 - len(current)]
        if kind != "risk_hash":
            scores = {n: predict(rows[n], model, kind) for n in names}
            for challenger in sorted(names, key=lambda n: (-scores[n], n)):
                if challenger in current or not current:
                    continue
                worst = min(current, key=lambda n: (scores[n], n))
                if scores[challenger] - scores[worst] > HURDLE:
                    current.remove(worst)
                    current.append(challenger)
                    replaced += 1
        chosen.extend(sorted(current))
    return tuple(chosen), replaced


def targets_for(days, models, kind, cache=None):
    if kind not in POLICIES or not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("registered policy and ordered nonempty dates required")
    cache = {} if cache is None else cache
    sleeves, diagnostics = [], []
    for phase in PHASES:
        previous, targets = (), []
        for i, day in enumerate(days):
            signal = days[i - 1] if i else None
            rebalance = i >= phase + 1 and (i - phase - 1) % HORIZON == 0
            weights = {}
            if rebalance:
                trained = models[int(day.date[:4])]
                if (
                    trained["maximum_label_end"] > trained["fit_cutoff"]
                    or trained["fit_cutoff"] >= signal.date
                ):
                    raise ValueError("model labels not strictly before signal")
                if signal.date not in cache:
                    cache[signal.date] = ranked_rows(signal.features)
                rows = cache[signal.date]
                previous, replacements = select(rows, previous, kind, trained["models"].get(kind))
                weights = {n: 0.025 for n in previous}
                diagnostics.append(
                    {
                        "date": signal.date,
                        "phase": phase,
                        "matched": len(rows),
                        "selected": len(previous),
                        "hurdle_replacements": replacements,
                    }
                )
            targets.append(
                TargetAllocation(
                    day.date,
                    f"{signal.date}T23:59:59+08:00" if signal else f"{day.date}T08:00:00+08:00",
                    weights,
                    rebalance,
                )
            )
        sleeves.append(tuple(targets))
    result = combine_sleeves(sleeves)
    return result, diagnostics


def plans():
    return [
        {"kind": "fit", "policy": m, "year": year} for year in (2023, 2024) for m in MECHANISMS
    ] + [{"kind": "account", "policy": p, "cost_bps": c} for p in POLICIES for c in (41, 82, 102)]


def public_model(model):
    """Only numerical model summaries; no stock or raw source records."""
    return {k: v for k, v in model.items() if k != "raw_rows"}
