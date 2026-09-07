"""Synthetic control-plane tests; no source contents or real attempt reservation."""

import copy
import json

import pytest

from stephen_quant.discovery import signal_construction_runtime as runtime
from stephen_quant.discovery.flow_response_predictor import POLICIES
from stephen_quant.discovery.flow_response_protocol import plans


def spec(root):
    return {
        "version": runtime.VERSION,
        "prior_debt": 3733,
        "budget": 4,
        "new_fits": 0,
        "validated_alpha": False,
        "research_contract": runtime.contract(),
        "runtime_code_sha256": "a" * 64,
        "completed_parent_evidence_sha256": "b" * 64,
        "calendar": {"count": 726, "sha256": "c" * 64},
        "inherited": {
            "root": str(root.resolve()),
            "trial_ids": {p["key"]: f"synthetic-{i}" for i, p in enumerate(plans())},
            "files": dict.fromkeys(
                ["registry.sqlite3", "history/history.json"]
                + [f"models/{p}-{y}.json" for p in POLICIES for y in (2023, 2024)],
                "d" * 64,
            ),
        },
    }


def test_reserve_all_four_no_fits_no_new_providers_and_no_replay(tmp_path):
    frozen = spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, frozen)
    runtime.check_native(reg, output, frozen, tids)
    assert len(tids) == reg.global_trial_count() == 4
    for tid in tids.values():
        assert not reg.fit_lineage(tid)["fits"]
        assert not reg.fit_lineage(tid)["stages"]
        assert not reg.feature_sources(tid)["providers"]
    with pytest.raises(FileExistsError):
        runtime.reserve_accounts(output, frozen)


@pytest.mark.parametrize("fault", ["missing", "policy", "code", "done", "snapshot", "promote"])
def test_invalid_reservation_blocks_before_numerical_read(tmp_path, monkeypatch, fault):
    frozen = spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, frozen)
    with reg.connect() as db:
        if fault == "missing":
            tids.pop(next(iter(tids)))
        if fault == "policy":
            db.execute("UPDATE trials SET hyperparams='{}'")
        if fault == "code":
            db.execute("UPDATE experiments SET code_version='other'")
        if fault == "done":
            db.execute("UPDATE trials SET result_json='{}'")
        if fault == "snapshot":
            frozen["calendar"]["sha256"] = "e" * 64
        if fault == "promote":
            frozen["validated_alpha"] = True
        db.commit()
    monkeypatch.setattr(runtime, "open_inputs", lambda *a: pytest.fail("unexpected numerical read"))
    with pytest.raises(ValueError):
        runtime.execute_accounts(reg, tids, frozen, output=output)
    assert not (output / "BACKEND_CLAIM.json").exists()


def test_failure_retains_entire_budget_and_blocks_retry(tmp_path, monkeypatch):
    frozen = spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, frozen)

    def unavailable(*args):
        raise OSError("synthetic unavailable source")

    monkeypatch.setattr(runtime, "open_inputs", unavailable)
    with pytest.raises(OSError):
        runtime.execute_accounts(reg, tids, frozen, output=output)
    failure = json.loads((output / "ABORTED.json").read_bytes())
    assert failure["reserved_trials"] == 4 and failure["raw_global_trial_lower_bound"] == 3737
    assert reg.global_trial_count() == 4 and not failure["automatic_retry"]
    with pytest.raises(ValueError):
        runtime.execute_accounts(reg, tids, frozen, output=output)


@pytest.mark.parametrize("fault", ["calendar", "model", "identity", "scope", "newfits"])
def test_exact_scope_hashes_and_original_lineage_required(tmp_path, fault):
    frozen = copy.deepcopy(spec(tmp_path / "old"))
    if fault == "calendar":
        frozen["calendar"]["count"] = 725
    if fault == "model":
        del frozen["inherited"]["files"]["models/response-2023.json"]
    if fault == "identity":
        frozen["inherited"]["trial_ids"].pop("response-82")
    if fault == "scope":
        frozen["research_contract"]["top_n"] = 50
    if fault == "newfits":
        frozen["new_fits"] = 1
    with pytest.raises(ValueError):
        runtime.reserve_accounts(tmp_path / "new", frozen)
    assert not (tmp_path / "new/registry.sqlite3").exists()
