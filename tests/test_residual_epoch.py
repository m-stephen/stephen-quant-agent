import json
import sqlite3

import pytest

from stephen_quant.workflows import v1110_residual_epoch as workflow


def test_model_and_account_reservations_precede_source_read(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}")
    output = tmp_path / "operation"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_dir": str(output), "preregistration_comment": 1}))
    monkeypatch.setattr(
        workflow,
        "verify_lineage",
        lambda c: (
            tmp_path / "source",
            {"snapshot_sha256": "a" * 64},
            [evidence],
            (tmp_path / "parent",),
        ),
    )
    monkeypatch.setattr(workflow, "CLAIM_ROOT", tmp_path / "claims")

    def fail(path):
        reservations = json.loads((output / "first_read_reservations.json").read_text())
        assert len(reservations["trials"]) == 21
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("select count(*) from trials").fetchone()[0] == 21
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(workflow, "load_frozen_days", fail)
    with pytest.raises(ValueError, match="synthetic source failure"):
        workflow.run(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    config.write_text(
        json.dumps({"output_dir": str(tmp_path / "repeat"), "preregistration_comment": 1})
    )
    with pytest.raises(FileExistsError):
        workflow.run(config)
    assert not (tmp_path / "repeat").exists()


def test_output_cannot_contain_source(tmp_path, monkeypatch):
    monkeypatch.setattr(
        workflow, "verify_lineage", lambda c: (tmp_path / "source", {}, [], (tmp_path / "parent",))
    )
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_dir": str(tmp_path), "preregistration_comment": 1}))
    with pytest.raises(ValueError, match="independent output"):
        workflow.run(config)
