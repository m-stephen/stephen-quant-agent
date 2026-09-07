"""Synthetic one-account recovery gates; never reads real frozen inputs."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_flow_response_tiny_fills import tiny_account

from stephen_quant.discovery import flow_response_diagnostic as m
from stephen_quant.discovery.search_power_dsl import sha256_json


def old_source():
    current = Path(m.flow_response_replay.__file__).read_bytes()
    return current.replace(b"if amount != 0.0:", b"if abs(amount) > 1e-12:")


@pytest.mark.parametrize("liquidation", [False, True])
def test_exact_old_new_account_comparison_explains_first_failure(liquidation):
    sessions, targets, report = tiny_account(liquidation=liquidation)
    result = m.compare_auditors(report, sessions, targets, old_source())
    assert result["engineering_pass"] and not result["validated_alpha"]
    assert result["original_audit"]["reproduced"]
    assert result["original_audit"]["first_divergence"]["explained"]
    assert result["corrected_audit"]["pass"]
    assert result["tiny_fills"]


def test_not_reproduced_cannot_be_declared_solved():
    sessions, targets, report = tiny_account(liquidation=True)
    current = Path(m.flow_response_replay.__file__).read_bytes()
    result = m.compare_auditors(report, sessions, targets, current)
    assert not result["original_audit"]["reproduced"]
    assert result["corrected_audit"]["pass"] and not result["engineering_pass"]


def test_new_audit_failure_keeps_diagnosis_unresolved():
    sessions, targets, report = tiny_account(liquidation=True)
    periods = list(report.periods)
    periods[-1] = replace(periods[-1], cash=periods[-1].cash + 100)
    result = m.compare_auditors(
        replace(report, periods=tuple(periods)), sessions, targets, old_source()
    )
    assert result["original_audit"]["reproduced"]
    assert not result["corrected_audit"]["pass"] and not result["engineering_pass"]


def test_exact_auditor_change_rejects_any_threshold_or_other_logic_change():
    current = Path(m.flow_response_replay.__file__).read_bytes()
    m.verify_only_fill_condition_changed(old_source(), current)
    with pytest.raises(ValueError, match="only"):
        m.verify_only_fill_condition_changed(
            old_source(), current.replace(b"atol=1e-7", b"atol=1e-3")
        )


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "worktree"
    root.mkdir()
    plan = {
        "version": m.VERSION,
        "claim_key": m.CLAIM_KEY,
        "paths": {"worktree": str(root), "claim": str(tmp_path / "common/once.json")},
        "code": {"sha256": "a" * 64},
        "contract": {"key": "risk-82", "roundtrip_bps": 82},
        "failed003": {
            "inventory_sha256": "b" * 64,
            "files": {
                "history/history.json": {"sha256": "c" * 64},
                "targets/risk.json": {"sha256": "d" * 64},
                "registry.sqlite3": {"sha256": "e" * 64},
            },
        },
        "prior_debt": 3706,
        "budget": 1,
        "validated_alpha": False,
    }
    expected = copy.deepcopy(plan)
    monkeypatch.setattr(m, "prepare_diagnostic", lambda _: copy.deepcopy(expected))
    monkeypatch.setattr(m, "fetch_preregistration", lambda i, d, _: {"id": i, "plan_sha256": d})
    monkeypatch.setattr(m, "_resource_preflight", lambda: {"physical_available_bytes": 8 * 1024**3})
    path = root / "plan.json"
    m.write(path, plan)
    return root, path, plan


@pytest.mark.parametrize(
    "field,value", [("prior_debt", 0), ("budget", 0), ("validated_alpha", True)]
)
def test_changed_plan_refused_before_claim(fixture, field, value):
    root, path, plan = fixture
    plan[field] = value
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="differs"):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("stage", ["fetch_preregistration", "_resource_preflight"])
def test_preflight_refusal_does_not_consume_attempt(fixture, monkeypatch, stage):
    root, path, plan = fixture

    def deny(*a, **kw):
        raise ValueError("synthetic preflight refusal")

    monkeypatch.setattr(m, stage, deny)
    with pytest.raises(ValueError, match="refusal"):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    assert not Path(plan["paths"]["claim"]).exists()


@pytest.mark.parametrize("outcome", ["FAILED", "GUARD_STOPPED", "PRELAUNCH_REFUSED"])
def test_claim_native_reservation_precede_child_and_failure_cannot_replay(
    fixture, monkeypatch, outcome
):
    root, path, plan = fixture
    claim = Path(plan["paths"]["claim"])
    output = m._operation(plan, sha256_json(plan))
    calls = []

    def child(command, **kw):
        calls.append(command)
        assert claim.exists()
        registry = m.ReadOnlyRegistry(output / "registry.sqlite3")
        assert registry.global_trial_count() == 1
        with registry.connect() as db:
            tid = db.execute("SELECT trial_id FROM trials").fetchone()[0]
        assert not registry.fit_lineage(tid)["stages"]
        assert not registry.feature_sources(tid)["providers"]
        return {"outcome": outcome}

    monkeypatch.setattr(m, "supervise", child)
    with pytest.raises(RuntimeError, match="no retry"):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    terminal = m.read(claim.with_name("once.terminal.json"))
    assert terminal["raw_global_trial_lower_bound"] == 3707
    assert terminal["committed_attempt_budget"] == terminal["native_reserved"] == 1
    with pytest.raises(FileExistsError):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    assert len(calls) == 1


def test_reservation_exception_retains_budget(fixture, monkeypatch):
    root, path, plan = fixture

    def fail(*a):
        raise OSError("synthetic reservation failure")

    monkeypatch.setattr(m, "reserve_diagnostic", fail)
    with pytest.raises(OSError):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    receipt = m.read(claim.with_name("once.terminal.json"))
    assert (
        receipt["committed_attempt_budget"] == 1 and receipt["raw_global_trial_lower_bound"] == 3707
    )
    assert receipt["native_reserved"] == 0


def test_diagnostic_native_snapshot_binds_saved_inputs_and_no_fit(fixture):
    _, _, plan = fixture
    output = m._operation(plan, sha256_json(plan))
    output.mkdir(parents=True)
    registry, tid = m.reserve_diagnostic(output, plan)
    with registry.connect() as db:
        hp, result = db.execute(
            "SELECT hyperparams,result_json FROM trials WHERE trial_id=?", (tid,)
        ).fetchone()
    assert json.loads(hp) == plan["contract"] and result is None
    assert not registry.fit_lineage(tid)["stages"]
    with pytest.raises(FileExistsError):
        m.reserve_diagnostic(output, plan)


def test_partial_reservation_reports_actual_native_count(fixture, monkeypatch):
    root, path, plan = fixture
    actual = m.reserve_diagnostic

    def fail(output, frozen):
        actual(output, frozen)
        raise OSError("synthetic failure after reservation")

    monkeypatch.setattr(m, "reserve_diagnostic", fail)
    with pytest.raises(OSError):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
    claim = Path(plan["paths"]["claim"])
    receipt = m.read(claim.with_name("once.terminal.json"))
    assert receipt["native_reserved"] == 1 and receipt["raw_global_trial_lower_bound"] == 3707


@pytest.mark.parametrize("kind", ["child_claim", "terminal", "receipt", "native_plan"])
def test_child_refuses_replay_or_mutation_before_numeric_read(fixture, monkeypatch, kind):
    root, path, plan = fixture

    def stage(command, **kwargs):
        output = Path(command[-1])
        if kind == "child_claim":
            m.write(output / "CHILD.json", {"already_consumed": True})
        elif kind == "terminal":
            claim = Path(plan["paths"]["claim"])
            m.write(claim.with_name("once.terminal.json"), {"outcome": "FAILED"})
        elif kind == "receipt":
            value = m.read(output / "RESERVATIONS.json")
            value["debt"] = 0
            (output / "RESERVATIONS.json").write_text(json.dumps(value))
        else:
            with m.ExperimentRegistry(output / "registry.sqlite3").connect() as db:
                db.execute("UPDATE trials SET hyperparams='{}'")

        def forbidden(*a, **kw):
            raise AssertionError("numeric history read before complete gates")

        monkeypatch.setattr(m, "read_verified_history", forbidden)
        with pytest.raises((ValueError, FileExistsError)):
            m.run_diagnostic_child(output, root)
        if kind == "terminal":
            # Synthetic fixture cleanup only, so the parent can save its actual terminal.
            Path(plan["paths"]["claim"]).with_name("once.terminal.json").unlink()
        return {"outcome": "FAILED"}

    monkeypatch.setattr(m, "supervise", stage)
    with pytest.raises(RuntimeError):
        m.launch_diagnostic(path, comment_id=1, worktree=root)
