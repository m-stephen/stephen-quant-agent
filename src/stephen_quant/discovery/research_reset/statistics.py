"""Dependency-light exact finite-look calibration and paired account estimands."""

from __future__ import annotations

import math


def binomial_cdf(k, n, p):
    if type(n) is not int or type(k) is not int or not 0 <= k <= n or n < 1:
        raise ValueError("valid binomial counts required")
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("probability outside [0,1]")
    if p == 0 or k == n:
        return 1.0
    if p == 1:
        return 0.0
    terms = [
        math.lgamma(n + 1)
        - math.lgamma(j + 1)
        - math.lgamma(n - j + 1)
        + j * math.log(p)
        + (n - j) * math.log1p(-p)
        for j in range(k + 1)
    ]
    peak = max(terms)
    return min(1.0, math.exp(peak) * math.fsum(math.exp(t - peak) for t in terms))


def _upper(k, n, tail):
    if k == n:
        return 1.0
    if k == 0:
        return -math.expm1(math.log(tail) / n)
    lo, hi = 0.0, 1.0
    for _ in range(55):
        mid = (lo + hi) / 2
        if binomial_cdf(k, n, mid) > tail:
            lo = mid
        else:
            hi = mid
    return hi


def exact_interval(k, n, tail):
    if type(n) is not int or type(k) is not int or not 0 <= k <= n or n < 1:
        raise ValueError("valid binomial counts required")
    if not math.isfinite(tail) or not 0 < tail < 0.5:
        raise ValueError("one-tail error budget outside (0,.5)")
    return (1 - _upper(n - k, n, tail), _upper(k, n, tail))


def calibration_decision(successes, n, *, kind, spec):
    spec.validate()
    if kind not in ("power", "fwer") or n not in spec.looks:
        raise ValueError("only frozen finite looks and named estimands are allowed")
    # A union bound covers both tails, every look and every required scenario.
    tail = spec.calibration_error / (2 * len(spec.looks) * len(spec.scenarios))
    lo, hi = exact_interval(successes, n, tail)
    threshold = spec.power_min if kind == "power" else spec.path_fwer_max
    if kind == "power":
        status = "PASS" if lo >= threshold else "FAIL" if hi < threshold else "CONTINUE"
    else:
        status = "PASS" if hi <= threshold else "FAIL" if lo > threshold else "CONTINUE"
    if n == spec.looks[-1] and status == "CONTINUE":
        status = "INCONCLUSIVE"
    return {
        "status": status,
        "n": n,
        "count": successes,
        "estimate": successes / n,
        "lower": lo,
        "upper": hi,
        "threshold": threshold,
        "kind": kind,
        "one_tail_error": tail,
        "delta_cal": spec.calibration_error,
        "method": "exact-binomial-bonferroni-scenarios-looks-two-tails",
    }


def drawdown(wealth):
    peak, worst = 1.0, 0.0
    for x in wealth:
        if not math.isfinite(x) or x <= 0:
            raise ValueError("positive finite normalized wealth required")
        peak = max(peak, x)
        worst = min(worst, x / peak - 1)
    return worst


def hac_mean(values, lag):
    values = tuple(float(x) for x in values)
    if not values or any(not math.isfinite(x) for x in values):
        raise ValueError("finite nonempty paired observations required")
    if type(lag) is not int or not 0 <= lag < len(values):
        raise ValueError("HAC lag must be less than observations")
    n = len(values)
    mean = math.fsum(values) / n
    z = [v - mean for v in values]
    variance = math.fsum(v * v for v in z) / n
    for j in range(1, lag + 1):
        variance += 2 * (1 - j / (lag + 1)) * math.fsum(z[i] * z[i - j] for i in range(j, n)) / n
    se = math.sqrt(max(0.0, variance) / n)
    return {
        "mean": mean,
        "se": se,
        "t": mean / se if se > 1e-15 else None,
        "lag": lag,
        "n": n,
        "interval": [mean - 1.96 * se, mean + 1.96 * se],
        "interpretation": "descriptive HAC normal approximation; not selection-adjusted",
    }


def paired_metrics(signal, baseline, *, capital_cny, lag=10):
    """Aligned daily *returns*, not NAV differences or an investable short account."""
    if not math.isfinite(capital_cny) or capital_cny <= 0:
        raise ValueError("positive common starting capital required")
    if len(signal) < 2 or len(signal) != len(baseline):
        raise ValueError("paired date/length mismatch")
    sr, br = [], []
    previous = ""
    for (day, a), (other, b) in zip(signal, baseline, strict=True):
        if day != other or day <= previous:
            raise ValueError("paired dates must agree and be strictly increasing")
        if any(not math.isfinite(v) or v <= -1 for v in (a, b)):
            raise ValueError("finite returns above -100% required; cannot drop bad dates")
        previous = day
        sr.append(a)
        br.append(b)
    ws, wb, ratios, active_wealth = 1.0, 1.0, [], []
    wa = 1.0
    active = [a - b for a, b in zip(sr, br, strict=True)]
    valid_active = True
    for a, b, d in zip(sr, br, active, strict=True):
        ws *= 1 + a
        wb *= 1 + b
        ratios.append(ws / wb)
        if d <= -1:
            valid_active = False
        if valid_active:
            wa *= 1 + d
            active_wealth.append(wa)
    midpoint = len(active) // 2
    return {
        "paired": hac_mean(active, lag),
        "signal_total_return": ws - 1,
        "baseline_total_return": wb - 1,
        "cumulative_return_difference_pp": 100 * (ws - wb),
        "relative_wealth_return": ws / wb - 1,
        "increment_cny": capital_cny * (ws - wb),
        "relative_wealth_drawdown": drawdown(ratios),
        "active_product_return": wa - 1 if valid_active else None,
        "active_product_drawdown": drawdown(active_wealth) if valid_active else None,
        "active_product_is_investable_account": False,
        "segment_means": [math.fsum(x) / len(x) for x in (active[:midpoint], active[midpoint:])],
        "capital_cny": capital_cny,
        "observations": len(active),
    }
