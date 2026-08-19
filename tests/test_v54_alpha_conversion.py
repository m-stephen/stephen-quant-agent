from __future__ import annotations

from stephen_quant.workflows.v54_alpha_conversion import (
    DIAGNOSTIC_BREADTHS,
    DIAGNOSTIC_HORIZONS,
    AnnualConversion,
    V54Config,
    _stable_generated,
    constrained_schemas,
)


def _annual(
    year: int, *, ic: float, net: float, positive_paths: int, paths: int = 20
) -> AnnualConversion:
    return AnnualConversion(
        year, 200, 20_000, ic, 0.01, net + 0.01, net, 0.5, 0.01,
        0.02, 0.01, 200, positive_paths, paths, 0.8, 100, 200.0, 0.0,
    )


def test_v54_generator_is_exactly_direction_complete() -> None:
    schemas = constrained_schemas()
    assert len(schemas) == 12
    assert len({schema.fingerprint for _, schema in schemas}) == 12
    assert {domain for domain, _ in schemas} == {"margin", "auction", "limit_event"}
    bases = {}
    for domain, schema in schemas:
        key = (domain, schema.event, schema.formula, schema.horizon)
        bases.setdefault(key, set()).add(schema.direction)
    assert len(bases) == 6
    assert all(directions == {-1, 1} for directions in bases.values())


def test_v54_diagnostic_grid_is_frozen_to_36_trials() -> None:
    config = V54Config()
    config.validate()
    assert 3 * len(DIAGNOSTIC_HORIZONS) * len(DIAGNOSTIC_BREADTHS) == 36


def test_v54_generated_stability_requires_confirmation_and_paths() -> None:
    passed = (
        _annual(2022, ic=-0.01, net=-0.01, positive_paths=8),
        _annual(2023, ic=0.02, net=0.03, positive_paths=12),
        _annual(2024, ic=0.01, net=0.02, positive_paths=13),
    )
    failed = (
        _annual(2022, ic=0.02, net=0.01, positive_paths=15),
        _annual(2023, ic=0.03, net=0.02, positive_paths=11),
        _annual(2024, ic=0.01, net=0.03, positive_paths=14),
    )
    assert _stable_generated(passed, minimum_path_fraction=0.60)
    assert not _stable_generated(failed, minimum_path_fraction=0.60)


def test_v54_path_gate_scales_with_horizon() -> None:
    three_of_five = tuple(
        _annual(year, ic=0.02, net=0.01, positive_paths=3, paths=5)
        for year in (2022, 2023, 2024)
    )
    two_of_five = tuple(
        _annual(year, ic=0.02, net=0.01, positive_paths=2, paths=5)
        for year in (2022, 2023, 2024)
    )
    assert _stable_generated(three_of_five, minimum_path_fraction=0.60)
    assert not _stable_generated(two_of_five, minimum_path_fraction=0.60)
