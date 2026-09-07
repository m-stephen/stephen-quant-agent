"""Small synthetic contracts only; empirical attempts are not consumed here."""

import copy
import json
from dataclasses import asdict
from datetime import date, timedelta

import pytest
from test_portfolio_construction import rows

from stephen_quant.discovery import portfolio_construction_runtime as runtime
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.portfolio_construction import contract
from stephen_quant.discovery.portfolio_construction_audit import audit_targets, independent_targets
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def synthetic_spec(root):
    return {
        "version": runtime.VERSION,
        "prior_debt": 3729,
        "budget": 4,
        "new_fits": 0,
        "validated_alpha": False,
        "accounts": runtime.account_plans(),
        "research_contract": contract(),
        "runtime_code_sha256": "a" * 64,
        "completed_parent_evidence_sha256": "b" * 64,
        "history": {
            "root": str(root.resolve()),
            "registry_sha256": "c" * 64,
            "history_sha256": "d" * 64,
            "consumer": "synthetic-lowvol",
        },
    }


def small_history():
    first = date(2023, 11, 15)
    days = [
        (first + timedelta(days=i)).isoformat()
        for i in range(100)
        if (first + timedelta(days=i)).weekday() < 5
    ]
    cross = {d: rows(90) for d in days}
    for j, d in enumerate(days):
        # Migration across cells must not influence a global selector's ranking.
        for row in cross[d].values():
            row["cell"] = (row["cell"] + j) % 20
        if j >= 20:
            for n in list(cross[d])[:7]:
                del cross[d][n]
        if j >= 45:
            cross[d] = {}
    return {"calendar": days, "ranks": cross, "bars": {d: {} for d in days}}


@pytest.mark.parametrize("policy", runtime.POLICIES)
def test_independent_reference_global_lag_four_phases_cash_and_year_carry(policy):
    history = small_history()
    target, diagnostic, _ = runtime.construction_targets(history, policy)
    expected, reference = independent_targets(history, policy)
    assert sha256_json([asdict(t) for t in target]) == sha256_json(expected)
    assert diagnostic == reference
    assert not target[0].rebalance and not target[0].weights
    assert sum(target[1].weights.values()) == pytest.approx(0.25)
    assert target[1].decided_at.startswith(history["calendar"][0])
    assert not target[-1].weights  # Empty current support eventually leaves all sleeves in cash.
    for phase in (0, 5, 10, 15):
        indices = [
            history["calendar"].index(d["execution_date"])
            for d in diagnostic
            if d["phase"] == phase
        ]
        assert indices == list(range(phase + 1, len(target), 20))
    assert any(d["selected_mean_vol"] is None for d in diagnostic)
    assert all(sum(d["selected_cell_counts"]) == d["selected"] for d in diagnostic)


def test_untouched_future_rows_cannot_change_past_targets():
    history = small_history()
    before, _, _ = runtime.construction_targets(history, "global_lowvol")
    future = history["calendar"][30:]
    for d in future:
        for r in history["ranks"][d].values():
            r["vol"] = 10 - r["vol"]
    after, _, _ = runtime.construction_targets(history, "global_lowvol")
    assert before[:31] == after[:31]


@pytest.mark.parametrize("mutation", ("target", "diagnostic", "style"))
def test_independent_audit_rejects_rehashed_wrong_selection_or_telemetry(tmp_path, mutation):
    history = small_history()
    result = {"targets_sha256": {}, "diagnostics": {}}
    for p in runtime.POLICIES:
        targets, diag, _ = runtime.construction_targets(history, p)
        raw = [asdict(t) for t in targets]
        if p == "global_lowvol":
            if mutation == "target":
                raw[1]["weights"] = {"outside-current-support": 0.25}
            elif mutation == "diagnostic":
                diag[0]["new_members"] = 0
            else:
                diag[0]["selected_mean_vol"] += 0.1
        path = tmp_path / f"targets/{p}.json"
        write(path, raw)
        result["targets_sha256"][p] = file_sha(path)
        result["diagnostics"][p] = diag
    with pytest.raises(ValueError, match="independent global"):
        audit_targets(tmp_path, result, history)


def test_complete_native_reservations_and_snapshot_before_source_read(tmp_path):
    spec = synthetic_spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, spec)
    runtime.check_native(reg, output, spec, tids)
    assert reg.global_trial_count() == len(tids) == 4
    assert not (output / "BACKEND_CLAIM.json").exists()
    for tid in tids.values():
        assert not reg.fit_lineage(tid)["stages"]
        assert not reg.feature_sources(tid)["providers"]
    with pytest.raises(FileExistsError):
        runtime.reserve_accounts(output, spec)


@pytest.mark.parametrize(
    "mutation", ("missing", "completed", "policy", "code", "snapshot", "promotion")
)
def test_invalid_native_state_blocks_before_any_numeric_history(tmp_path, monkeypatch, mutation):
    spec = synthetic_spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, spec)
    with reg.connect() as db:
        if mutation == "missing":
            tids.pop(next(iter(tids)))
        elif mutation == "completed":
            db.execute("UPDATE trials SET result_json='{}'")
        elif mutation == "policy":
            db.execute("UPDATE trials SET hyperparams='{}'")
        elif mutation == "code":
            db.execute("UPDATE experiments SET code_version='other'")
        elif mutation == "snapshot":
            spec["history"]["history_sha256"] = "f" * 64
        else:
            spec["validated_alpha"] = True
        db.commit()
    monkeypatch.setattr(runtime, "open_history", lambda *a: pytest.fail("unexpected numeric read"))
    with pytest.raises(ValueError):
        runtime.execute_accounts(reg, tids, spec, output=output)
    assert not (output / "BACKEND_CLAIM.json").exists()


def test_failed_backend_keeps_four_attempts_and_refuses_retry(tmp_path, monkeypatch):
    spec = synthetic_spec(tmp_path / "old")
    output = tmp_path / "new"
    reg, tids = runtime.reserve_accounts(output, spec)

    def fail(*a):
        raise OSError("synthetic unavailable history")

    monkeypatch.setattr(runtime, "open_history", fail)
    with pytest.raises(OSError):
        runtime.execute_accounts(reg, tids, spec, output=output)
    aborted = json.loads((output / "ABORTED.json").read_text())
    assert aborted["reserved_trials"] == 4 and aborted["raw_global_trial_lower_bound"] == 3733
    assert aborted["completed_account_keys"] == [] and not aborted["validated_alpha"]
    with pytest.raises(ValueError):
        runtime.execute_accounts(reg, tids, spec, output=output)
    assert reg.global_trial_count() == 4


@pytest.mark.parametrize("bad", ("2025-01-02", "2021-12-30"))
def test_calendar_scope_rejected_in_both_implementations(bad):
    history = small_history()
    history["calendar"] = sorted(history["calendar"] + [bad])
    for fn in (runtime.construction_targets, independent_targets):
        with pytest.raises(ValueError):
            fn(history, "global_lowvol")


def test_spec_cannot_add_parameter_variants(tmp_path):
    spec = synthetic_spec(tmp_path)
    bad = copy.deepcopy(spec)
    bad["accounts"].append({**bad["accounts"][0], "buffer": 80})
    with pytest.raises(ValueError):
        runtime.reserve_accounts(tmp_path / "new", bad)
