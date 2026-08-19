from __future__ import annotations

from collections import Counter

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.workflows.v70_discover_alpha import _direction_complete_plan
from stephen_quant.workflows.v72_discover_alpha import (
    V72_SOURCE_PAIR_QUOTAS,
    V72_VERSION,
    run_v72_discover_alpha,
)


def test_v72_source_balanced_plan_is_direction_complete() -> None:
    plan, proposal_ids = _direction_complete_plan(
        16,
        source_pair_quotas=V72_SOURCE_PAIR_QUOTAS,
    )
    assert len(plan.templates) == len(proposal_ids) == 32
    formulas: dict[tuple[str, str], set[int]] = {}
    for template in plan.templates:
        key = ("+".join(template.data_sources), template.formula_template)
        formulas.setdefault(key, set()).add(template.direction)
    assert all(directions == {-1, 1} for directions in formulas.values())
    counts = Counter(source for source, _ in formulas)
    assert counts == dict(V72_SOURCE_PAIR_QUOTAS)
    for source in ("qd_fund_flow", "qd_margin", "qd_chip"):
        signatures = {
            template.required_fields
            for template in plan.templates
            if "+".join(template.data_sources) == source
        }
        assert len(signatures) == dict(V72_SOURCE_PAIR_QUOTAS)[source]


def test_v72_metadata_run_reports_latest_release(tmp_path) -> None:
    report = run_v72_discover_alpha(
        LocalPathConfig(None, {}),
        registry=ExperimentRegistry(tmp_path / "registry.sqlite3"),
        output_dir=tmp_path / "output",
        code_version="test",
        metadata_only=True,
    )
    assert report.method_version == V72_VERSION
    assert report.generated_direction_complete_candidates == 32
    assert "V7.2" in report.to_markdown("en")
    assert (tmp_path / "output" / "v7.2-report.json").is_file()
