"""Finite, label-free ordered events; sparse allocations with matched clocks.

No return labels, fitted parameters, or future bars enter the scheduler. Histories
must be consecutive on the supplied global calendar, not merely consecutive rows
for an instrument. Vendor flow is a proxy, not observed order-book imbalance.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from dataclasses import replace
from itertools import pairwise, product

from stephen_quant.baseline.stateful import TargetAllocation

from .search_power_dsl import sha256_json

VERSION = "11.16.0"
STARTS = ("positive_flow_innovation", "negative_price_innovation")
CONFIRMS = ("quiet_positive_flow", "recovery_positive_flow")
POLICIES = ("event", "risk_hash", "confirm_only")
RISK = ("volatility_20", "liquidity", "ret_20")
LOOKBACK, COOLDOWN, HOLD, SLOTS = 20, 40, 20, 40


def contract():
    return {
        "version": VERSION,
        "raw_debt_before": 3456,
        "reserved_trials": 50,
        "native_fit_stages": [],
        "scope": "2022 warmup; reused2023-2024; no2025/2026",
        "sources": "EOD-available daily and net-flow; no optional-source coverage filter",
        "flow_z": "(current flow - mean(previous20))/sample_sd(previous20)",
        "price_z": "current adjusted-close simple return/sample_sd(previous20 returns)",
        "support": "asof base eligibility and20 preceding consecutive eligible observations; positive SDs",
        "sequence": "start[t-lag] AND confirm[t],false-to-true; lag1or3 global sessions",
        "cooldown": "40 sessions per qualifying trigger,including full-target rejection; no extension",
        "controls": "same admission,12 risk cells,expiry; exclude own targets and all qualifying events",
        "control_cooldown": "40 sessions from selected control admission signal",
        "risk_cells": "3 vol strata; each2 vol halves,then2 ADV halves; instrument breaks ties",
        "tie_break": "ascending SHA256(v11.16:184:identity:policy:instrument),constant across dates",
        "first_admission": "2023 signal; next open; no warmup triggers consume cooldown",
        "holding": "entry t+1; planned exit t+21; no forced end liquidation; no year reset",
        "allocation": "40 desired slots at0.025; unmatched/empty slots cash; no rescaling",
        "execution": "target_changes; unchanged holdings drift subject to existing per-name cap; retries",
        "anchor_execution": "original frozen lowvol targets with legacy full_target,byte-compare",
        "costs_bps": [82, 164],
        "capital_cny": 3_000_000,
        "limitations": "adjusted fractional shares,not physical lots/dividend accounting; timing/risk matching not exact exposure",
        "screen": "bothcosts:2positive years,SR>=.7,MDD>=-.25,each3control totalgap>=.03,annualgap>=-.05,50admissions/year,98%matched/year",
        "validated_alpha": False,
    }


def catalog():
    rows = []
    for start, confirm, lag in product(STARTS, CONFIRMS, (1, 3)):
        ast = {"start": start, "confirm": confirm, "lag": lag, "contract": contract()}
        rows.append(
            {"identity": f"{start}--{confirm}--lag{lag}", **ast, "sha256": sha256_json(ast)}
        )
    return rows


def plans():
    return [
        {
            "key": f"{a['identity']}-{p}-{82 * s}",
            "identity": a["identity"],
            "policy": p,
            "scale": s,
            "roundtrip_bps": 82 * s,
            "ast_sha256": a["sha256"],
        }
        for a, p, s in product(catalog(), POLICIES, (1, 2))
    ] + [
        {
            "key": f"anchor-lowvol-{82 * s}",
            "identity": "anchor",
            "policy": "lowvol",
            "scale": s,
            "roundtrip_bps": 82 * s,
            "ast_sha256": "original-frozen-card",
        }
        for s in (1, 2)
    ]


def require_contract(registry, tids):
    if set(tids) != {p["key"] for p in plans()} or len(set(tids.values())) != 50:
        raise ValueError("all50 distinct native reservations required before values")
    for tid in tids.values():
        if registry.fit_lineage(tid) != {"stages": [], "fits": [], "sha256": sha256_json([])}:
            raise ValueError("explicit native no-fit required before values")


def check_calendar(days):
    if not days or any(a.date >= b.date for a, b in pairwise(days)):
        raise ValueError("nonempty ordered unique calendar required")
    if any(d.date < "2022-01-01" or d.date >= "2025-01-01" for d in days):
        raise ValueError("restricted calendar")


def innovation_days(days, emit=None):
    """Emit every valid raw history row, including warmup; z fields may be null.

    Missing base eligibility resets the innovation history too (a conservative
    common-support choice). Previous adjusted close may come from a valid bar
    outside that eligibility pool but must be from the previous global session.
    """
    check_calendar(days)
    histories, last_seen, previous, result = {}, {}, {}, []
    for i, day in enumerate(days):
        current = {b.instrument: b.close_price for b in day.bars}
        values = {}
        for name, fields in sorted(day.features.items()):
            if not all(
                k in fields and math.isfinite(fields[k]) for k in (*RISK, "net_inflow_ratio")
            ):
                continue
            if (
                name not in previous
                or name not in current
                or previous[name] <= 0
                or current[name] <= 0
            ):
                continue
            r, flow = current[name] / previous[name] - 1, fields["net_inflow_ratio"]
            if not math.isfinite(r):
                continue
            if last_seen.get(name) != i - 1:
                histories[name] = deque(maxlen=LOOKBACK)
            history = histories[name]
            row = {
                "date": day.date,
                "index": i,
                "instrument": name,
                "close": current[name],
                "previous_close": previous[name],
                "price_return": r,
                "flow": flow,
                **{k: fields[k] for k in RISK},
                "flow_z": None,
                "price_z": None,
            }
            if len(history) == LOOKBACK:
                mf = math.fsum(x[0] for x in history) / LOOKBACK
                mr = math.fsum(x[1] for x in history) / LOOKBACK
                sf = math.sqrt(math.fsum((x[0] - mf) ** 2 for x in history) / (LOOKBACK - 1))
                sr = math.sqrt(math.fsum((x[1] - mr) ** 2 for x in history) / (LOOKBACK - 1))
                if sf > 0 and sr > 0:
                    row.update(flow_z=(flow - mf) / sf, price_z=r / sr)
                    if all(math.isfinite(row[k]) for k in ("flow_z", "price_z")):
                        values[name] = {k: row[k] for k in (*RISK, "flow", "flow_z", "price_z")}
                    else:
                        row.update(flow_z=None, price_z=None)
            if emit:
                emit(row)
            history.append((flow, r))
            last_seen[name] = i
        result.append(replace(day, features=values))
        previous = current
    return tuple(result)


def risk_cells(features):
    if any(not all(k in f and math.isfinite(f[k]) for k in RISK) for f in features.values()):
        raise ValueError("finite risk support required")
    names = sorted(features, key=lambda n: (features[n]["volatility_20"], n))
    groups = {g: [] for g in range(3)}
    for i, name in enumerate(names):
        groups[3 * i // len(names)].append(name)
    result = {}
    for g, ordered in groups.items():
        mid = (len(ordered) + 1) // 2
        for v, half in enumerate((ordered[:mid], ordered[mid:])):
            half = sorted(half, key=lambda n: (features[n]["liquidity"], n))
            for j, name in enumerate(half):
                result[name] = f"{g}:{v}:{2 * j // len(half)}"
    return result


def start_true(fields, atom):
    if atom == STARTS[0]:
        return fields["flow_z"] >= 2 and fields["flow"] > 0
    if atom == STARTS[1]:
        return fields["price_z"] <= -2
    raise ValueError("unregistered start")


def confirm_true(fields, atom):
    if atom == CONFIRMS[0]:
        return abs(fields["price_z"]) <= 0.5 and fields["flow"] > 0
    if atom == CONFIRMS[1]:
        return 0 <= fields["price_z"] <= 1 and fields["flow"] > 0
    raise ValueError("unregistered confirm")


def order_key(identity, policy, name):
    return hashlib.sha256(f"v11.16:184:{identity}:{policy}:{name}".encode()).hexdigest(), name


def schedules(days, ast, emit=None):
    """Use signal prefix only; return all three policies and event-source log.

    Target slots expire by planned clock independently of whether an order filled.
    The execution engine retains responsibility for blocked exits and pending buys.
    """
    check_calendar(days)
    if ast not in catalog():
        raise ValueError("unregistered AST")
    identity, lag = ast["identity"], ast["lag"]
    previous_hit, trigger_clock = set(), {}
    holdings = {p: {} for p in POLICIES}
    clocks = {p: {} for p in POLICIES[1:]}
    targets, admissions, counts = {p: [] for p in POLICIES}, [], []
    # Evaluate warmup conditions for edge detection, but no warmup admissions/clocks.
    for i, signal in enumerate(days):
        f = signal.features
        earlier = days[i - lag].features if i >= lag else {}
        hit = {
            n
            for n in f
            if n in earlier
            and start_true(earlier[n], ast["start"])
            and confirm_true(f[n], ast["confirm"])
        }
        rising = hit - previous_hit
        previous_hit = hit
        if signal.date < "2023-01-01" or i + 1 == len(days):
            continue
        trade = days[i + 1]
        if trade.date[:4] not in ("2023", "2024"):
            continue
        entry, expiry = i + 1, i + 1 + HOLD
        for policy in POLICIES:
            holdings[policy] = {n: e for n, e in holdings[policy].items() if e > entry}
        eligible = {n for n in rising if i - trigger_clock.get(n, -COOLDOWN) >= COOLDOWN}
        trigger_clock.update(dict.fromkeys(eligible, i))
        cells = risk_cells(f)
        chosen = sorted(
            eligible - set(holdings["event"]), key=lambda n: order_key(identity, "event", n)
        )[: SLOTS - len(holdings["event"])]
        matched = {p: 0 for p in POLICIES[1:]}
        for n in sorted(eligible):
            if emit:
                emit(
                    {
                        "identity": identity,
                        "index": i,
                        "date": signal.date,
                        "instrument": n,
                        "cell": cells[n],
                        "admitted": n in chosen,
                    }
                )
        for n in chosen:
            row = {
                "identity": identity,
                "signal_index": i,
                "signal_date": signal.date,
                "entry_index": entry,
                "entry_date": trade.date,
                "expiry_index": expiry,
                "event": n,
                "cell": cells[n],
            }
            holdings["event"][n] = expiry
            for policy in POLICIES[1:]:
                pool = [
                    m
                    for m in f
                    if cells[m] == cells[n]
                    and m not in eligible
                    and m not in holdings[policy]
                    and i - clocks[policy].get(m, -COOLDOWN) >= COOLDOWN
                    and (policy == "risk_hash" or confirm_true(f[m], ast["confirm"]))
                ]
                selected = min(pool, key=lambda m: order_key(identity, policy, m)) if pool else None
                row[policy] = selected
                if selected is not None:
                    holdings[policy][selected] = expiry
                    clocks[policy][selected] = i
                    matched[policy] += 1
            admissions.append(row)
        counts.append(
            {
                "date": signal.date,
                "entry_date": trade.date,
                "year": trade.date[:4],
                "eligible": len(f),
                "triggers": len(eligible),
                "admissions": len(chosen),
                **matched,
                "desired_names": {p: len(holdings[p]) for p in POLICIES},
            }
        )
        for policy in POLICIES:
            targets[policy].append(
                TargetAllocation(
                    trade.date,
                    signal.date + "T23:59:59+08:00",
                    {n: 1 / SLOTS for n in sorted(holdings[policy])},
                    True,
                )
            )
    # The first2023 trading day has no authorized2023 signal. Keep its capital cash.
    trading = [d for d in days if d.date >= "2023-01-01"]
    for policy in POLICIES:
        existing = {t.trade_date: t for t in targets[policy]}
        targets[policy] = tuple(
            existing.get(
                d.date,
                TargetAllocation(
                    d.date,
                    d.date + "T08:00:00+08:00",
                    {},
                    True,
                ),
            )
            for d in trading
        )
    return targets, admissions, counts


def screen(candidate, controls, counts):
    years = ("2023", "2024")
    if set(candidate["years"]) != set(years) or len(controls) != 3:
        raise ValueError("both years and all three controls required")
    stats = {
        y: {
            k: sum(d[k] for d in counts if d["year"] == y)
            for k in ("admissions", "risk_hash", "confirm_only")
        }
        for y in years
    }
    return {
        "accounts": all(r["audit"]["pass"] for r in [candidate, *controls]),
        "both_years_positive": all(candidate["years"][y] > 0 for y in years),
        "sharpe": candidate["pooled_sharpe"] >= 0.7,
        "drawdown": candidate["metrics"]["max_drawdown"] >= -0.25,
        "total_increment": all(
            candidate["metrics"]["net_total_return"] - c["metrics"]["net_total_return"] >= 0.03
            for c in controls
        ),
        "annual_increment": all(
            candidate["years"][y] - c["years"][y] >= -0.05 for c in controls for y in years
        ),
        "admissions": all(stats[y]["admissions"] >= 50 for y in years),
        "matching": all(
            stats[y]["admissions"] > 0 and stats[y][p] / stats[y]["admissions"] >= 0.98
            for y in years
            for p in POLICIES[1:]
        ),
    }
