from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.cli import build_parser
from stephen_quant.discovery import v21_mechanism_generation_plan
from stephen_quant.v2 import (
    load_v21_real_research_config,
    run_reliability_calibration,
)
from stephen_quant.v2.real_qd import resolve_discovery_config


def test_v21_manifest_freezes_research_and_sealed_windows() -> None:
    path = Path("configs/v2.1-real-research.json")
    config = load_v21_real_research_config(path)
    discovery = resolve_discovery_config(config, path)

    assert discovery.search_profile == "v2.1"
    assert discovery.research_end == "2024-12-31"
    assert discovery.validation_start == "2025-01-03"
    assert discovery.test_start == "2026-01-05"
    assert discovery.schema_budget == 26


def test_v21_manifest_rejects_research_overlap_with_holdout(tmp_path: Path) -> None:
    payload = json.loads(Path("configs/v2.1-real-research.json").read_text(encoding="utf-8"))
    payload["research_end"] = "2025-01-03"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="chronological|research must end"):
        load_v21_real_research_config(path)


def test_v21_mechanism_plan_has_distinct_bounded_families() -> None:
    plan = v21_mechanism_generation_plan()
    plan.validate()
    ids = tuple(item.template_id for item in plan.templates)

    assert len(ids) >= 12
    assert len(ids) == len(set(ids))
    assert plan.windows == (5, 20)
    assert plan.horizons == ("20d",)
    assert len(ids) * len(plan.windows) == 26
    for template in plan.templates:
        template.render(window=5, horizon="20d").validate()


def test_v21_reliability_controls_reject_duplicates_and_retain_signal() -> None:
    report = run_reliability_calibration()

    assert report.decision == "PASS"
    assert report.exact_duplicate_recall == 1.0
    assert report.duplicate_precision == 1.0
    assert report.duplicate_recall == 1.0
    assert report.known_valid_recall == 1.0
    assert report.false_promotion_rate == 0.0


def test_v21_offline_replay_does_not_require_local_paths() -> None:
    args = build_parser().parse_args(
        [
            "v2-real-research",
            "--mode",
            "replay",
            "--replay-manifest",
            "frozen-manifest.json",
        ]
    )

    assert args.paths_config is None
    assert args.mode == "replay"
