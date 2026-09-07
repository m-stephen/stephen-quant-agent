import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def setup_successor(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "lead_successor", Path(__file__).parents[1] / "scripts/run_lead_successor.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parent = tmp_path / "parent"
    parent.mkdir()
    challenge = tmp_path / "challenge"
    challenge.mkdir()
    for folder in (parent, challenge):
        for name in ("RESULT.json", "registry.sqlite3", "first_read_reservations.json"):
            (folder / name).write_text("{}")
    frozen = tmp_path / "frozen.json"
    frozen.write_text("{}")
    result = {
        "decision": "PREREGISTER_NEXT_BOUNDED_MECHANISM_EPOCH",
        "engineering_pass": True,
        "stress_survivors": [],
        "raw_global_trial_lower_bound": 3088,
        "spec": {"leads_sha256": file_sha(frozen)},
    }
    (challenge / "RESULT.json").write_text(json.dumps(result))
    monkeypatch.setattr(
        module,
        "verify_parent",
        lambda config: (parent, frozen, {"snapshot_sha256": "b" * 64}, {}, (), tmp_path / "inputs"),
    )
    monkeypatch.setattr(module, "CLAIM_ROOT", tmp_path / "claims")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"protected_paths": []}))
    return module, config, challenge, tmp_path / "output", result


@pytest.mark.parametrize(
    "field,value",
    [("engineering_pass", False), ("stress_survivors", ["lead"]), ("decision", "ALPHA_PASS")],
)
def test_successor_refuses_wrong_gate(setup_successor, field, value):
    module, config, challenge, output, result = setup_successor
    result[field] = value
    (challenge / "RESULT.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="completed engineering"):
        module.run(config, challenge, output)
    assert not output.exists()


def test_successor_registers_before_price_and_refuses_duplicate_parent(
    setup_successor, monkeypatch
):
    module, config, challenge, output, _ = setup_successor

    def fail_at_read(folder):
        manifest = json.loads((output / "first_read_reservations.json").read_text())
        assert len(manifest["trials"]) == 96
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("SELECT count(*) FROM trials").fetchone()[0] == 96
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(module, "load_frozen_days", fail_at_read)
    with pytest.raises(ValueError, match="synthetic source failure"):
        module.run(config, challenge, output)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    with pytest.raises(FileExistsError):
        module.run(config, challenge, output.with_name("duplicate"))
    assert not output.with_name("duplicate").exists()
