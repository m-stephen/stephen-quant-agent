import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from stephen_quant.discovery.incremental_alpha import IncrementalHypothesis
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def stage(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "calendar_lead_stress", Path(__file__).parents[1] / "scripts/run_calendar_lead_stress.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    parent = tmp_path / "parent"
    parent.mkdir()
    h = IncrementalHypothesis("concentration", 1, "blend", 20)
    previous = {
        "survivors": [h.name],
        "engineering_pass": True,
        "raw_global_trial_lower_bound": 3256,
        "spec": {"runtime_code_sha256": m.runtime_code_hash()},
    }
    (parent / "RESULT.json").write_text(json.dumps(previous))
    for name in ("registry.sqlite3", "first_read_reservations.json", "FROZEN_LEADS.json"):
        (parent / name).write_text("{}")
    frozen = tmp_path / "frozen.json"
    frozen.write_text("{}")
    monkeypatch.setattr(m, "PARENT_SHA", file_sha(parent / "RESULT.json"))
    monkeypatch.setattr(m, "CLAIM_ROOT", tmp_path / "claims")
    monkeypatch.setattr(
        m,
        "verify_parent",
        lambda config: (
            tmp_path / "old",
            frozen,
            {"snapshot_sha256": "a" * 64},
            {},
            (h,),
            tmp_path / "inputs",
        ),
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"protected_paths": []}))
    return m, config, parent, tmp_path / "output", previous


@pytest.mark.parametrize(
    "key,value",
    [("survivors", []), ("engineering_pass", False), ("raw_global_trial_lower_bound", 3184)],
)
def test_deep_requires_frozen_lead_and_debt(stage, key, value, monkeypatch):
    m, config, parent, output, previous = stage
    previous[key] = value
    (parent / "RESULT.json").write_text(json.dumps(previous))
    monkeypatch.setattr(m, "PARENT_SHA", file_sha(parent / "RESULT.json"))
    with pytest.raises(ValueError, match="frozen staggered lead"):
        m.run(config, parent, output)
    assert not output.exists()


def test_deep_preread_reservations_and_duplicate_prevention(stage, monkeypatch):
    m, config, parent, output, _ = stage

    def fail(folder):
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("select count(*) from trials").fetchone()[0] == 12
        assert (
            len(json.loads((output / "first_read_reservations.json").read_text())["trials"]) == 12
        )
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(m, "load_frozen_days", fail)
    with pytest.raises(ValueError, match="synthetic source failure"):
        m.run(config, parent, output)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    with pytest.raises(FileExistsError):
        m.run(config, parent, output.with_name("duplicate"))
    assert not output.with_name("duplicate").exists()
