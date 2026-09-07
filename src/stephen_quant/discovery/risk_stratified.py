"""Predeclared, label-free mechanism ranks across the full as-of risk support.

This is a new hypothesis family, not a retuning of the V11.11 frozen allocation.
Same-day ranks are unfitted transforms. Cell quotas match broad risk/liquidity
support, not exact beta, industry, turnover or cash exposure.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import replace
from itertools import pairwise

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.evaluation import average_ranks

from .calendar_robustness import PHASES, combine_sleeves
from .search_power_dsl import sha256_json
from .temporal_increments import LOOKBACK, RISK_FIELDS, SOURCE_FIELDS, path_values

VERSION = "11.14.0"
GROUPS = ("low", "middle", "high")
MECHANISMS = ("flow_price_absorption", "quiet_accumulation", "auction_exhaustion")
CONTROLS = ("hash", "price_reversal")
POLICIES = MECHANISMS + CONTROLS
RANK_FIELDS = ("flow_consistency", "auction_tail_balance", "chip_path_efficiency", "ret_20")


def contract():
    return {
        "version": VERSION,
        "pool": "all asof ADV>=10m nonST history>=20;20consecutive source observations",
        "strata": "sort(vol20,instrument);floor(3*i/N) -> low,middle,high",
        "cells": "within each stratum:2 equal vol bins,each split into2 ADV bins;ties by name",
        "selection": "10names per cell;retain previous desired in top13;fill by score;no cross-cell filling",
        "formulas": {
            "flow_price_absorption": "rank(flow_consistency)*(1-rank(ret20))",
            "quiet_accumulation": "rank(flow_consistency)*(1-rank(chip_path_efficiency))",
            "auction_exhaustion": "(1-rank(auction_tail_balance))*(1-rank(ret20))",
        },
        "direction": "higher joint score;fixed before returns;no direction fitting",
        "rank": "average tie ranks/(cell_size+1),within contemporaneous cell",
        "controls": "same4cell quotas and retention:SHA256(v11.14:184:instrument);negative ret20",
        "matching_limit": "broad risk/liquidity cells only;not exact style,cash or turnover match",
        "calendar": "four fixed phases0,5,10,15;20session horizon;one netted continuous account",
        "targets": "2.5% per selected name per sleeve;no scaling sparse cells;next open execution",
        "execution": "legacy full_target;adjusted fractional units;not broker certified",
        "capital_cny": 3_000_000,
        "costs_roundtrip_bps": [82, 164],
        "scope": "reused2023-2024development;warmup2022;no2025/2026",
        "native_fit_stages": [],
        "reserved_accounts": 32,
        "trial_lower_bound_before": 3334,
        "screen": {
            "both_years_positive": True,
            "sharpe_min": 0.7,
            "max_drawdown_floor": -0.25,
            "total_increment_vs_each_control_min": 0.03,
            "annual_increment_vs_each_control_floor": -0.05,
            "comparators": [
                "same-stratum hash",
                "same-stratum price reversal",
                "original lowvol anchor",
            ],
            "both_costs_required": True,
        },
        "catalog_overlap": "reuses temporal primitives but replaces lowrisk200 linear swap hurdle with joint cell ranks across3strata;new family,not novel primitives",
        "validated_alpha": False,
    }


def plans():
    rows = [
        {"group": g, "policy": p, "scale": s, "roundtrip_bps": 82 * s, "key": f"{g}-{p}-{82 * s}"}
        for g in GROUPS
        for p in POLICIES
        for s in (1, 2)
    ]
    return rows + [
        {
            "group": "anchor",
            "policy": "lowvol",
            "scale": s,
            "roundtrip_bps": 82 * s,
            "key": f"anchor-lowvol-{82 * s}",
        }
        for s in (1, 2)
    ]


def mechanism_days(days):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered nonempty dates required")
    histories, last_seen, result, coverage = {}, {}, [], []
    for i, day in enumerate(days):
        values = {}
        for name, fields in day.features.items():
            if not all(k in fields and math.isfinite(fields[k]) for k in SOURCE_FIELDS):
                histories.pop(name, None)
                last_seen.pop(name, None)
                continue
            if last_seen.get(name) != i - 1:
                histories[name] = deque(maxlen=LOOKBACK)
            histories[name].append(tuple(fields[k] for k in SOURCE_FIELDS))
            last_seen[name] = i
            if len(histories[name]) == LOOKBACK and all(
                k in fields and math.isfinite(fields[k]) for k in RISK_FIELDS
            ):
                values[name] = {
                    **{k: fields[k] for k in RISK_FIELDS},
                    **path_values(histories[name]),
                }
        result.append(replace(day, features=values))
        coverage.append({"date": day.date, "common": len(values)})
    return tuple(result), coverage


def cells(features):
    if any(
        not all(k in f and math.isfinite(f[k]) for k in RISK_FIELDS + RANK_FIELDS)
        for f in features.values()
    ):
        raise ValueError("finite common features required")
    result = {g: {str(i): [] for i in range(4)} for g in GROUPS}
    ordered = sorted(features, key=lambda n: (features[n]["volatility_20"], n))
    groups = {g: [] for g in GROUPS}
    for i, name in enumerate(ordered):
        groups[GROUPS[3 * i // len(ordered)]].append(name)
    for group, names in groups.items():
        halves = (names[: (len(names) + 1) // 2], names[(len(names) + 1) // 2 :])
        for v, half in enumerate(halves):
            half = sorted(half, key=lambda n: (features[n]["liquidity"], n))
            for i, name in enumerate(half):
                result[group][str(2 * v + 2 * i // len(half))].append(name)
    return result


def scores(features, names, policy):
    if policy not in POLICIES:
        raise ValueError("unregistered policy")
    names = sorted(names)
    if policy == "hash":
        # Constant in time, so the control does not incur artificial daily re-randomization.
        return {n: int(hashlib.sha256(f"v11.14:184:{n}".encode()).hexdigest(), 16) for n in names}
    ranks = {
        k: dict(
            zip(
                names,
                (r / (len(names) + 1) for r in average_ranks([features[n][k] for n in names])),
                strict=True,
            )
        )
        for k in RANK_FIELDS
    }
    if policy == "price_reversal":
        return {n: 1 - ranks["ret_20"][n] for n in names}
    return {
        n: (
            ranks["flow_consistency"][n]
            if policy != "auction_exhaustion"
            else 1 - ranks["auction_tail_balance"][n]
        )
        * (1 - ranks["chip_path_efficiency" if policy == "quiet_accumulation" else "ret_20"][n])
        for n in names
    }


def select(features, grouped, previous, policy):
    if set(grouped) != {"0", "1", "2", "3"}:
        raise ValueError("four fixed cells required")
    all_names = [n for bucket in grouped.values() for n in bucket]
    if len(set(all_names)) != len(all_names):
        raise ValueError("disjoint cells required")
    selected, detail = [], []
    for cell, names in sorted(grouped.items()):
        values = scores(features, names, policy)
        ordered = sorted(names, key=lambda n: (-values[n], n))
        chosen = [n for n in ordered[:13] if n in previous][:10]
        chosen += [n for n in ordered if n not in chosen][: 10 - len(chosen)]
        selected.extend(chosen)
        detail.append({"cell": cell, "eligible": len(names), "selected": len(chosen)})
    return tuple(sorted(selected)), detail


def targets_for(registry, tid, days, group, policy, cache):
    if (
        group not in GROUPS
        or policy not in POLICIES
        or not days
        or any(a.date >= b.date for a, b in pairwise(days))
    ):
        raise ValueError("registered policy and ordered dates required")
    if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
        raise ValueError("explicit native no-fit contract required before values")
    sleeves, diagnostics = [], []
    for phase in PHASES:
        previous, targets = (), []
        for i, day in enumerate(days):
            signal = days[i - 1] if i else None
            rebalance = i >= phase + 1 and (i - phase - 1) % 20 == 0
            weights = {}
            if rebalance:
                if signal.date not in cache:
                    cache[signal.date] = cells(signal.features)
                grouped = cache[signal.date][group]
                chosen, detail = select(signal.features, grouped, previous, policy)
                diagnostics.append(
                    {
                        "date": signal.date,
                        "phase": phase,
                        "cells": detail,
                        "new_members": len(set(chosen) - set(previous)),
                        "selected": len(chosen),
                        "mean_volatility20": sum(
                            signal.features[n]["volatility_20"] for n in chosen
                        )
                        / len(chosen)
                        if chosen
                        else 0,
                        "mean_ADV_cny": sum(signal.features[n]["liquidity"] for n in chosen)
                        / len(chosen)
                        if chosen
                        else 0,
                    }
                )
                previous = chosen
                weights = {n: 0.025 for n in chosen}
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


def screen(candidate, controls):
    return {
        "accounts": candidate["audit"]["pass"] and all(c["audit"]["pass"] for c in controls),
        "both_years_positive": all(candidate["years"][y] > 0 for y in ("2023", "2024")),
        "sharpe": candidate["pooled_sharpe"] >= 0.7,
        "drawdown": candidate["metrics"]["max_drawdown"] >= -0.25,
        "total_increment": all(
            candidate["metrics"]["net_total_return"] - c["metrics"]["net_total_return"] >= 0.03
            for c in controls
        ),
        "annual_increment": all(
            candidate["years"][y] - c["years"][y] >= -0.05
            for c in controls
            for y in ("2023", "2024")
        ),
    }
