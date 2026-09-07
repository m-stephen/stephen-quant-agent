"""Report-only reconciliation tests; never regenerate or consume research paths."""

import importlib.util
from pathlib import Path

import pytest

from stephen_quant.discovery.power_design.contracts import PowerSpec
from stephen_quant.discovery.research_reset.statistics import calibration_decision

spec = importlib.util.spec_from_file_location(
    "v121_verifier", Path(__file__).resolve().parents[1] / "scripts/verify_v121.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


@pytest.mark.parametrize(
    "n,k", [(100, 0), (200, 0), (500, 0), (100, 89), (200, 178), (200, 185), (500, 401), (100, 100)]
)
@pytest.mark.parametrize("kind", ["power", "fwer"])
def test_independent_probability_polynomial_matches_frozen_finite_look(n, k, kind):
    verifier.compare(
        calibration_decision(k, n, kind=kind, spec=PowerSpec()), verifier.reference_look(k, n, kind)
    )


@pytest.mark.parametrize(
    "actual,expected",
    [
        ({"n": 199}, {"n": 200}),
        ({"lower": 0.9}, {"lower": 0.8}),
        ([1, 2], [1]),
        ({"status": "PASS"}, {"status": "FAIL"}),
        ({"a": 1, "extra": 1}, {"a": 1}),
    ],
)
def test_changed_summary_cannot_pass_verifier(actual, expected):
    with pytest.raises(ValueError):
        verifier.compare(actual, expected)
