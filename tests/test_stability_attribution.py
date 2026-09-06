import importlib.util
import json
from pathlib import Path

import pytest


def driver():
    path = Path(__file__).resolve().parents[1] / "scripts/run_stability_attribution.py"
    spec = importlib.util.spec_from_file_location("attribution_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_budget_is_frozen_twelve_no_fitting_variants():
    plans = driver().plans()
    assert len(plans) == len({p["key"] for p in plans}) == 12
    assert {p["roundtrip_bps"] for p in plans} == {0, 82, 164}
    assert driver().DEBT == 3322


def test_no_preregistration_rejected_before_sources(tmp_path):
    config = tmp_path / "cfg.json"
    config.write_text(json.dumps({"preregistration_comment": True}))
    with pytest.raises(ValueError, match="preregistration"):
        driver().run(config)


def test_existing_operation_rejected_before_sources(tmp_path):
    config = tmp_path / "cfg.json"
    config.write_text(
        json.dumps(
            {
                "preregistration_comment": 123,
                "parent_dir": "missing",
                "original_tree": "missing",
                "input_dir": "missing",
                "output_dir": str(tmp_path),
            }
        )
    )
    with pytest.raises(FileExistsError, match="already exists"):
        driver().run(config)


def test_factorial_cross_difference_and_cost_drag():
    d = driver()
    records = {
        p["key"]: {
            "metrics": {
                "net_total_return": 0.1
                + (p["policy"] == "stable_lowrisk") * 0.03
                + (p["mode"] == "target_changes") * 0.02
                - p["scale"] * 0.01
            }
        }
        for p in d.plans()
    }
    out = d.attribution(records)
    assert out["82"]["membership_increment"]["target_changes"] == pytest.approx(0.03)
    assert out["82"]["interaction"] == pytest.approx(0)
    assert out["cost_path_drag"]["stable_lowrisk-target_changes-164"] == pytest.approx(0.02)
