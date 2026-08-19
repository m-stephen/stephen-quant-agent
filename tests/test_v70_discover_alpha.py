from __future__ import annotations

import json

from stephen_quant.cli import build_parser
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.path_config import LocalPathConfig
from stephen_quant.workflows.v70_discover_alpha import (
    _direction_complete_plan,
    run_v70_discover_alpha,
)


def test_v70_direction_complete_plan_is_bounded_and_paired() -> None:
    plan, proposal_ids = _direction_complete_plan(8)
    assert len(plan.templates) == 16
    assert len(proposal_ids) == 16
    by_formula: dict[str, set[int]] = {}
    for template in plan.templates:
        by_formula.setdefault(template.formula_template, set()).add(template.direction)
    assert len(by_formula) == 8
    assert all(directions == {-1, 1} for directions in by_formula.values())
    assert any("period_return" in formula for formula in by_formula)
    assert any("volatility" in formula for formula in by_formula)


def test_v70_metadata_run_reports_coverage_without_local_paths(tmp_path) -> None:
    paths = {}
    for key in ("qd_daily_dir", "qd_fund_flow_dir", "qd_auction_dir"):
        root = tmp_path / key
        root.mkdir()
        (root / "sample_20240102.csv").write_text("fixture", encoding="utf-8")
        (root / "sample_20240103.csv").write_text("fixture", encoding="utf-8")
        paths[key] = root
    report = run_v70_discover_alpha(
        LocalPathConfig(None, paths),
        registry=ExperimentRegistry(tmp_path / "registry.sqlite3"),
        output_dir=tmp_path / "report",
        code_version="test",
        metadata_only=True,
    )
    assert report.system_status == "OPERATIONAL"
    assert report.alpha_status == "NO_VALIDATED_ALPHA"
    assert report.common_core_sessions == 2
    assert report.recorded_trials == 0
    assert not report.deployable
    assert not report.validation_window_opened
    assert not report.test_window_opened
    payload = report.to_json()
    assert str(tmp_path) not in payload
    assert json.loads(payload)["decision"] == "V7_OPERATIONAL_METADATA_ONLY"


def test_v70_cli_requires_local_path_config() -> None:
    args = build_parser().parse_args(
        ["discover-alpha", "--paths-config", "configs/qd-paths.local.json", "--metadata-only"]
    )
    assert args.command == "discover-alpha"
    assert args.metadata_only
