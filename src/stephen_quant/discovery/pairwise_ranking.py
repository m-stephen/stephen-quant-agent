"""Date-balanced within-cell ranking; scores are not calibrated return forecasts."""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from itertools import combinations_with_replacement, pairwise

import numpy as np

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.evaluation import average_ranks
from stephen_quant.integrity.fit_lineage import FitStage

from .calendar_robustness import PHASES, combine_sleeves
from .risk_stratified import mechanism_days
from .risk_stratified import screen as economic_screen
from .search_power_dsl import sha256_json
from .temporal_increments import MECHANISMS, RISK_FIELDS

VERSION = "11.19.0"
FIELDS = RISK_FIELDS + MECHANISMS
BASES = ("linear", "quadratic")
KINDS = ("full", "risk", "shuffle", "regression")
HORIZON, STRIDE, EMBARGO = 20, 5, 5
L2 = 0.01
MAX_STEPS, GRADIENT_TOL = 40, 1e-9


def plans():
    rows = [
        {
            "basis": b,
            "policy": k,
            "identity": b,
            "scale": c,
            "roundtrip_bps": 82 * c,
            "key": f"{b}-{k}-{82 * c}",
        }
        for b in BASES
        for k in KINDS
        for c in (1, 2)
    ]
    return rows + [
        {
            "basis": "none",
            "policy": k,
            "identity": "control",
            "scale": c,
            "roundtrip_bps": 82 * c,
            "key": f"control-{k}-{82 * c}",
        }
        for k in ("hash", "lowvol", "original_lowvol", "original_stable")
        for c in (1, 2)
    ]


def contract():
    return {
        "version": VERSION,
        "budget": 24,
        "prior_debt": 3600,
        "fields": FIELDS,
        "basis": BASES,
        "kinds": KINDS,
        "features": "V11.14 full-support20consecutive-flow/auction/chip paths;no new primitives",
        "cells": "5equal vol bins then4equal ADV bins per vol bin;ties by instrument",
        "ranks": "2*average_rank/(Ncell+1)-1;current same-cell known features;stateless",
        "basis_definition": "linear x;quadratic x plus all x_i*x_j for i<=j;no intercept",
        "pair_sample": "first64names by fixed SHA256 per cell;adjacent disjoint pairs;before labels",
        "label": "relative20session nextopen-to-open gross return;missingentry rejects pair;missingendpoint pastmark",
        "training": "2023on2022,2024on2022-23;prefix before label creation;5session embargo;stride5",
        "dependence": "overlapping20session labels;date-balanced loss;paircount is not independent sample size",
        "loss": "weighted pair logistic or squared relative-return difference;date totals equal",
        "optimization": {
            "l2": L2,
            "max_newton_steps": MAX_STEPS,
            "gradient_tolerance": GRADIENT_TOL,
            "armijo_backtracking_steps": 32,
        },
        "shuffle": "within each training date/cell rotate accepted leg returns floor(Nlegs/3);no cross-date movement",
        "allocation": "2stocks/cell,top3 incumbent buffer,20cells,4phases0/5/10/15;no score-to-bps hurdle",
        "execution": "nextopen,target_changes;both original anchors full_target;CNY3m;82/164bps",
        "scope": "2022train,2023/24reuseddevelopment,no2025/26",
        "fit_models": 16,
        "native_fit_records": 32,
        "screen": "bothcosts,bothyearspositive,SR>=.7,MDD>=-.25,eachcontroltotal>=3pp,annual>=-5pp,coverage>=.95",
        "validated_alpha": False,
    }


def stages():
    return tuple(
        FitStage(str(y), "2022-01-01", f"{y - 1}-12-31", f"{y}-01-01", f"{y}-12-31")
        for y in (2023, 2024)
    )


def name_hash(name):
    return hashlib.sha256(f"v11.19:184:{name}".encode()).hexdigest()


def ranked_rows(features):
    """Only current cross-sectional values; no labels or learned population filter."""
    if any(not all(k in f and math.isfinite(f[k]) for k in FIELDS) for f in features.values()):
        raise ValueError("finite common fields required")
    ordered = sorted(features, key=lambda n: (features[n]["volatility_20"], n))
    vol = defaultdict(list)
    for i, n in enumerate(ordered):
        vol[5 * i // len(ordered)].append(n)
    groups = {i: [] for i in range(20)}
    for v, names in vol.items():
        names.sort(key=lambda n: (features[n]["liquidity"], n))
        for i, n in enumerate(names):
            groups[4 * v + 4 * i // len(names)].append(n)
    rows = {}
    for cell, names in groups.items():
        names.sort()
        rank = {
            k: dict(
                zip(
                    names,
                    (
                        2 * r / (len(names) + 1) - 1
                        for r in average_ranks([features[n][k] for n in names])
                    ),
                    strict=True,
                )
            )
            for k in FIELDS
        }
        for n in names:
            rows[n] = {
                "cell": cell,
                "x": [rank[k][n] for k in FIELDS],
                "vol": features[n]["volatility_20"],
            }
    return rows


def pair_names(rows):
    groups = defaultdict(list)
    for n, row in rows.items():
        groups[row["cell"]].append(n)
    output = []
    for cell, names in sorted(groups.items()):
        ordered = sorted(names, key=lambda n: (name_hash(n), n))[:64]
        output += [(cell, ordered[i], ordered[i + 1]) for i in range(0, len(ordered) - 1, 2)]
    return output


def basis_vector(x, basis, kind):
    if basis not in BASES or kind not in KINDS or len(x) != 6:
        raise ValueError("registered basis and six ranked inputs required")
    if not all(math.isfinite(v) and -1 <= v <= 1 for v in x):
        raise ValueError("bounded finite rank inputs required")
    z = list(x[:3] if kind == "risk" else x)
    return (
        z + [z[i] * z[j] for i, j in combinations_with_replacement(range(len(z)), 2)]
        if basis == "quadratic"
        else z
    )


def leg_label(bars, i, n):
    entry = bars[i + 1].get(n)
    if entry is None or not math.isfinite(entry.open_price) or entry.open_price <= 0:
        return {
            "entry_valid": False,
            "return": None,
            "entry_price": None,
            "end_price": None,
            "mark_date": None,
            "fresh_end": False,
        }
    endpoint = bars[i + HORIZON + 1].get(n)
    if endpoint is not None and math.isfinite(endpoint.open_price) and endpoint.open_price > 0:
        price, date, fresh = endpoint.open_price, endpoint.trade_date, True
    else:
        past = [
            bars[j][n]
            for j in range(i + 1, i + HORIZON + 1)
            if n in bars[j] and math.isfinite(bars[j][n].close_price) and bars[j][n].close_price > 0
        ]
        price = past[-1].close_price if past else entry.open_price
        date, fresh = (past[-1].trade_date if past else entry.trade_date), False
    return {
        "entry_valid": True,
        "return": price / entry.open_price - 1,
        "entry_price": entry.open_price,
        "end_price": price,
        "mark_date": date,
        "fresh_end": fresh,
    }


def training_pairs(days, cache):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered nonempty global sessions required")
    # Construct no label past the latest eligible training prefix, even though
    # frozen development features are available to the caller.
    prefix = tuple(d for d in days if "2022-01-01" <= d.date < "2024-01-01")[:-EMBARGO]
    bars = [{b.instrument: b for b in day.bars} for day in prefix]
    result = []
    for i in range(0, len(prefix) - HORIZON - 1, STRIDE):
        signal = prefix[i]
        if signal.date not in cache:
            cache[signal.date] = ranked_rows(signal.features)
        current = cache[signal.date]
        for cell, a, b in pair_names(current):
            left, right = leg_label(bars, i, a), leg_label(bars, i, b)
            result.append(
                {
                    "date": signal.date,
                    "entry_date": prefix[i + 1].date,
                    "label_end": prefix[i + HORIZON + 1].date,
                    "cell": cell,
                    "left": a,
                    "right": b,
                    "left_x": current[a]["x"],
                    "right_x": current[b]["x"],
                    "left_label": left,
                    "right_label": right,
                    "supported": left["entry_valid"] and right["entry_valid"],
                }
            )
    return result


def design_matrix(rows, basis, kind):
    if not rows:
        raise ValueError("training pairs required")
    counts = Counter(r["date"] for r in rows)
    dates = len(counts)
    weights = np.asarray([1 / (dates * counts[r["date"]]) for r in rows])
    x = np.asarray(
        [
            [
                a - b
                for a, b in zip(
                    basis_vector(r["left_x"], basis, kind),
                    basis_vector(r["right_x"], basis, kind),
                    strict=True,
                )
            ]
            for r in rows
        ]
    )
    outcomes = {
        i: (r["left_label"]["return"], r["right_label"]["return"]) for i, r in enumerate(rows)
    }
    if kind == "shuffle":
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[(r["date"], r["cell"])].append(i)
        for indices in groups.values():
            flat = [v for i in indices for v in outcomes[i]]
            shift = len(flat) // 3
            rotated = flat[-shift:] + flat[:-shift] if shift else flat
            for j, i in enumerate(indices):
                outcomes[i] = (rotated[2 * j], rotated[2 * j + 1])
    delta = np.asarray([outcomes[i][0] - outcomes[i][1] for i in range(len(rows))])
    y = delta if kind == "regression" else np.where(delta > 0, 1.0, np.where(delta < 0, 0.0, 0.5))
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("finite supported pair matrix required")
    return x, y, weights


def objective(beta, x, y, weights, regression=False):
    z = x @ beta
    if regression:
        errors, curvature = z - y, np.ones(len(y))
        loss = float(np.sum(weights * (z - y) ** 2) / 2)
    else:
        probability = 0.5 + 0.5 * np.tanh(z / 2)
        errors, curvature = probability - y, probability * (1 - probability)
        loss = float(np.sum(weights * (np.logaddexp(0, z) - y * z)))
    grad = x.T @ (weights * errors) + L2 * beta
    hessian = x.T @ ((weights * curvature)[:, None] * x) + L2 * np.eye(x.shape[1])
    return loss + L2 * float(beta @ beta) / 2, grad, hessian


def optimize(x, y, weights, regression=False):
    if x.ndim != 2 or len(y) != len(x) or len(weights) != len(x) or not len(x):
        raise ValueError("aligned nonempty training matrix required")
    if (
        not all(np.isfinite(a).all() for a in (x, y, weights))
        or np.any(weights <= 0)
        or not math.isclose(float(weights.sum()), 1.0, abs_tol=1e-12)
    ):
        raise ValueError("finite normalized positive date weights required")
    if not regression and np.any((y < 0) | (y > 1)):
        raise ValueError("pair target probability outside unit interval")
    beta = np.zeros(x.shape[1])
    trace = []
    for _ in range(MAX_STEPS):
        loss, grad, hessian = objective(beta, x, y, weights, regression)
        trace.append(loss)
        if float(np.max(np.abs(grad))) <= GRADIENT_TOL:
            return beta, {"loss_trace": trace, "gradient_max": float(np.max(np.abs(grad)))}
        step = np.linalg.solve(hessian, grad)
        for backoff in range(32):
            scale = 0.5**backoff
            proposal = beta - scale * step
            new_loss = objective(proposal, x, y, weights, regression)[0]
            if new_loss <= loss - 1e-4 * scale * float(grad @ step):
                beta = proposal
                break
        else:
            raise ValueError("fixed optimizer line search failed")
    raise ValueError("fixed optimizer did not converge")


def fit_model(pairs, calendar, year, basis, kind):
    if year not in (2023, 2024) or calendar != sorted(set(calendar)):
        raise ValueError("registered year and global calendar required")
    prefix = [d for d in calendar if "2022-01-01" <= d < f"{year}-01-01"]
    if len(prefix) <= EMBARGO:
        raise ValueError("insufficient prefix")
    cutoff = prefix[-EMBARGO - 1]
    rows = [
        r
        for r in pairs
        if r["supported"] and "2022-01-01" <= r["date"] < r["entry_date"] < r["label_end"] <= cutoff
    ]
    keys = [(r["date"], r["cell"], r["left"], r["right"]) for r in rows]
    if len(keys) != len(set(keys)) or [r["date"] for r in rows] != sorted(r["date"] for r in rows):
        raise ValueError("duplicate or unordered training pairs")
    sessions = sorted({r["date"] for r in rows})
    if len(sessions) < 30:
        raise ValueError("minimum30 actual training dates required")
    x, y, weights = design_matrix(rows, basis, kind)
    beta, trace = optimize(x, y, weights, kind == "regression")
    return {
        "year": year,
        "basis": basis,
        "kind": kind,
        "fit_cutoff": cutoff,
        "maximum_label_end": max(r["label_end"] for r in rows),
        "training_signal_sessions": sessions,
        "training_signal_dates": len(sessions),
        "training_pairs": len(rows),
        "training_rows_sha256": sha256_json(rows),
        "training_design_sha256": sha256_json(
            {"x": x.tolist(), "y": y.tolist(), "weights": weights.tolist()}
        ),
        "weights": beta.tolist(),
        "parameter_count": len(beta),
        "optimizer": trace,
        "date_weight_range": [1 / len(sessions), 1 / len(sessions)],
    }


def score(model, x):
    phi = basis_vector(x, model["basis"], model["kind"])
    if len(phi) != len(model["weights"]) or not all(math.isfinite(v) for v in model["weights"]):
        raise ValueError("invalid model parameters")
    return sum(a * b for a, b in zip(phi, model["weights"], strict=True))


def select(rows, values, previous):
    if set(rows) != set(values) or not all(math.isfinite(v) for v in values.values()):
        raise ValueError("complete finite current score support required")
    selected = []
    for cell in range(20):
        names = sorted(
            (n for n, row in rows.items() if row["cell"] == cell), key=lambda n: (-values[n], n)
        )
        chosen = [n for n in names[:3] if n in previous][:2]
        chosen += [n for n in names if n not in chosen][: 2 - len(chosen)]
        selected.extend(chosen)
    return tuple(sorted(selected))


def targets_for(registry, tid, days, policy, cache, models=None, paths=None):
    if (
        policy not in KINDS + ("hash", "lowvol")
        or not days
        or any(a.date >= b.date for a, b in pairwise(days))
    ):
        raise ValueError("registered policy and ordered window required")
    if policy in KINDS and (models is None or paths is None):
        raise ValueError("immutable native models required")
    if policy not in KINDS and registry.fit_lineage(tid) != {
        "stages": [],
        "fits": [],
        "sha256": sha256_json([]),
    }:
        raise ValueError("native no-fit control required")
    sleeves, diagnostics = [], []
    for phase in PHASES:
        previous, targets = (), []
        for i, day in enumerate(days):
            signal = days[i - 1] if i else None
            refresh = i >= phase + 1 and (i - phase - 1) % HORIZON == 0
            weights = {}
            if refresh:
                if policy in KINDS:
                    model = models[int(day.date[:4])]
                    registry.assert_prediction_fit(
                        tid,
                        model=model,
                        artifact_path=paths[int(day.date[:4])],
                        prediction_date=day.date,
                        signal_date=signal.date,
                    )
                if signal.date not in cache:
                    cache[signal.date] = ranked_rows(signal.features)
                rows = cache[signal.date]
                if policy in KINDS:
                    values = {n: score(model, row["x"]) for n, row in rows.items()}
                elif policy == "hash":
                    values = {n: int(name_hash(n), 16) for n in rows}
                else:
                    values = {n: -row["vol"] for n, row in rows.items()}
                chosen = select(rows, values, previous)
                diagnostics.append(
                    {
                        "date": signal.date,
                        "phase": phase,
                        "eligible": len(rows),
                        "selected": len(chosen),
                        "new_members": len(set(chosen) - set(previous)),
                        "scores_sha256": sha256_json(values),
                    }
                )
                previous = chosen
                weights = {n: 0.025 for n in chosen}
            targets.append(
                TargetAllocation(
                    day.date,
                    f"{signal.date}T23:59:59+08:00" if signal else f"{day.date}T08:00:00+08:00",
                    weights,
                    refresh,
                )
            )
        sleeves.append(tuple(targets))
    return combine_sleeves(sleeves), diagnostics


def prepare(days):
    return mechanism_days(days)


def screen(candidate, controls, diagnostics):
    checks = economic_screen(candidate, controls)
    for year in ("2023", "2024"):
        rows = [d for d in diagnostics if d["date"].startswith(year)]
        checks[f"coverage_{year}"] = (
            bool(rows) and sum(d["selected"] for d in rows) / (40 * len(rows)) >= 0.95
        )
    return checks
