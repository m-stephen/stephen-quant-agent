from stephen_quant.workflows.v44_path_robust_alpha import PathRobustness
from stephen_quant.workflows.v46_orthogonal_search import (
    CandidateEvidence,
    V46Config,
    YearEvidence,
    curated_schemas,
    select_orthogonal,
    stable_candidate,
)


def _path(year: int, value: float = 0.02) -> PathRobustness:
    return PathRobustness(year, 20, 1.0, 0.2, 18, value, -0.01, -0.03, 1.0, value, 1.1, value, -0.04)


def _years(*, bad_2025: bool = False) -> tuple[YearEvidence, ...]:
    result = []
    for year in (2022, 2023, 2024, 2025):
        rank_ic = -0.01 if bad_2025 and year == 2025 else 0.03
        result.append(YearEvidence(year, 200, rank_ic, 0.01, (0.01, 0.02, 0.01, 0.02), _path(year)))
    return tuple(result)


def _candidate(name: str, domain: str, objective: float) -> CandidateEvidence:
    return CandidateEvidence(name, "a" * 64, domain, 1, _years(), True, False, objective, f"trial-{name}", 1)


def test_v46_catalog_is_direction_complete_and_budgeted() -> None:
    schemas = curated_schemas()
    assert len(schemas) == 36
    for domain in ("auction", "fund_flow", "chip"):
        items = [schema for item_domain, schema in schemas if item_domain == domain]
        assert len(items) == 12
        assert sum(schema.schema_id.endswith("_inverse") for schema in items) == 6
    assert len({schema.fingerprint for _, schema in schemas}) == 36


def test_v46_stability_requires_each_outer_validation_year_positive() -> None:
    config = V46Config()
    config.validate()
    assert stable_candidate(_years(), config)
    assert not stable_candidate(_years(bad_2025=True), config)


def test_orthogonal_selection_keeps_one_per_domain_and_rejects_collinear_domain() -> None:
    candidates = (
        _candidate("auction-best", "auction", 3.0),
        _candidate("auction-second", "auction", 2.0),
        _candidate("flow-collinear", "fund_flow", 2.5),
        _candidate("chip-orthogonal", "chip", 2.0),
    )
    daily = {
        "auction-best": {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0},
        "auction-second": {"a": 2.0, "b": 1.0, "c": 2.0, "d": 1.0},
        "flow-collinear": {"a": 2.0, "b": 4.0, "c": 6.0, "d": 8.0},
        "chip-orthogonal": {"a": 1.0, "b": -1.0, "c": -1.0, "d": 1.0},
    }
    selected, correlations = select_orthogonal(candidates, daily, maximum_correlation=0.75)
    assert [item.candidate_id for item in selected] == ["auction-best", "chip-orthogonal"]
    assert correlations == (("auction-best", "chip-orthogonal", 0.0),)
