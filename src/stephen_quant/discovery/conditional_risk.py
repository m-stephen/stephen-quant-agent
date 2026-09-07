"""Small train-only portfolio overlay; proxy labels are not executable P&L."""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

import numpy as np

from stephen_quant.integrity.fit_lineage import FitStage

from .risk_stratified import screen as economic_screen
from .search_power_dsl import sha256_json

VERSION = "11.18.0"
BASES = ("lowvol", "stable_lowrisk")
RULES = ("mean", "mean_second")
POLICIES = ("model", "fixed", "lag20", "shuffle")
FIELDS = ("breadth20", "mean_return20", "mean_volatility20", "dispersion1")
RISK = ("ret_20", "volatility_20", "liquidity")
BASKET, HORIZON, MIN_TRAIN = 200, 5, 30


def plans():
    rows = [
        {
            "base": b,
            "rule": r,
            "policy": p,
            "scale": c,
            "identity": f"{b}-{r}",
            "roundtrip_bps": 82 * c,
            "key": f"{b}-{r}-{p}-{82 * c}",
        }
        for b in BASES
        for r in RULES
        for p in POLICIES
        for c in (1, 2)
    ]
    rows += [
        {
            "base": b,
            "rule": "risk_only",
            "policy": "risk_only",
            "scale": c,
            "identity": f"{b}-risk_only",
            "roundtrip_bps": 82 * c,
            "key": f"{b}-risk_only-{82 * c}",
        }
        for b in BASES
        for c in (1, 2)
    ]
    return rows + [
        {
            "base": b,
            "rule": "none",
            "policy": p,
            "scale": c,
            "identity": f"{b}-{p}",
            "roundtrip_bps": 82 * c,
            "key": f"{b}-{p}-{82 * c}",
        }
        for b in BASES
        for p in ("unscaled", "original")
        for c in (1, 2)
    ]


def contract():
    return {
        "version": VERSION,
        "budget": 44,
        "prior_debt": 3556,
        "features": FIELDS,
        "basket": BASKET,
        "horizon": HORIZON,
        "sample_grid": "global2022_index_mod5=0;nextopen_to_open6;nooverlap",
        "fit": "annual2022prefix;label_maturity_plus5embargo;min30;standardized_ridge_lambda1",
        "rules": "mu/(10*qbar),mu/(10*qhat);qfloor=max(1e-8,.1*qbar);clip.25to1;nearest.25",
        "controls": "training_mean_exposure,20session_lag,rotated_training_targets,risk_only,unscaled,original",
        "exposure_clock": "execution_index1mod5;previous_session_features;continuous_no_year_reset",
        "costs": [82, 164],
        "capital_cny": 3_000_000,
        "cash_return": 0,
        "scope": "reused2023-24;train2022;no2025/26",
        "validated_alpha": False,
    }


def stages():
    return tuple(
        FitStage(str(y), "2022-01-01", f"{y - 1}-12-31", f"{y}-01-01", f"{y}-12-31")
        for y in (2023, 2024)
    )


def market_states(days):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered nonempty calendar required")
    previous, rows = {}, []
    for i, day in enumerate(days):
        bars = {b.instrument: b for b in day.bars}
        current, eligible = {}, {}
        for n, f in day.features.items():
            if n not in bars or not all(k in f and math.isfinite(f[k]) for k in RISK):
                continue
            close = bars[n].close_price
            if not math.isfinite(close) or close <= 0:
                continue
            current[n] = close
            if n in previous:
                eligible[n] = {**{k: f[k] for k in RISK}, "return1": close / previous[n] - 1}
        previous = current
        names = sorted(eligible)
        row = {
            "date": day.date,
            "index": i,
            "eligible": len(names),
            "available": len(names) >= BASKET,
        }
        if row["available"]:
            returns = [eligible[n]["return1"] for n in names]
            mean = sum(returns) / len(names)
            row["x"] = [
                sum(eligible[n]["ret_20"] > 0 for n in names) / len(names),
                sum(eligible[n]["ret_20"] for n in names) / len(names),
                sum(eligible[n]["volatility_20"] for n in names) / len(names),
                math.sqrt(sum((r - mean) ** 2 for r in returns) / len(names)),
            ]
            row["basket"] = sorted(names, key=lambda n: (eligible[n]["volatility_20"], n))[:BASKET]
        else:
            row.update(x=None, basket=[])
        rows.append(row)
    return rows


def proxy_labels(days, states, evidence=lambda row: None):
    if [d.date for d in days] != [s["date"] for s in states]:
        raise ValueError("state/calendar mismatch")
    bars = [{b.instrument: b for b in d.bars} for d in days]
    result = []
    for i, state in enumerate(states):
        end = i + HORIZON + 1
        if (
            i % HORIZON
            or not state["available"]
            or end >= len(days)
            or days[end].date >= "2024-01-01"
        ):
            continue
        names = state["basket"]
        if len(names) != BASKET or len(set(names)) != BASKET:
            raise ValueError("exact asof basket required")
        total, entries, fresh = 0.0, 0, 0
        for n in names:
            entry = bars[i + 1].get(n)
            op = entry.open_price if entry is not None else None
            endpoint, mark_date = None, None
            if op is not None:
                entries += 1
                endpoint, mark_date = op, days[i + 1].date
                for j in range(i + 1, end):
                    if n in bars[j]:
                        endpoint, mark_date = bars[j][n].close_price, days[j].date
                if n in bars[end]:
                    endpoint, mark_date = bars[end][n].open_price, days[end].date
                    fresh += 1
            r = endpoint / op - 1 if op is not None else 0.0
            if not math.isfinite(r):
                raise ValueError("nonfinite proxy return")
            total += r / BASKET
            evidence(
                {
                    "signal_date": state["date"],
                    "instrument": n,
                    "entry_date": days[i + 1].date,
                    "label_end": days[end].date,
                    "entry_price": op,
                    "end_mark": endpoint,
                    "mark_date": mark_date,
                    "return": r,
                }
            )
        result.append(
            {
                "date": state["date"],
                "entry_date": days[i + 1].date,
                "label_end": days[end].date,
                "x": state["x"],
                "return": total,
                "entries": entries,
                "fresh": fresh,
                "supported": entries >= 0.95 * BASKET and fresh >= 0.95 * entries,
            }
        )
    return result


def quantize(value):
    if not math.isfinite(value):
        raise ValueError("nonfinite exposure")
    return math.floor(min(1.0, max(0.25, value)) * 4 + 0.5) / 4


def predict(model, x, rule):
    if (
        rule not in RULES + ("risk_only",)
        or len(x) != len(FIELDS)
        or not all(map(math.isfinite, x))
    ):
        raise ValueError("registered rule and finite features required")
    z = (np.asarray(x) - np.asarray(model["center"])) / np.asarray(model["scale"])
    mu = model["mean_return"] + float(z @ np.asarray(model["beta_return"]))
    q = model["mean_second"] + float(z @ np.asarray(model["beta_second"]))
    numerator = model["mean_return"] if rule == "risk_only" else mu
    denominator = model["mean_second"] if rule == "mean" else q
    return quantize(numerator / (10 * max(model["second_floor"], denominator)))


def fit_model(rows, calendar, year, shuffled=False):
    if year not in (2023, 2024) or calendar != sorted(set(calendar)):
        raise ValueError("registered year and calendar required")
    prefix = [d for d in calendar if "2022-01-01" <= d < f"{year}-01-01"]
    if len(prefix) <= 5:
        raise ValueError("insufficient training calendar")
    cutoff = prefix[-6]
    train = [
        r
        for r in rows
        if r["supported"]
        and "2022-01-01" <= r["date"] < r["entry_date"] <= r["label_end"] <= cutoff
    ]
    if len(train) < MIN_TRAIN or [r["date"] for r in train] != sorted({r["date"] for r in train}):
        raise ValueError("insufficient or unordered actual training labels")
    if any(a["label_end"] > b["entry_date"] for a, b in pairwise(train)):
        raise ValueError("overlapping training returns")
    x = np.asarray([r["x"] for r in train], dtype=float)
    y = np.asarray([r["return"] for r in train], dtype=float)
    if x.shape != (len(train), len(FIELDS)) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("invalid training numbers")
    shift = len(y) // 3 if shuffled else 0
    assigned = np.roll(y, shift)
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (x - center) / scale
    matrix = z.T @ z + len(x) * np.eye(len(FIELDS))
    mu, qbar = float(assigned.mean()), float((assigned**2).mean())
    model = {
        "year": year,
        "fit_cutoff": cutoff,
        "maximum_label_end": max(r["label_end"] for r in train),
        "training_signal_sessions": [r["date"] for r in train],
        "training_signal_dates": len(train),
        "training_rows_sha256": sha256_json(train),
        "shuffled": bool(shuffled),
        "rotation": shift,
        "assigned_label_dates": [
            train[(i - shift) % len(train)]["date"] for i in range(len(train))
        ],
        "center": center.tolist(),
        "scale": scale.tolist(),
        "mean_return": mu,
        "mean_second": qbar,
        "second_floor": max(1e-8, 0.1 * qbar),
        "beta_return": np.linalg.solve(matrix, z.T @ (assigned - mu)).tolist(),
        "beta_second": np.linalg.solve(matrix, z.T @ (assigned**2 - qbar)).tolist(),
    }
    model["training_mean_exposure"] = {
        rule: sum(predict(model, r["x"], rule) for r in train) / len(train)
        for rule in RULES + ("risk_only",)
    }
    return model


def daily_predictions(registry, tid, states, calendar, models, paths):
    if [r["date"] for r in states] != calendar:
        raise ValueError("prediction calendar mismatch")
    window = [(i, d) for i, d in enumerate(calendar) if d >= "2023-01-01"]
    out = {}
    for j, (i, dt) in enumerate(window):
        if j == 0:
            continue
        signal = states[i - 1]
        model, path = models[int(dt[:4])], paths[int(dt[:4])]
        # At the first session of a new year the preceding signal may belong to
        # the old year; the new fit cutoff is embargoed, not the calendar year end.
        registry.assert_prediction_fit(
            tid, model=model, artifact_path=path, prediction_date=dt, signal_date=signal["date"]
        )
        out[dt] = {
            "signal_date": signal["date"],
            "available": signal["available"],
            **{
                rule: predict(model, signal["x"], rule) if signal["available"] else 0.25
                for rule in RULES + ("risk_only",)
            },
            "training_mean": model["training_mean_exposure"],
        }
    return out


def overlay_targets(base, predictions, rule, policy):
    if rule not in RULES + ("risk_only",) or policy not in POLICIES + ("risk_only",):
        raise ValueError("unregistered overlay")
    if not base or any(a.trade_date >= b.trade_date for a, b in pairwise(base)):
        raise ValueError("ordered base required")
    live, allocation, targets, evidence = {}, 1.0, [], []
    for i, target in enumerate(base):
        refresh = i >= 1 and (i - 1) % 5 == 0
        if target.rebalance:
            live = dict(target.weights)
        for name in target.forced_exits:
            live.pop(name, None)
        if refresh:
            p = predictions[target.trade_date]
            if p["signal_date"] >= target.trade_date:
                raise ValueError("signal must precede execution")
            if policy == "fixed":
                allocation = p["training_mean"][rule]
            elif policy == "lag20":
                lag = predictions.get(base[i - 20].trade_date) if i >= 20 else None
                allocation = lag[rule] if lag is not None else p["training_mean"][rule]
            else:
                allocation = p[rule]
        if not math.isfinite(allocation) or not 0.25 <= allocation <= 1:
            raise ValueError("invalid bounded exposure")
        rebalance = target.rebalance or refresh
        weights = {n: w * allocation for n, w in live.items()} if rebalance else {}
        if (
            any(not math.isfinite(w) or w < 0 for w in weights.values())
            or sum(weights.values()) > 1 + 1e-10
        ):
            raise ValueError("invalid base exposure")
        decided = f"{base[i - 1].trade_date}T23:59:59+08:00" if i else target.decided_at
        targets.append(replace(target, weights=weights, rebalance=rebalance, decided_at=decided))
        evidence.append(
            {
                "date": target.trade_date,
                "allocation": allocation,
                "refresh": refresh,
                "base_weight": sum(live.values()),
                "target_weight": sum(weights.values()),
            }
        )
    return tuple(targets), evidence


def screen(account, controls, states):
    gates = economic_screen(account, controls)
    for year in ("2023", "2024"):
        rows = [r for r in states if r["date"].startswith(year)]
        gates[f"state_coverage_{year}"] = (
            bool(rows) and sum(r["available"] for r in rows) / len(rows) >= 0.95
        )
    return gates
