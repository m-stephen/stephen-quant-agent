"""Predeclared response diagnostics, deliberately not a trading-account simulator."""

from __future__ import annotations

import math
from itertools import pairwise

from .risk_stratified import GROUPS, MECHANISMS, POLICIES, cells, scores
from .search_power_dsl import sha256_json

VERSION = "11.15.0"
READOUTS = POLICIES + ("cell_equal_weight",)
LABELS = ("before_entry", "same_day", "open_1", "open_5", "open_20")
FIELDS = (
    "volatility_20",
    "liquidity",
    "ret_20",
    "flow_consistency",
    "auction_tail_balance",
    "chip_path_efficiency",
)


def plans():
    return [
        {"key": f"{g}-{p}-{label}", "group": g, "policy": p, "label": label}
        for g in GROUPS
        for p in READOUTS
        for label in LABELS
    ]


def contract():
    return {
        "version": VERSION,
        "native_fit_stages": [],
        "raw_debt_before": 3366,
        "reserved_trials": 90,
        "scope": "reused2023-2024;2022warmup;no2025/2026",
        "selection": "inherited asof risk cells;daily top10 per cell,no buffer;0.025 each",
        "cell_equal_weight": "0.25 per nonempty cell,divided among all asof names",
        "direction": "unchanged V11.14,including constant hash control",
        "label_offsets": {
            "before_entry": [0, "close", 1, "open"],
            "same_day": [1, "open", 1, "close"],
            "open_1": [1, "open", 2, "open"],
            "open_5": [1, "open", 6, "open"],
            "open_20": [1, "open", 21, "open"],
        },
        "maturity": "all labels share signal dates with t+21 inside2024;global calendar",
        "missing": "do not change membership;missing price contributes0;report missing weight",
        "stress": "open horizons only;unbuyable/missing entry cash0;unavailable exit loss100%",
        "aggregation": "fixed unit-notional weights;equal signal dates,year of signal;not compounded",
        "not_tradable": ["before_entry", "same_day"],
        "dependencies": "overlapping stocks/dates/horizons;no independent sample count or Sharpe",
        "strong_response": "both years:mean>0.0164,each3control gap>=0.003,coverage>=0.99,entry>=0.98,stress>0",
        "screen_limit": "sufficient reason for a new execution study,not a necessary alpha condition",
        "validated_alpha": False,
    }


def mature_indices(days):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("ordered nonempty calendar required")
    if any(d.date >= "2025-01-01" for d in days):
        raise ValueError("restricted calendar")
    return tuple(i for i in range(len(days) - 21) if "2023-01-01" <= days[i].date <= "2024-12-31")


def require_contract(registry, tids):
    if set(tids) != {p["key"] for p in plans()}:
        raise ValueError("all90 native reservations required before values")
    for tid in tids.values():
        if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
            raise ValueError("explicit native no-fit required before values")


def memberships(features):
    """No price-label or next-session arguments are accepted here."""
    grouped = cells(features)
    result = {}
    for group, buckets in grouped.items():
        for cell, names in buckets.items():
            for name in names:
                result[name] = dict(group=group, cell=cell, **{f"w_{p}": 0.0 for p in READOUTS})
                result[name]["w_cell_equal_weight"] = 0.25 / len(names)
            for policy in POLICIES:
                values = scores(features, names, policy)
                chosen = sorted(names, key=lambda n: (-values[n], n))[:10]
                for name in chosen:
                    result[name][f"w_{policy}"] = 0.025
    return result


def endpoints(days, maps, i, name):
    result = {"date": days[i].date, "year": days[i].date[:4], "instrument": name}
    for tag, offset in (("signal", 0), ("entry", 1), ("exit1", 2), ("exit5", 6), ("exit20", 21)):
        result[f"{tag}_date"] = days[i + offset].date
        bar = maps[i + offset].get(name)
        result[f"{tag}_open"] = bar.open_price if bar else None
        result[f"{tag}_close"] = bar.close_price if bar else None
        result[f"{tag}_buy"] = int(bool(bar and bar.can_buy_open))
        result[f"{tag}_sell"] = int(bool(bar and bar.can_sell_open))
    return result


def response(row, label):
    if label not in LABELS:
        raise ValueError("unregistered label")
    if label == "before_entry":
        start, end = row["signal_close"], row["entry_open"]
        exit_tag = None
    elif label == "same_day":
        start, end = row["entry_open"], row["entry_close"]
        exit_tag = None
    else:
        exit_tag = "exit" + label.split("_")[1]
        start, end = row["entry_open"], row[f"{exit_tag}_open"]
    valid = all(v is not None and math.isfinite(v) and v > 0 for v in (start, end))
    value = end / start - 1 if valid else 0.0
    entry = row["entry_open"]
    can_enter = bool(entry is not None and math.isfinite(entry) and entry > 0 and row["entry_buy"])
    stress = None
    if exit_tag is not None:
        stress = (value if valid and row[f"{exit_tag}_sell"] else -1.0) if can_enter else 0.0
    return value, float(valid), float(can_enter), stress


def day_response(rows):
    """Equal-cell fixed-notional sufficient statistics; never reweight missing labels."""
    totals = {(g, p, l): [0.0] * 5 for g in GROUPS for p in READOUTS for l in LABELS}
    date, year = None, None
    for row in rows:
        if date is not None and row["date"] != date:
            raise ValueError("one signal date required")
        date, year = row["date"], row["year"]
        values = {l: response(row, l) for l in LABELS}
        for policy in READOUTS:
            weight = row[f"w_{policy}"]
            if weight < 0 or not math.isfinite(weight):
                raise ValueError("finite positive weights required")
            if not weight:
                continue
            for label, (value, valid, entry, stress) in values.items():
                acc = totals[row["group"], policy, label]
                for j, v in enumerate((1, value, valid, entry, stress or 0)):
                    acc[j] += weight * v
    if date is None:
        raise ValueError("no asof eligible names")
    result = []
    for (g, p, label), (weight, value, valid, entry, stress) in totals.items():
        if weight > 1.00000001:
            raise ValueError("overallocated diagnostic")
        result.append(
            {
                "date": date,
                "year": year,
                "group": g,
                "policy": p,
                "label": label,
                "weight": weight,
                "gross": value,
                "valid_weight": valid,
                "entry_weight": entry,
                "stress": stress if label.startswith("open_") else None,
            }
        )
    return result


def summarize(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault((row["group"], row["policy"], row["label"], row["year"]), []).append(row)
    result = []
    for (g, p, label, year), items in sorted(grouped.items()):
        n = len(items)

        def mean(k, items=items, n=n):
            return sum(r[k] for r in items) / n

        valid = mean("valid_weight")
        result.append(
            {
                "group": g,
                "policy": p,
                "label": label,
                "year": year,
                "dates": n,
                "mean_gross": mean("gross"),
                "mean_weight": mean("weight"),
                "valid_weight": valid,
                "entry_weight": mean("entry_weight"),
                "complete_price_mean": mean("gross") / valid if valid else None,
                "mean_stress": mean("stress") if label.startswith("open_") else None,
            }
        )
    return result


def strong_responses(rows):
    lookup = {(r["group"], r["policy"], r["label"], r["year"]): r for r in rows}
    result = {}
    for group in GROUPS:
        for policy in MECHANISMS:
            for label in LABELS[2:]:
                checks = []
                for year in ("2023", "2024"):
                    r = lookup.get((group, policy, label, year))
                    controls = [
                        lookup.get((group, p, label, year))
                        for p in ("hash", "price_reversal", "cell_equal_weight")
                    ]
                    checks.append(
                        bool(
                            r
                            and all(controls)
                            and r["mean_gross"] > 0.0164
                            and r["valid_weight"] >= 0.99
                            and r["entry_weight"] >= 0.98
                            and r["mean_stress"] > 0
                            and all(r["mean_gross"] - c["mean_gross"] >= 0.003 for c in controls)
                        )
                    )
                result[f"{group}-{policy}-{label}"] = all(checks)
    return result
