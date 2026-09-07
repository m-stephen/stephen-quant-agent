"""Train-only statistical peers, not economic links or a causal diffusion model."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import replace
from itertools import pairwise

import numpy as np

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.integrity.fit_lineage import UnsupervisedFitStage

from .calendar_robustness import PHASES, combine_sleeves
from .risk_stratified import GROUPS
from .risk_stratified import screen as economic_screen

VERSION = "11.17.0"
SIGNALS = ("price", "flow")
POLICIES = ("peer", "own", "shuffle", "hash")
RISK = ("volatility_20", "liquidity", "ret_20")
MIN_OBS, DEGREE, MIN_PEERS, MIN_CORR = 120, 10, 8, 0.15


def contract():
    return {
        "version": VERSION,
        "graph": "train_prefix_minus5sessions;demeaned_daily_returns;pairwise_Pearson120;top10_positive>=0.15",
        "shuffle": "conjugated_node_permutation_within12_training_end_risk_cells;fixedSHA184",
        "signals": "peer_weighted_price5_or_mean_flow5_minus_own;same_support_min8of10peers_each_graph",
        "controls": "own_negative,shuffle_gap,stable_hash;common_cell_gap_equals_own_ordering",
        "portfolio": "3strata_separate;4cells_x10;retain_top13;4phases0/5/10/15;20sessions;target_changes",
        "costs": [82, 164],
        "capital_cny": 3_000_000,
        "screen": "both_years>0;SR>=0.7;DD>=-0.25;each_control_total_delta>=0.03;annual_delta>=-0.05",
        "coverage": "each_year_mean_receiver_ratio>=0.70;each_stratum>=40on95pct_signal_dates",
        "years": "2022fit/warmup;2023-2024reused_development;no2025/26",
        "budget": 50,
        "prior_debt": 3506,
        "validated_alpha": False,
    }


def plans():
    return [
        {
            "identity": f"{s}-{g}",
            "signal": s,
            "group": g,
            "policy": p,
            "scale": c,
            "roundtrip_bps": 82 * c,
            "key": f"{s}-{g}-{p}-{82 * c}",
        }
        for s in SIGNALS
        for g in GROUPS
        for p in POLICIES
        for c in (1, 2)
    ] + [
        {
            "identity": "anchor",
            "signal": "none",
            "group": "none",
            "policy": "lowvol",
            "scale": c,
            "roundtrip_bps": 82 * c,
            "key": f"anchor-lowvol-{82 * c}",
        }
        for c in (1, 2)
    ]


def stages():
    return tuple(
        UnsupervisedFitStage(str(y), "2022-01-01", f"{y - 1}-12-31", f"{y}-01-01", f"{y}-12-31")
        for y in (2023, 2024)
    )


def risk_cells(features):
    if any(not all(k in f and math.isfinite(f[k]) for k in RISK) for f in features.values()):
        raise ValueError("finite risk fields required")
    result = {g: {str(i): [] for i in range(4)} for g in GROUPS}
    ordered = sorted(features, key=lambda n: (features[n]["volatility_20"], n))
    groups = {g: [] for g in GROUPS}
    for i, n in enumerate(ordered):
        groups[GROUPS[3 * i // len(ordered)]].append(n)
    for g, names in groups.items():
        halves = (names[: (len(names) + 1) // 2], names[(len(names) + 1) // 2 :])
        for v, half in enumerate(halves):
            half = sorted(half, key=lambda n: (features[n]["liquidity"], n))
            for i, n in enumerate(half):
                result[g][str(2 * v + 2 * i // len(half))].append(n)
    return result


def peer_days(days, evidence=lambda row: None):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("nonempty ordered calendar required")
    last, histories, result = {}, {}, []
    for i, day in enumerate(days):
        bars = {b.instrument: b for b in day.bars}
        values = {}
        for n, f in day.features.items():
            if n not in bars or not all(k in f and math.isfinite(f[k]) for k in RISK):
                continue
            close = bars[n].close_price
            prior = last.get(n)
            last[n] = (i, close)
            if prior is None or prior[0] != i - 1 or close <= 0 or prior[1] <= 0:
                histories.pop(n, None)
                continue
            r = close / prior[1] - 1
            if not math.isfinite(r):
                raise ValueError("nonfinite adjacent price return")
            row = {**{k: f[k] for k in RISK}, "return1": r}
            flow = f.get("net_inflow_ratio")
            if flow is None or not math.isfinite(flow):
                histories.pop(n, None)
            else:
                hist = histories.setdefault(n, deque(maxlen=5))
                hist.append((r, flow))
                if len(hist) == 5:
                    row.update(
                        price=math.prod(1 + x[0] for x in hist) - 1,
                        flow=sum(x[1] for x in hist) / 5,
                    )
            values[n] = row
            evidence(
                {
                    "date": day.date,
                    "instrument": n,
                    **row,
                    "price": row.get("price"),
                    "flow": row.get("flow"),
                }
            )
        result.append(replace(day, features=values))
    return tuple(result)


def fit_graph(days, year):
    if year not in (2023, 2024) or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("registered year and ordered dates required")
    prefix = tuple(d for d in days if "2022-01-01" <= d.date < f"{year}-01-01")[:-5]
    if len(prefix) < MIN_OBS:
        raise ValueError("insufficient graph training history")
    counts, last_risk = {}, {}
    for d in prefix:
        for n, f in d.features.items():
            if not math.isfinite(f["return1"]):
                raise ValueError("nonfinite graph input")
            counts[n] = counts.get(n, 0) + 1
            last_risk[n] = {k: f[k] for k in RISK}
    names = sorted(n for n, count in counts.items() if count >= MIN_OBS)
    index = {n: i for i, n in enumerate(names)}
    # Center using all eligible names on each day, not future-surviving graph nodes.
    values = np.zeros((len(names), len(prefix)), dtype=np.float64)
    mask = np.zeros_like(values)
    observed = []
    for j, d in enumerate(prefix):
        if not d.features:
            continue
        mean = sum(f["return1"] for f in d.features.values()) / len(d.features)
        used = False
        for n, f in d.features.items():
            if n in index:
                values[index[n], j] = f["return1"] - mean
                mask[index[n], j] = 1
                used = True
        if used:
            observed.append(d.date)
    if not names or not observed:
        raise ValueError("no eligible training nodes")
    squares = values * values
    edges, overlap_evidence = {}, {}
    # Bounded receiver blocks: no N*N*T tensor or materialized full matrices.
    for start in range(0, len(names), 128):
        stop = min(start + 128, len(names))
        m, x = mask[start:stop], values[start:stop]
        count = m @ mask.T
        total_x, total_y = x @ mask.T, m @ values.T
        with np.errstate(divide="ignore", invalid="ignore"):
            numerator = x @ values.T - total_x * total_y / count
            var_x = squares[start:stop] @ mask.T - total_x * total_x / count
            var_y = m @ squares.T - total_y * total_y / count
            corr = numerator / np.sqrt(np.maximum(var_x, 0) * np.maximum(var_y, 0))
        for local, i in enumerate(range(start, stop)):
            choices = [
                j
                for j in range(len(names))
                if j != i
                and count[local, j] >= MIN_OBS
                and math.isfinite(corr[local, j])
                and corr[local, j] >= MIN_CORR
            ]
            chosen = sorted(choices, key=lambda j: (-corr[local, j], names[j]))[:DEGREE]
            if len(chosen) == DEGREE:
                edges[names[i]] = [[names[j], float(min(corr[local, j], 1.0))] for j in chosen]
                overlap_evidence[names[i]] = [int(count[local, j]) for j in chosen]
    buckets = risk_cells({n: last_risk[n] for n in names})
    permutation = {}
    for cells in buckets.values():
        for members in cells.values():
            old = sorted(members)
            new = sorted(
                members,
                key=lambda n: (hashlib.sha256(f"v11.17:184:{year}:{n}".encode()).hexdigest(), n),
            )
            permutation.update(zip(old, new, strict=True))
    shuffled = {
        permutation[n]: [[permutation[p], w] for p, w in peers] for n, peers in edges.items()
    }
    return {
        "fit_kind": "unsupervised",
        "year": year,
        "fit_cutoff": prefix[-1].date,
        "maximum_observation_at": observed[-1],
        "training_observation_sessions": observed,
        "training_observation_dates": len(observed),
        "nodes": names,
        "graph": edges,
        "overlaps": overlap_evidence,
        "permutation": permutation,
        "shuffle": shuffled,
        "training_counts": {n: counts[n] for n in names},
        "training_risk": {n: last_risk[n] for n in names},
    }


def signal_rows(features, model):
    current = {
        n: f
        for n, f in features.items()
        if all(k in f and math.isfinite(f[k]) for k in SIGNALS + RISK)
    }
    result = {}
    for n in sorted(current.keys() & model["graph"].keys() & model["shuffle"].keys()):
        peer_values = {}
        for policy, graph_key in (("peer", "graph"), ("shuffle", "shuffle")):
            available = [(p, w) for p, w in model[graph_key][n] if p in current]
            if len(available) < MIN_PEERS:
                break
            total = sum(w for _, w in available)
            if total <= 0:
                raise ValueError("nonpositive graph weights")
            for s in SIGNALS:
                peer_values[f"{s}_{policy}"] = (
                    sum(current[p][s] * w for p, w in available) / total - current[n][s]
                )
        if len(peer_values) == 4:
            result[n] = {**current[n], **peer_values}
    return result, len(current)


def choose(features, buckets, prior, signal, policy):
    if signal not in SIGNALS or policy not in POLICIES:
        raise ValueError("undeclared signal or policy")
    chosen = []
    for names in buckets.values():

        def score(n):
            if policy == "hash":
                return int(hashlib.sha256(f"v11.17:184:{n}".encode()).hexdigest(), 16)
            return -features[n][signal] if policy == "own" else features[n][f"{signal}_{policy}"]

        ordered = sorted(names, key=lambda n: (-score(n), n))
        keep = [n for n in ordered[:13] if n in prior][:10]
        chosen.extend(keep + [n for n in ordered if n not in keep][: 10 - len(keep)])
    return tuple(sorted(chosen))


def prepared_signals(registry, tid, days, models, paths):
    result, diagnostics = {}, []
    for signal, execution in pairwise(days):
        if execution.date < "2023-01-01":
            continue
        year = int(execution.date[:4])
        registry.assert_prediction_fit(
            tid,
            model=models[year],
            artifact_path=paths[year],
            prediction_date=execution.date,
            signal_date=signal.date,
        )
        rows, denominator = signal_rows(signal.features, models[year])
        grouped = risk_cells(rows)
        result[execution.date] = (signal.date, rows, grouped)
        diagnostics.append(
            {
                "date": execution.date,
                "signal_date": signal.date,
                "eligible": denominator,
                "common": len(rows),
                "ratio": len(rows) / denominator if denominator else 0.0,
                **{g: sum(len(x) for x in grouped[g].values()) for g in GROUPS},
            }
        )
    return result, diagnostics


def targets_for(days, cache, group, signal, policy):
    window = tuple(d for d in days if d.date >= "2023-01-01")
    sleeves = []
    for phase in PHASES:
        previous, targets = (), []
        for i, day in enumerate(window):
            dt, rows, grouped = cache[day.date]
            # First deployment observation is Jan's first EOD, not a warmup position.
            rebalance = i >= phase + 1 and (i - phase - 1) % 20 == 0
            weights = {}
            if rebalance:
                previous = choose(rows, grouped[group], previous, signal, policy)
                weights = {n: 0.025 for n in previous}
            targets.append(TargetAllocation(day.date, f"{dt}T23:59:59+08:00", weights, rebalance))
        sleeves.append(tuple(targets))
    return combine_sleeves(sleeves)


def screen(candidate, controls, coverage):
    result = economic_screen(candidate, controls)
    for year in ("2023", "2024"):
        rows = [r for r in coverage if r["date"].startswith(year)]
        result[f"coverage_{year}"] = bool(rows) and sum(r["ratio"] for r in rows) / len(rows) >= 0.7
        result[f"stratum_size_{year}"] = (
            bool(rows) and sum(r[candidate["group"]] >= 40 for r in rows) / len(rows) >= 0.95
        )
    return result
