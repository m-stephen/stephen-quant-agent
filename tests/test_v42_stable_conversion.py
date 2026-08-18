from __future__ import annotations

from dataclasses import replace

import pytest

from stephen_quant.workflows.v41_semantic_alpha import UsageScore, UsageSpec
from stephen_quant.workflows.v42_stable_conversion import (
    FROZEN_SHORTLIST_SHA256,
    FROZEN_V41_SHORTLIST,
    StabilityScore,
    SubwindowScore,
    V42Config,
    chronological_subwindows,
    finalize_stability_scores,
    select_stable_mapping,
)


def _usage(candidate: str, spec: UsageSpec, sharpe: float) -> UsageScore:
    return UsageScore(
        candidate,
        2023,
        spec,
        3_000_000,
        120,
        240,
        sharpe,
        0.20,
        -0.08,
        0.05,
        0.01,
        0.0,
        sharpe,
    )


def _stability(
    candidate: str,
    spec: UsageSpec,
    *,
    full: float,
    worst: float,
    preliminary: bool,
) -> StabilityScore:
    windows = tuple(SubwindowScore(index, 60, 0.03, worst + index / 100, -0.03) for index in range(1, 5))
    reasons = () if preliminary else ("negative_worst_subwindow",)
    return StabilityScore(
        candidate,
        spec,
        _usage(candidate, spec, full),
        _usage(candidate, spec, full - 0.1),
        windows,
        windows,
        1.0 if preliminary else 0.5,
        worst + 0.02,
        worst,
        worst - 0.05,
        0.0,
        None,
        preliminary,
        False,
        full + worst,
        reasons,
    )


def test_frozen_shortlist_and_hash_are_deterministic() -> None:
    assert len(FROZEN_V41_SHORTLIST) == 12
    assert len(set(FROZEN_V41_SHORTLIST)) == 12
    assert FROZEN_SHORTLIST_SHA256 == (
        "913de6d25c60289f9a0c04f053d2803bd5933b0a893ad8984203ec002dce9a46"
    )


def test_chronological_subwindows_cover_returns_once_in_order() -> None:
    values = tuple(index / 10_000 for index in range(1, 11))
    windows = chronological_subwindows(values)

    assert [item.observations for item in windows] == [2, 3, 2, 3]
    assert sum(item.observations for item in windows) == len(values)
    assert all(item.cumulative_excess_return > 0 for item in windows)


def test_maximum_sharpe_regime_wrapper_cannot_beat_stable_unconditional_mapping() -> None:
    scores = []
    for breadth in (5, 10, 20):
        scores.append(
            _stability(
                "candidate",
                UsageSpec("TIMING", breadth, "all"),
                full=1.2,
                worst=0.4,
                preliminary=True,
            )
        )
        scores.append(
            _stability(
                "candidate",
                UsageSpec("TIMING", breadth, "risk_off"),
                full=6.0,
                worst=-2.0,
                preliminary=False,
            )
        )

    finalized = finalize_stability_scores(tuple(scores), V42Config())
    selected = select_stable_mapping(finalized)

    assert selected.spec.regime == "all"
    assert selected.eligible
    rejected = [item for item in finalized if item.spec.regime == "risk_off"]
    assert all(not item.eligible for item in rejected)


def test_regime_wrapper_requires_increment_over_same_unconditional_mapping() -> None:
    scores = []
    for breadth in (5, 10, 20):
        unconditional = _stability(
            "candidate",
            UsageSpec("BUY", breadth, "all"),
            full=1.0,
            worst=0.5,
            preliminary=True,
        )
        wrapper = _stability(
            "candidate",
            UsageSpec("BUY", breadth, "risk_on"),
            full=1.1,
            worst=0.51,
            preliminary=True,
        )
        scores.extend((unconditional, wrapper))

    finalized = finalize_stability_scores(tuple(scores), V42Config())
    wrappers = [item for item in finalized if item.spec.regime == "risk_on"]

    assert all("regime_increment_not_proven" in item.rejection_reasons for item in wrappers)
    assert all(not item.eligible for item in wrappers)


def test_shadow_year_and_selector_thresholds_are_frozen() -> None:
    with pytest.raises(ValueError, match="windows are frozen"):
        replace(V42Config(), shadow_year=2025).validate()
    with pytest.raises(ValueError, match="four chronological"):
        replace(V42Config(), subwindows=5).validate()
