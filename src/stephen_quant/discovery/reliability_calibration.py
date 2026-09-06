"""Independent synthetic paths through the actual portfolio/execution selector."""

from __future__ import annotations

import math
import os
import random
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from statistics import mean

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import (
    ResearchCandidate,
    ResearchDay,
    metric_bundle,
    run_candidate,
    selection_key,
    sharpe,
    temporal_selection,
)
from stephen_quant.discovery.search_power_dsl import sha256_json


def family_placebo(series: dict[str, list[float]], *, seed=114, repetitions=199, block=20):
    """Symmetric block-sign null; repeat the same family selector in each draw.

    Validity is conditional on approximate block sign symmetry. Synthetic audit
    checks this test against known nulls; historical output remains diagnostic.
    """
    if not series or len({len(v) for v in series.values()}) != 1:
        raise ValueError("placebo requires aligned return matrix")
    winner = max(series, key=lambda key: selection_key(series[key], key))
    observed = mean(series[winner])
    rng = random.Random(seed)
    exceed = 0
    n = len(series[winner])
    for _ in range(repetitions):
        signs = [rng.choice((-1, 1)) for _ in range((n + block - 1) // block)]
        null_max = max(sum(v[i] * signs[i // block] for i in range(n)) / n for v in series.values())
        exceed += null_max >= observed
    return {
        "p_value": (exceed + 1) / (repetitions + 1),
        "winner": winner,
        "repetitions": repetitions,
        "block_sessions": block,
        "null": "common_block_sign_symmetry_of_active_returns",
        "exchangeability": "assumption_not_independent_confirmation",
    }


def wilson(success, n):
    z = 1.959963984540054
    p = success / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def synthetic_days(seed: int, planted: bool, size=80, periods=160):
    rng = random.Random(seed)
    target_field = "ret_20" if seed % 2 else "net_inflow_ratio"
    direction = 1 if seed % 3 else -1
    prices = [100.0] * size
    latent = {
        field: [rng.gauss(0, 1) for _ in range(size)] for field in ("ret_20", "net_inflow_ratio")
    }
    frames = []
    current = date(2022, 1, 3)
    for t in range(periods):
        while current.weekday() > 4:
            current += timedelta(days=1)
        day = current.isoformat()
        bars = []
        for i in range(size):
            opening = prices[i]
            # Feature at t-1 determines t return; the new t feature is generated below.
            edge = 0.003 * direction * latent[target_field][i] if planted else 0.0
            volatility = 0.007 if t < periods // 2 else 0.011
            ret = edge + rng.gauss(0, volatility)
            prices[i] *= 1 + ret
            if not (i == 0 and 40 <= t < 43):
                bars.append(
                    StatefulBar(
                        day,
                        f"S{i:03d}",
                        opening,
                        prices[i],
                        500_000.0,
                        f"{day}T08:00:00+08:00",
                        not (i == 1 and t % 37 == 0),
                        True,
                        False,
                        "synthetic_limit" if i == 1 and t % 37 == 0 else "normal",
                    )
                )
        for field, values in latent.items():
            latent[field] = [0.99 * x + rng.gauss(0, 0.1) for x in values]
        features = {f"S{i:03d}": {f: latent[f][i] for f in latent} for i in range(size)}
        if t % 11 == 0:
            features["S003"].pop("net_inflow_ratio")
        frames.append(ResearchDay(day, features, tuple(bars)))
        current += timedelta(days=1)
    return tuple(frames), target_field, direction


def _case(args):
    seed, planted = args
    days, field, direction = synthetic_days(seed, planted)
    candidates = [
        ResearchCandidate(f"{f}:{s}", (f,), direction=s, horizon=5)
        for f in ("ret_20", "net_inflow_ratio")
        for s in (-1, 1)
    ]
    series = {}
    coverage = {}
    for candidate in candidates:
        account, cov, _ = run_candidate(days, candidate, multiplier=2)
        base, _, _ = run_candidate(days, candidate, multiplier=2, benchmark=True)
        metrics = metric_bundle(account, base)
        series[candidate.name] = metrics["daily_active"]
        coverage[candidate.name] = sum(x["active"] for x in cov)
    verdict = family_placebo(series, seed=seed, repetitions=199)
    winner = verdict["winner"]
    statistics = temporal_selection([d.date for d in days], series, 2818)
    assert statistics["winner"] == winner
    detected = (
        verdict["p_value"] <= 0.05 and mean(series[winner]) > 0 and sharpe(series[winner]) >= 0.5
    )
    return {
        "seed": seed,
        "planted": planted,
        "winner": winner,
        "expected": f"{field}:{direction}",
        "recovered": winner == f"{field}:{direction}",
        "detected": detected,
        "p_value": verdict["p_value"],
        "winner_sharpe": sharpe(series[winner]),
        "dsr": statistics["dsr"],
        "pbo": statistics["pbo"],
        "effective_observations": statistics["effective_observations"],
        "purged_samples": sum(f["purged_n"] for f in statistics["folds"]),
        "statistical_gate_pass": (
            detected
            and statistics["dsr"] >= 0.95
            and statistics["pbo"] is not None
            and statistics["pbo"] <= 0.05
        ),
        "pid": os.getpid(),
        "coverage": coverage,
    }


def run_calibration(*, workers=8, audit=True):
    start = 114900 if audit else 114000
    jobs = [(start + i, True) for i in range(24)] + [(start + 1000 + i, False) for i in range(100)]
    if workers == 1:
        rows = [_case(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_case, jobs))
    pids = sorted({r["pid"] for r in rows})
    content = [{k: v for k, v in r.items() if k != "pid"} for r in rows]
    recovered = sum(r["recovered"] for r in rows if r["planted"])
    detected = sum(r["detected"] for r in rows if r["planted"])
    false = sum(r["detected"] for r in rows if not r["planted"])
    interval = wilson(false, 100)
    return {
        "pass": recovered / 24 >= 0.75 and detected / 24 >= 0.75 and interval[1] <= 0.05,
        "planted_recovered": recovered,
        "planted_detected": detected,
        "planted_cases": 24,
        "null_false_positives": false,
        "null_cases": 100,
        "null_fwer": false / 100,
        "null_wilson95": interval,
        "content_sha256": sha256_json(content),
        "actual_worker_pids": pids,
        "requested_workers": workers,
        "cases": content,
        "scope": "fixed family selector + masked scores + stateful execution + double costs + family placebo",
        "statistical_gate_planted_pass": sum(
            r["statistical_gate_pass"] for r in rows if r["planted"]
        ),
        "statistical_gate_null_pass": sum(
            r["statistical_gate_pass"] for r in rows if not r["planted"]
        ),
        "statistical_scope": "daily DSR and purged CPCV/PBO executed on all paths; power gate is selector/placebo, not a promise of Court power",
        "not_covered": "24-candidate market-family FWER; unbounded adaptive search; market-data availability; live brokerage fills",
    }
