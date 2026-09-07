"""Independent covariance matrix and finite-n stationary AR measurement checks."""

import math

import numpy as np

from ..research_reset.statistics import exact_interval, hac_mean
from .contracts import LENGTHS


def matrix_hac(values, lag):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError("finite one dimensional sequence required")
    if type(lag) is not int or not 0 <= lag < len(x):
        raise ValueError("invalid matrix HAC lag")
    n = len(x)
    distance = np.abs(np.arange(n)[:, None] - np.arange(n)[None, :])
    weights = np.maximum(0, 1 - distance / (lag + 1))
    centered = x - np.mean(x)
    # Independent quadratic form: Bartlett covariance of the sample mean.
    se = math.sqrt(max(0.0, float(centered @ weights @ centered) / n**2))
    return {
        "mean": float(np.mean(x)),
        "se": se,
        "t": float(np.mean(x)) / se if se > 1e-15 else None,
    }


def ar_mean_variance(n, rho):
    if type(n) is not int or n < 2 or not -1 < rho < 1:
        raise ValueError("stationary AR and positive sample size required")
    # Unit marginal variance; finite n, not just the asymptotic approximation.
    return (n + 2 * math.fsum((n - k) * rho**k for k in range(1, n))) / n**2


def measurement_suite(repetitions=2000):
    if type(repetitions) is not int or not 20 <= repetitions <= 2000:
        raise ValueError("bounded measurement repetitions required")
    rows, largest_error = [], 0.0
    for n in LENGTHS:
        for rho in (0.0, 0.3, 0.8):
            rng = np.random.default_rng(2026090802 + n + int(100 * rho))
            x = np.zeros((repetitions, n))
            x[:, 0] = rng.normal(size=repetitions)
            for t in range(1, n):
                x[:, t] = rho * x[:, t - 1] + math.sqrt(1 - rho**2) * rng.normal(size=repetitions)
            means = np.mean(x, axis=1)
            estimates = [hac_mean(row, 10) for row in x]
            se = np.array([v["se"] for v in estimates])
            for i in range(min(3, repetitions)):
                reference = matrix_hac(x[i], 10)
                largest_error = max(largest_error, abs(reference["se"] - se[i]))
            covered = int(np.sum(np.abs(means) <= 1.96 * se))
            exceed = int(np.sum(means >= 2.5 * se))
            coverage_ci = exact_interval(covered, repetitions, 0.025)
            rows.append(
                {
                    "n": n,
                    "rho": rho,
                    "independent_replications": repetitions,
                    "true_mean": 0.0,
                    "true_mean_sd": math.sqrt(ar_mean_variance(n, rho)),
                    "empirical_mean_sd": float(np.std(means, ddof=1)),
                    "average_estimated_se": float(np.mean(se)),
                    "nominal_interval_coverage": covered / repetitions,
                    "coverage_interval_pointwise": coverage_ci,
                    "t_ge_2_5_rate": exceed / repetitions,
                    "undercoverage_flag": coverage_ci[1] < 0.95,
                }
            )
    return {
        "numerical_status": "PASS" if largest_error < 1e-12 else "FAIL",
        "maximum_matrix_se_absolute_error": largest_error,
        "rows": rows,
        "inference_status": "LIMITED_FINITE_SAMPLE_COVERAGE"
        if any(r["undercoverage_flag"] for r in rows)
        else "NO_FLAG_IN_DECLARED_CASES",
        "meaning": "numeric correctness is not valid confidence coverage; fixed lag10 not tuned",
        "intervals": "pointwise descriptive MC intervals, not simultaneous calibration acceptance",
    }
