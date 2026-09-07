import math
from dataclasses import replace

import pytest

from stephen_quant.discovery.research_reset.contracts import ResetSpec
from stephen_quant.discovery.research_reset.statistics import (
    binomial_cdf,
    calibration_decision,
    exact_interval,
    hac_mean,
    paired_metrics,
)


@pytest.mark.parametrize(
    "k,n,p,expected",
    [(0, 2, 0.5, 0.25), (1, 2, 0.5, 0.75), (2, 2, 0.5, 1), (0, 20, 0, 1), (0, 20, 1, 0)],
)
def test_binomial_reference(k, n, p, expected):
    assert binomial_cdf(k, n, p) == pytest.approx(expected)


def test_exact_bounds_reference_and_symmetry():
    lo, hi = exact_interval(0, 100, 0.05)
    assert lo == 0
    assert hi == pytest.approx(0.029513049607039932)
    assert exact_interval(100, 100, 0.05) == pytest.approx((1 - hi, 1))
    lo, hi = exact_interval(7, 50, 0.025)
    # SciPy/Clopper-Pearson documentation reference, no runtime SciPy dependency.
    assert (lo, hi) == pytest.approx((0.05819170033997342, 0.26739600249700846))


@pytest.mark.parametrize(
    "args",
    [
        (-1, 100, 0.05),
        (101, 100, 0.05),
        (0, 0, 0.05),
        (True, 100, 0.05),
        (0, 100, 0),
        (0, 100, math.nan),
    ],
)
def test_exact_invalid_inputs(args):
    with pytest.raises(ValueError):
        exact_interval(*args)


def test_finite_looks_cover_all_scenes_and_tails():
    spec = ResetSpec()
    first = calibration_decision(0, 100, kind="fwer", spec=spec)
    assert first["one_tail_error"] * 2 * 3 * 4 == pytest.approx(0.05)
    assert first["status"] == "CONTINUE"  # Ordinary unadjusted CI would pass early.
    assert calibration_decision(0, 200, kind="fwer", spec=spec)["status"] == "PASS"
    assert calibration_decision(100, 100, kind="power", spec=spec)["status"] == "PASS"
    assert calibration_decision(0, 100, kind="power", spec=spec)["status"] == "FAIL"
    assert calibration_decision(25, 500, kind="fwer", spec=spec)["status"] == "INCONCLUSIVE"
    assert calibration_decision(400, 500, kind="power", spec=spec)["status"] == "INCONCLUSIVE"


def test_cannot_peek_at_unplanned_look_or_relax_threshold():
    with pytest.raises(ValueError):
        calibration_decision(0, 101, kind="fwer", spec=ResetSpec())
    with pytest.raises(ValueError):
        calibration_decision(0, 100, kind="fwer", spec=replace(ResetSpec(), path_fwer_max=0.1))


def test_ordinary_intervals_are_not_sequentially_valid():
    # Exact dynamic probability, no simulation and no market labels.
    # At p=.05, uncorrected one-sided95% upper bounds cross below truth when
    # cumulative successes <=1,4,16 at looks100,200,500 respectively.
    p, distribution, old_n, crossing = 0.05, [1.0], 0, 0.0
    for n, cutoff in ((100, 1), (200, 4), (500, 16)):
        increment = n - old_n
        mass = [(1 - p) ** increment]
        for k in range(1, increment + 1):
            mass.append(mass[-1] * (increment - k + 1) / k * p / (1 - p))
        next_mass = [0.0] * (n + 1)
        for k, prior in enumerate(distribution):
            for j, value in enumerate(mass):
                next_mass[k + j] += prior * value
        crossing += sum(next_mass[: cutoff + 1])
        next_mass[: cutoff + 1] = [0.0] * (cutoff + 1)
        distribution, old_n = next_mass, n
    assert crossing == pytest.approx(0.07670278585491326)
    assert crossing > 0.05


def test_paired_units_are_not_interchangeable():
    a = [("a", 0.10), ("b", -0.05)]
    b = [("a", 0.02), ("b", 0.03)]
    result = paired_metrics(a, b, capital_cny=3_000_000, lag=0)
    assert result["paired"]["mean"] == pytest.approx(0)
    assert result["cumulative_return_difference_pp"] == pytest.approx(-0.56)
    assert result["increment_cny"] == pytest.approx(-16800)
    assert result["relative_wealth_return"] == pytest.approx(1.045 / 1.0506 - 1)
    assert result["active_product_return"] == pytest.approx(-0.0064)
    assert result["active_product_is_investable_account"] is False


@pytest.mark.parametrize(
    "a,b",
    [
        ([("a", 0.1)], [("a", 0.1)]),
        ([("a", 0.1), ("b", 0.1)], [("b", 0.1), ("c", 0.1)]),
        ([("a", 0.1), ("a", 0.1)], [("a", 0.1), ("a", 0.1)]),
        ([("a", math.nan), ("b", 0)], [("a", 0), ("b", 0)]),
        ([("a", -1), ("b", 0)], [("a", 0), ("b", 0)]),
    ],
)
def test_paired_invalid_or_missing_dates_fail(a, b):
    with pytest.raises(ValueError):
        paired_metrics(a, b, capital_cny=3_000_000, lag=0)


def test_hac_constant_sequence_is_not_infinite_confidence():
    result = hac_mean([0.01] * 20, 5)
    assert result["se"] == 0
    assert result["t"] is None
