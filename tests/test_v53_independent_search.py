from __future__ import annotations

import pytest

from stephen_quant.workflows.v44_path_robust_alpha import PathRobustness
from stephen_quant.workflows.v46_orthogonal_search import YearEvidence
from stephen_quant.workflows.v53_independent_search import (
    BASE_SCHEMA_IDS,
    V53Config,
    _stable,
    independent_schemas,
)


def _path(value: float) -> PathRobustness:
    return PathRobustness(
        2022,
        20,
        0.5,
        0.1,
        16,
        value,
        -0.01,
        -0.03,
        0.8,
        value,
        0.7,
        value,
        -0.05,
    )


def test_v53_search_space_is_exactly_direction_complete_and_independent() -> None:
    schemas = independent_schemas()
    assert len(schemas) == 14
    assert len({schema.fingerprint for _, schema in schemas}) == 14
    assert {domain for domain, _ in schemas} == {"margin", "auction", "limit_event"}
    for base in BASE_SCHEMA_IDS:
        matching = [schema for _, schema in schemas if schema.schema_id.startswith(base)]
        assert {schema.direction for schema in matching} == {-1, 1}
    assert all("qd_chip" not in schema.data_sources for _, schema in schemas)
    assert all("qd_fund_flow" not in schema.data_sources for _, schema in schemas)


def test_v53_stability_requires_positive_confirmation_years() -> None:
    passed = tuple(
        YearEvidence(year, 200, ic, 0.01, (ic, ic, ic, ic), _path(0.02))
        for year, ic in ((2022, -0.01), (2023, 0.02), (2024, 0.01))
    )
    failed = tuple(
        YearEvidence(year, 200, ic, 0.01, (ic, ic, ic, ic), _path(0.02))
        for year, ic in ((2022, 0.02), (2023, -0.01), (2024, 0.03))
    )
    assert _stable(passed)
    assert not _stable(failed)


def test_v53_rejects_relaxed_falsification_gates() -> None:
    with pytest.raises(ValueError, match="falsification"):
        V53Config(minimum_dsr=0.90).validate()
