"""Three predeclared path mechanisms in an as-of low-risk foundation."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import replace
from itertools import pairwise

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.evaluation import average_ranks

from .calendar_robustness import PHASES, combine_sleeves
from .residual_mechanisms import EMBARGO_SESSIONS, HORIZON, HURDLE, ResidualFit, dot

VERSION = "11.11.0"
MECHANISMS = ("flow_consistency", "auction_tail_balance", "chip_path_efficiency")
POLICIES = MECHANISMS + ("stable_lowrisk", "lowvol")
SOURCE_FIELDS = ("net_inflow_ratio", "auction_return", "concentration")
RISK_FIELDS = ("volatility_20", "ret_20", "liquidity")
LOOKBACK, LOWRISK_SIZE = 20, 200


def contract():
    return {
        "mechanisms": list(MECHANISMS),
        "source_fields": list(SOURCE_FIELDS),
        "formulas": {
            "flow_consistency": "mean(sign(flow20))*abs(sum(flow20))/sum(abs(flow20));zero_if_all_zero",
            "auction_tail_balance": "sum(auction20**3)/sum(abs(auction20)**3);zero_if_all_zero",
            "chip_path_efficiency": "(width_t-width_t19)/sum(abs(diff(width20)));zero_if_constant",
        },
        "coverage": "20consecutive_global_sessions;all3sources_and_current3riskfields_finite;no_fill",
        "pool": "lowest200vol20_asof_within_common_coverage;ties_by_instrument",
        "nuisance": "intercept+centered_cross_sectional_ranks(vol20,ret20,ADV)within_lowrisk200",
        "fit": "2023on2022;2024on2022-2023;prefix_before_labels;5session_embargo;stride5;ridge0.01",
        "label": "next_open_to20session_exit;missing_entry_excluded;missing_exit=-100%",
        "allocation": "keep_previous_desired_names_in_lowrisk200;fill_lowvol;max40_at2.5%;then_incremental_swaps",
        "hurdle_return": HURDLE,
        "calendar": "four_fixed_0_5_10_15_cohorts_one_continuous_netted_account",
        "costs_roundtrip_bps": [41, 82, 102],
        "capital_cny": 3_000_000,
        "controls": ["identical_policy_without_active_swaps", "lowvol_top40_buffer10"],
        "native_fit_stages": True,
        "economic_screen": {
            "costs": [82, 102],
            "both_years_positive": True,
            "sharpe_min": 0.7,
            "drawdown_floor": -0.25,
            "total_increment_vs_each_control_min": 0.03,
            "annual_increment_vs_lowvol_floor": -0.05,
        },
        "exposure": "reused2022-2024;2023and2024development;no2025/2026",
        "validated_alpha": False,
    }


def path_values(history):
    if len(history) != LOOKBACK or not all(math.isfinite(v) for row in history for v in row):
        raise ValueError("twenty finite consecutive observations required")
    flow, auction, chip = (list(values) for values in zip(*history, strict=True))
    flow_abs = sum(abs(v) for v in flow)
    # Scale before cubing to avoid overflow; ratio is invariant to positive scale.
    scale = max(abs(v) for v in auction)
    cubes = [(v / scale) ** 3 for v in auction] if scale else [0.0] * LOOKBACK
    auction_abs = sum(abs(v) for v in cubes)
    path = sum(abs(b - a) for a, b in pairwise(chip))
    values = (
        (sum((v > 0) - (v < 0) for v in flow) / LOOKBACK * abs(sum(flow)) / flow_abs)
        if flow_abs
        else 0.0,
        sum(cubes) / auction_abs if auction_abs else 0.0,
        (chip[-1] - chip[0]) / path if path else 0.0,
    )
    if not all(math.isfinite(v) and abs(v) <= 1 + 1e-12 for v in values):
        raise ValueError("invalid temporal feature")
    return dict(zip(MECHANISMS, values, strict=True))


def temporal_days(days):
    """As-of transformation, no labels; return only the low-risk pool, retaining all bars."""
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered nonempty dates required")
    histories, last_seen, result, coverage = {}, {}, [], []
    for i, day in enumerate(days):
        values = {}
        for n, f in day.features.items():
            if not all(k in f and math.isfinite(f[k]) for k in SOURCE_FIELDS):
                histories.pop(n, None)
                last_seen.pop(n, None)
                continue
            if last_seen.get(n) != i - 1:
                histories[n] = deque(maxlen=LOOKBACK)
            history = histories[n]
            history.append(tuple(f[k] for k in SOURCE_FIELDS))
            last_seen[n] = i
            if len(history) == LOOKBACK and all(
                k in f and math.isfinite(f[k]) for k in RISK_FIELDS
            ):
                values[n] = {**{k: f[k] for k in RISK_FIELDS}, **path_values(history)}
        ordered = sorted(values, key=lambda n: (values[n]["volatility_20"], n))[:LOWRISK_SIZE]
        result.append(replace(day, features={n: values[n] for n in ordered}))
        coverage.append({"date": day.date, "common": len(values), "lowrisk": len(ordered)})
    return tuple(result), coverage


def ranked_rows(features):
    names = sorted(features)
    if any(
        not all(
            k in features[n] and math.isfinite(features[n][k]) for k in RISK_FIELDS + MECHANISMS
        )
        for n in names
    ):
        raise ValueError("finite temporal pool required")
    if len(names) > LOWRISK_SIZE:
        raise ValueError("pool exceeds fixed low-risk limit")
    ranks = {
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
        for k in RISK_FIELDS + MECHANISMS
    }
    return {
        n: {
            "x": [1.0, *(ranks[k][n] for k in RISK_FIELDS)],
            "z": {k: ranks[k][n] for k in MECHANISMS},
            "vol": ranks["volatility_20"][n],
        }
        for n in names
    }


def fit_year(days, year, cache):
    if year not in (2023, 2024) or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("registered year and ordered dates required")
    prefix = tuple(d for d in days if "2022-01-01" <= d.date < f"{year}-01-01")[:-EMBARGO_SESSIONS]
    if len(prefix) <= HORIZON + 1:
        raise ValueError("insufficient training prefix")
    fits = {m: ResidualFit() for m in MECHANISMS}
    sessions, label_end = [], ""
    missing_entry = missing_exit = 0
    for i in range(0, len(prefix) - HORIZON - 1, 5):
        signal = prefix[i]
        if signal.date not in cache:
            cache[signal.date] = ranked_rows(signal.features)
        entry = {b.instrument: b.open_price for b in prefix[i + 1].bars}
        exit_prices = {b.instrument: b.open_price for b in prefix[i + HORIZON + 1].bars}
        accepted = 0
        for n, row in cache[signal.date].items():
            if n not in entry or not math.isfinite(entry[n]) or entry[n] <= 0:
                missing_entry += 1
                continue
            if n not in exit_prices:
                y = -1.0
                missing_exit += 1
            else:
                y = exit_prices[n] / entry[n] - 1
            for m, fit in fits.items():
                fit.add(row["x"], row["z"][m], y)
            accepted += 1
        if accepted:
            sessions.append(signal.date)
            label_end = prefix[i + HORIZON + 1].date
    return {
        "year": year,
        "fit_cutoff": prefix[-1].date,
        "maximum_label_end": label_end,
        "training_signal_sessions": sessions,
        "training_signal_dates": len(sessions),
        "missing_entry_excluded": missing_entry,
        "missing_exit_imputed_loss": missing_exit,
        "models": {m: fit.finish() for m, fit in fits.items()},
    }


def select(rows, previous, policy, model=None):
    if policy not in POLICIES:
        raise ValueError("unregistered policy")
    order = sorted(rows, key=lambda n: (rows[n]["vol"], n))
    retainable = order[:50] if policy == "lowvol" else order
    current = [n for n in retainable if n in previous][:40]
    current += [n for n in order if n not in current][: 40 - len(current)]
    swaps = 0
    if policy in MECHANISMS:
        scores = {
            n: model["slope"] * (row["z"][policy] - dot(row["x"], model["nuisance_z"]))
            for n, row in rows.items()
        }
        if not all(math.isfinite(v) for v in scores.values()):
            raise ValueError("finite predictions required")
        for n in sorted(rows, key=lambda n: (-scores[n], n)):
            if n in current or not current:
                continue
            worst = min(current, key=lambda n: (scores[n], n))
            if scores[n] - scores[worst] > HURDLE:
                current.remove(worst)
                current.append(n)
                swaps += 1
    return tuple(sorted(current)), swaps


def targets_for(registry, tid, days, models, policy, model_paths, cache):
    if policy not in POLICIES or not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("registered policy and ordered dates required")
    lineage = registry.fit_lineage(tid)
    if bool(lineage["stages"]) != (policy in MECHANISMS):
        raise ValueError("native fitted or explicit unfitted contract required")
    # Validate all actual models before feature values are read for target construction.
    if policy in MECHANISMS:
        for previous, day in pairwise(days):
            year = int(day.date[:4])
            registry.assert_prediction_fit(
                tid,
                model=models[year],
                artifact_path=model_paths[year],
                prediction_date=day.date,
                signal_date=previous.date,
            )
    sleeves, diagnostics = [], []
    for phase in PHASES:
        previous, targets = (), []
        for i, day in enumerate(days):
            signal = days[i - 1] if i else None
            rebalance = i >= phase + 1 and (i - phase - 1) % HORIZON == 0
            weights = {}
            if rebalance:
                if signal.date not in cache:
                    cache[signal.date] = ranked_rows(signal.features)
                rows = cache[signal.date]
                model = (
                    models[int(day.date[:4])]["models"][policy] if policy in MECHANISMS else None
                )
                previous, swaps = select(rows, previous, policy, model)
                weights = {n: 0.025 for n in previous}
                diagnostics.append(
                    {
                        "date": signal.date,
                        "phase": phase,
                        "matched": len(rows),
                        "selected": len(previous),
                        "hurdle_replacements": swaps,
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
    return combine_sleeves(sleeves), diagnostics


def plans():
    return [{"kind": "fit", "policy": m, "year": y} for y in (2023, 2024) for m in MECHANISMS] + [
        {"kind": "account", "policy": p, "cost_bps": c} for p in POLICIES for c in (41, 82, 102)
    ]
