"""No-market tests for all-account continuation reservation boundaries."""

import copy

import pytest

from stephen_quant.discovery import flow_response_continuation as m


@pytest.fixture
def spec():
    files = {"registry.sqlite3": "a" * 64, "history/history.json": "b" * 64}
    files.update({f"models/{p}-{y}.json": "c" * 64 for p in m.POLICIES for y in (2023, 2024)})
    return {
        "version": m.VERSION,
        "prior_debt": 3707,
        "budget": 22,
        "new_fits": 0,
        "validated_alpha": False,
        "accounts": m.account_plans(),
        "research_contract": m.contract(),
        "runtime_code_sha256": "d" * 64,
        "anchor_card_sha256": "e" * 64,
        "consumed_evidence_sha256": "f" * 64,
        "inherited": {
            "root": "synthetic-unread",
            "files": files,
            "trial_ids": {p["key"]: f"old-{i}" for i, p in enumerate(m.plans())},
        },
    }


def test_all_native_accounts_reserved_without_any_source_read(tmp_path, spec, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("inherited evidence read before reservations")

    monkeypatch.setattr(m, "verified_inherited", forbidden)
    reg, tids = m.reserve_continuation(tmp_path, spec)
    assert reg.global_trial_count() == len(tids) == 22
    for tid in tids.values():
        assert not reg.fit_lineage(tid)["stages"]
        assert not reg.fit_lineage(tid)["fits"]
        assert not reg.feature_sources(tid)["providers"]
    with pytest.raises(FileExistsError):
        m.reserve_continuation(tmp_path, spec)


@pytest.mark.parametrize("change", ["debt", "budget", "fit", "alpha", "missing_model", "path"])
def test_unfrozen_or_incomplete_contract_rejected_before_reservation(tmp_path, spec, change):
    changed = copy.deepcopy(spec)
    if change == "debt":
        changed["prior_debt"] = 3706
    elif change == "budget":
        changed["budget"] = 1
    elif change == "fit":
        changed["new_fits"] = 1
    elif change == "alpha":
        changed["validated_alpha"] = True
    elif change == "missing_model":
        del changed["inherited"]["files"]["models/risk-2023.json"]
    else:
        changed["inherited"]["files"]["../escape"] = "0" * 64
    with pytest.raises(ValueError):
        m.reserve_continuation(tmp_path, changed)
    assert not (tmp_path / "registry.sqlite3").exists()


@pytest.mark.parametrize("change", ["missing", "duplicate", "changed", "completed"])
def test_native_preflight_precedes_inherited_numeric_read(tmp_path, spec, monkeypatch, change):
    output, original = tmp_path / "new", tmp_path / "original"
    original.mkdir()
    reg, tids = m.reserve_continuation(output, spec)
    if change == "missing":
        tids.pop("risk-82")
    elif change == "duplicate":
        tids["risk-82"] = tids["response-82"]
    elif change == "changed":
        with reg.connect() as db:
            db.execute("UPDATE experiments SET search_space='{}'")
    else:
        reg.record_trial_result(tids["risk-82"], "{}")

    def forbidden(*a, **kw):
        raise AssertionError("preflight read inherited data")

    monkeypatch.setattr(m, "verified_inherited", forbidden)
    with pytest.raises(ValueError):
        m.execute_continuation(reg, tids, spec, output=output, original_tree=original)
    assert not (output / "BACKEND_CLAIM.json").exists()


def test_failure_keeps_all_debt_and_refuses_same_operation_retry(tmp_path, spec, monkeypatch):
    output, original = tmp_path / "new", tmp_path / "original"
    original.mkdir()
    reg, tids = m.reserve_continuation(output, spec)

    def fail(*a):
        raise ValueError("synthetic inherited evidence failure")

    monkeypatch.setattr(m, "verified_inherited", fail)
    with pytest.raises(ValueError):
        m.execute_continuation(reg, tids, spec, output=output, original_tree=original)
    failure = m.read(output / "ABORTED.json")
    assert failure["raw_global_trial_lower_bound"] == 3729
    assert failure["reserved_trials"] == reg.global_trial_count() == 22
    assert not failure["validated_alpha"] and not failure["automatic_retry"]
    with pytest.raises(FileExistsError):
        m.execute_continuation(reg, tids, spec, output=output, original_tree=original)
