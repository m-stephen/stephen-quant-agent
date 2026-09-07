"""Synthetic historical-code binding; never rebuild a consumed plan at new HEAD."""

import pytest

from stephen_quant.discovery import portfolio_construction_evidence as evidence
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def fixture_code(tmp_path, monkeypatch, changed=""):
    path = tmp_path / "original.py"
    path.write_bytes(b"value = 1\r\n")
    code = {"commit": evidence.COMMIT, "files": {"original.py": file_sha(path)}}
    code["sha256"] = sha256_json(code["files"])
    calls = []

    def git(root, *args):
        calls.append(args)
        if args == ("cat-file", "-t", evidence.COMMIT):
            return "commit"
        assert args == ("diff", "--name-only", evidence.COMMIT, "HEAD", "--")
        return changed

    monkeypatch.setattr(evidence, "_git", git)
    return path, code, calls


def test_new_module_does_not_rebind_or_invalidate_old_completed_code(tmp_path, monkeypatch):
    path, code, calls = fixture_code(tmp_path, monkeypatch, "new_module.py")
    proof = evidence.verify_historical_code(tmp_path, code)
    assert proof["commit"] == evidence.COMMIT and proof["files"] == 1
    assert path.read_bytes().endswith(b"\r\n")  # Raw bytes preserved, not text-normalized.
    assert len(calls) == 2


@pytest.mark.parametrize("mutation", ("raw", "history", "commit", "code_hash"))
def test_changed_consumed_runtime_cannot_be_silently_accepted(tmp_path, monkeypatch, mutation):
    path, code, _ = fixture_code(
        tmp_path, monkeypatch, "original.py" if mutation == "history" else ""
    )
    if mutation == "raw":
        path.write_bytes(b"value = 1\n")
    elif mutation == "commit":
        code["commit"] = "0" * 40
    elif mutation == "code_hash":
        code["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        evidence.verify_historical_code(tmp_path, code)


def test_completed_parent_metadata_pins_all_consumed_evidence_not_just_headline_profit():
    assert set(evidence.FILES) == {
        "RESULT.json",
        "AUDIT.json",
        "ASSESSMENT.json",
        "registry.sqlite3",
        "frozen_spec.json",
        "supervisor-backend/SUPERVISOR.json",
        "supervisor-audit/SUPERVISOR.json",
    }
    assert len(evidence.CLAIM_SHA) == len(evidence.TERMINAL_SHA) == 64
    assert evidence.PRIOR_DEBT == 3729
