"""Synthetic launch gates; lifecycle stubs do not claim a numerical recovery test."""

import copy
import json
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest
from test_flow_response_failure import failed_fixture

from stephen_quant.discovery import flow_response_launch as m
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    paths = {k: tmp_path / k for k in ("worktree", "parent", "inputs", "original")}
    for p in paths.values():
        p.mkdir()
    paths["claim"] = tmp_path / "common/claims/once.json"
    paths["failed_epoch"], paths["failed_claim"] = failed_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(m, "layout", lambda _: paths)
    monkeypatch.setattr(m, "code_evidence", lambda _: {"sha256": "c" * 64, "commit": "1" * 40})
    calendar = [str(date(2022, 1, 3) + timedelta(days=i)) for i in range(64)]
    calendar += ["2023-01-03", "2023-01-04", "2024-01-02", "2024-01-03"]
    sources = []
    for name in ("daily", "fund_flow", "auction", "chip", "minute"):
        path = paths["inputs"] / f"{name}.parquet"
        if name in ("daily", "fund_flow"):
            with duckdb.connect(":memory:") as db:
                db.execute("CREATE TABLE source(trade_date DATE,close VARCHAR)")
                db.executemany("INSERT INTO source VALUES (?,?)", [(d, "POISON") for d in calendar])
                db.execute("COPY source TO ? (FORMAT PARQUET)", [str(path)])
            digest = file_sha(path)
        else:
            digest = "0" * 64  # These three files deliberately do not exist.
        sources.append(
            {"source": name, "file": path.name, "sha256": digest, "max_date": calendar[-1]}
        )
    snapshot = sha256_json(sources)
    monkeypatch.setattr(m, "SNAPSHOT_SHA", snapshot)
    m.write(
        paths["inputs"] / "manifest.json",
        {
            "sources": sources,
            "snapshot_sha256": snapshot,
            "exposed_sealed_rows": 0,
        },
    )
    card = {"targets_file_sha256": {}}
    for name in ("lowvol", "stable_lowrisk"):
        target = paths["original"] / f"artifacts/temporal-increments/epoch-001/targets/{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not-json:weights-must-not-be-decoded-in-prepare")
        card["targets_file_sha256"][name] = file_sha(target)
    card_path = paths["original"] / "configs/v11.11-frozen-stability-observation.json"
    m.write(card_path, card)
    monkeypatch.setattr(m, "CARD_SHA", file_sha(card_path))
    parent = paths["parent"]
    m.write(parent / "inherited_lineage.json", {"prior_debt": 3648, "test": "synthetic"})
    spec = {
        "plans": [{"key": f"synthetic-{n}"} for n in range(12)],
        "runtime_code_sha256": "a" * 64,
    }
    records = {
        p["key"]: {
            "key": p["key"],
            "fit_lineage_sha256": sha256_json([]),
            "inherited_receipt_sha256": file_sha(parent / "inherited_lineage.json"),
        }
        for p in spec["plans"]
    }
    with sqlite3.connect(parent / "registry.sqlite3") as db:
        db.executescript("""
        CREATE TABLE trials(trial_id TEXT,hyperparams TEXT,result_json TEXT,experiment_id TEXT);
        CREATE TABLE trial_fit_contracts(trial_id TEXT,stages_json TEXT);
        CREATE TABLE experiments(experiment_id TEXT,code_version TEXT,search_space TEXT);
        CREATE TABLE trial_model_fits(trial_id TEXT);
        """)
        db.execute("INSERT INTO experiments VALUES (?,?,?)", ("e", "a" * 64, json.dumps(spec)))
        for i, p in enumerate(spec["plans"]):
            db.execute(
                "INSERT INTO trials VALUES (?,?,?,?)",
                (str(i), json.dumps(p), json.dumps(records[p["key"]]), "e"),
            )
            db.execute("INSERT INTO trial_fit_contracts VALUES (?,?)", (str(i), "[]"))
    m.write(parent / "frozen_spec.json", spec)
    m.write(parent / "first_read_reservations.json", {"reserved": 12})
    result = {
        "raw_global_trial_lower_bound": 3660,
        "completed_trials": 12,
        "reserved_trials": 12,
        "engineering_pass": True,
        "protected_unchanged": True,
        "validated_alpha": False,
        "screen_survived": {"linear": False, "quadratic": False},
        "spec": spec,
        "records": records,
    }
    m.write(parent / "RESULT.json", result)
    monkeypatch.setattr(m, "PARENT_SHA", file_sha(parent / "RESULT.json"))
    m.write(
        parent / "INDEPENDENT_AUDIT.json",
        {
            "pass": True,
            "evidence_hashes": {p.name: file_sha(p) for p in parent.iterdir()},
        },
    )
    monkeypatch.setattr(m, "AUDIT_SHA", file_sha(parent / "INDEPENDENT_AUDIT.json"))
    plan = m.prepare_plan(paths["worktree"])
    plan_path = paths["worktree"] / "artifacts/flow-response/PLAN.json"
    m.write(plan_path, plan)
    monkeypatch.setattr(
        m, "fetch_preregistration", lambda ident, digest, _: {"id": ident, "plan_sha256": digest}
    )
    monkeypatch.setattr(m, "_resource_preflight", lambda: {"physical_available_bytes": 8 * 1024**3})
    return paths, plan, plan_path


def test_prepare_uses_only_dates_two_files_and_target_hashes_without_claim(fixture):
    paths, plan, _ = fixture
    assert set(plan["evidence"]["sources"]) == {
        "manifest.json",
        "daily.parquet",
        "fund_flow.parquet",
    }
    assert {d[:4] for d in plan["spec"]["calendar"]} == {"2022", "2023", "2024"}
    assert not paths["claim"].exists()
    assert not (paths["worktree"] / "artifacts/flow-response/epochs").exists()
    assert plan["committed_attempt_budget"] == 23 and plan["parent_debt"] == 3683
    assert plan["evidence"]["failed_epoch"]["consumed_attempts"] == 23
    assert plan["spec"]["failed_epoch_evidence_sha256"] == sha256_json(
        plan["evidence"]["failed_epoch"]
    )
    assert m.verify_plan(plan, paths["worktree"]) == sha256_json(plan)


@pytest.mark.parametrize(
    "key,relative",
    [
        ("parent", "registry.sqlite3"),
        ("parent", "RESULT.json"),
        ("parent", "INDEPENDENT_AUDIT.json"),
        ("inputs", "manifest.json"),
        ("inputs", "daily.parquet"),
        ("inputs", "fund_flow.parquet"),
        ("original", "artifacts/temporal-increments/epoch-001/targets/lowvol.json"),
        ("failed_epoch", "registry.sqlite3"),
        ("failed_epoch", "RESERVATIONS.json"),
    ],
)
def test_changed_frozen_bytes_refuse_before_claim_or_numeric_access(fixture, key, relative):
    paths, _, plan_path = fixture
    path = paths[key] / relative
    path.write_bytes(path.read_bytes() + b"mutated")
    with pytest.raises(ValueError):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert not paths["claim"].exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("parent_debt", 0),
        ("committed_attempt_budget", 1),
        ("validated_alpha", True),
        ("limits", {"private_commit_bytes": 999}),
    ],
)
def test_plan_knobs_cannot_bypass_frozen_protocol(fixture, field, value):
    paths, plan, plan_path = fixture
    plan[field] = value
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="plan differs"):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert not paths["claim"].exists()


def test_readonly_registry_cannot_initialize_or_modify_parent(fixture):
    paths, _, _ = fixture
    path = paths["parent"] / "registry.sqlite3"
    before = file_sha(path)
    registry = m.ReadOnlyRegistry(path)
    assert registry.global_trial_count() == 12
    with registry.connect() as db, pytest.raises(sqlite3.OperationalError):
        db.execute("DELETE FROM trials")
    assert file_sha(path) == before


def test_resource_refusal_does_not_claim_or_reserve(fixture, monkeypatch):
    paths, _, plan_path = fixture

    def fail():
        raise ValueError("low RAM")

    monkeypatch.setattr(m, "_resource_preflight", fail)
    with pytest.raises(ValueError, match="low RAM"):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert not paths["claim"].exists()


@pytest.mark.parametrize(
    "outcome", ["GUARD_STOPPED", "FAILED", "PRELAUNCH_REFUSED", "TERMINATION_FAILED"]
)
def test_failed_backend_keeps_all23_and_prevents_other_operation(fixture, monkeypatch, outcome):
    paths, plan, plan_path = fixture
    calls = []

    def stop(command, **kwargs):
        calls.append(command[2])
        assert paths["claim"].exists()
        operation = m._operation(plan, sha256_json(plan))
        assert m.ReadOnlyRegistry(operation / "registry.sqlite3").global_trial_count() == 23
        return {"outcome": outcome}

    monkeypatch.setattr(m, "supervise", stop)
    with pytest.raises(RuntimeError, match="no retry"):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert calls == ["backend"]
    terminal = m.read(paths["claim"].with_name("once.terminal.json"))
    assert terminal["committed_attempt_budget"] == terminal["native_reserved"] == 23
    assert terminal["raw_global_trial_lower_bound"] == 3706
    assert terminal["outcome"] == "FAILED" and terminal["exception_type"] == "RuntimeError"
    # A different worktree and therefore different plan/output cannot reset the global parent claim.
    paths["worktree"] = paths["worktree"].parent / "second-worktree"
    paths["worktree"].mkdir()
    second = m.prepare_plan(paths["worktree"])
    other = paths["worktree"] / "PLAN.json"
    m.write(other, second)
    with pytest.raises(FileExistsError):
        m.launch(other, comment_id=2, worktree=paths["worktree"])
    assert calls == ["backend"]


def test_reservation_failure_retains_claim_and_honest_native_count(fixture, monkeypatch):
    paths, _, plan_path = fixture

    def fail(output, spec):
        assert paths["claim"].exists()
        (output / "registry.sqlite3").write_bytes(b"incomplete sqlite file")
        raise RuntimeError("reservation failed before any numerical computation")

    monkeypatch.setattr(m, "reserve_trials", fail)
    with pytest.raises(RuntimeError, match="reservation failed"):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    terminal = m.read(paths["claim"].with_name("once.terminal.json"))
    assert terminal["native_reserved"] is None
    assert terminal["native_count_error"] == "DatabaseError"
    assert terminal["committed_attempt_budget"] == 23


def test_two_stage_lifecycle_waits_for_verified_producer_exit(fixture, monkeypatch):
    import stephen_quant.discovery.flow_response_epoch_audit as audit_module
    import stephen_quant.workflows.flow_response_epoch as backend_module

    paths, plan, plan_path = fixture
    events = []

    def backend(registry, tids, spec, *, output, **kwargs):
        assert m.check_complete_reservations(registry, tids)["reserved"] == 23
        events.append("backend-numeric-stub")
        m.write(
            output / "RESULT.json",
            {
                "status": "COMPLETE_PENDING_INDEPENDENT_AUDIT",
                "records": {},
                "diagnostics": {},
            },
        )

    def audit(registry, *, operation, **kwargs):
        assert isinstance(registry, m.ReadOnlyRegistry)
        assert events == ["spawn-backend", "backend-numeric-stub", "exit-backend", "spawn-audit"]
        assert m.read(operation / "supervisor-backend/SUPERVISOR.json")["outcome"] == "COMPLETED"
        events.append("audit-numeric-stub")
        return {"pipeline_audit_pass": True, "validated_alpha": False}

    def supervised(command, **kwargs):
        stage = command[2]
        events.append("spawn-" + stage)
        m.run_stage(stage, operation=command[4], worktree=paths["worktree"])
        events.append("exit-" + stage)
        receipt = {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
        m.write(kwargs["output"] / "SUPERVISOR.json", receipt)
        return receipt

    monkeypatch.setattr(backend_module, "execute_reserved_epoch", backend)
    monkeypatch.setattr(audit_module, "audit_complete_epoch", audit)
    monkeypatch.setattr(
        m,
        "screen_records",
        lambda *args, **kw: {"validated_alpha": False, "screen_survived": {"response": False}},
    )
    monkeypatch.setattr(m, "supervise", supervised)
    result = m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert result["outcome"] == "COMPLETE_EXPLORATORY_AUDITED"
    assert not result["validated_alpha"] and result["native_reserved"] == 23
    root = m._operation(plan, sha256_json(plan))
    assert m.read(root / "RESULT.json")["status"] == "COMPLETE_PENDING_INDEPENDENT_AUDIT"
    assert (root / "AUDIT.json").exists() and (root / "ASSESSMENT.json").exists()
    with pytest.raises(ValueError, match="active global"):
        m.run_stage("backend", operation=root, worktree=paths["worktree"])


@pytest.mark.parametrize("mutation", ["issue", "hash", "id", "future", "naive"])
def test_preregistration_is_fetched_from_fixed_api_and_checked(tmp_path, monkeypatch, mutation):
    value = {
        "id": 99,
        "issue_url": m.ISSUE_URL,
        "body": "V11.21-PREREGISTRATION-SHA256: " + "a" * 64,
        "created_at": "2022-01-01T00:00:00Z",
        "updated_at": "2022-01-01T00:00:00Z",
    }
    if mutation == "issue":
        value["issue_url"] = m.ISSUE_URL + "0"
    elif mutation == "hash":
        value["body"] = "V11.21-PREREGISTRATION-SHA256: " + "b" * 64
    elif mutation == "id":
        value["id"] = 98
    elif mutation == "future":
        value["updated_at"] = "2099-01-01T00:00:00Z"
    else:
        value["updated_at"] = "2022-01-01T00:00:00"

    def response(command, **kwargs):
        assert command == [
            "gh",
            "api",
            "--hostname",
            "github.com",
            f"repos/{m.REPO}/issues/comments/99",
        ]
        assert not {k.upper() for k in kwargs["env"]} & m._SECRETS
        return json.dumps(value).encode()

    monkeypatch.setattr(subprocess, "check_output", response)
    with pytest.raises(ValueError, match="preregistration"):
        m.fetch_preregistration(99, "a" * 64, tmp_path)


def test_clean_code_checked_before_opening_source(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "_git", lambda *args: " M dirty.py")
    with pytest.raises(ValueError, match="clean committed"):
        m.code_evidence(tmp_path)


def test_worktrees_share_claim_location_from_common_git_directory(tmp_path, monkeypatch):
    common = tmp_path / ".git"
    common.mkdir()
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setattr(
        m, "_git", lambda root, *args: str(root if args[-1] == "--show-toplevel" else common)
    )
    first, second = m.layout(a), m.layout(b)
    assert first["claim"] == second["claim"]
    assert first["worktree"] != second["worktree"]
    assert first["parent"] == second["parent"]


def test_verified_plan_detects_missing_controls_and_runtime_change(fixture, monkeypatch):
    paths, plan, _ = fixture
    copy_plan = copy.deepcopy(plan)
    copy_plan["spec"]["plans"].pop()
    with pytest.raises(ValueError, match="plan differs"):
        m.verify_plan(copy_plan, paths["worktree"])
    monkeypatch.setattr(m, "code_evidence", lambda _: {"sha256": "d" * 64, "commit": "2" * 40})
    with pytest.raises(ValueError, match="plan differs"):
        m.verify_plan(plan, paths["worktree"])


@pytest.mark.parametrize("mutation", ["comment", "claim", "reservations", "trial_id"])
def test_child_refuses_modified_launch_evidence_before_numeric_call(fixture, monkeypatch, mutation):
    import stephen_quant.workflows.flow_response_epoch as backend_module

    paths, _, plan_path = fixture
    numeric = []
    monkeypatch.setattr(
        backend_module, "execute_reserved_epoch", lambda *a, **kw: numeric.append(True)
    )

    def intervene(command, **kwargs):
        root = Path(command[4])
        if mutation == "comment":
            path = root / "PREREGISTRATION.json"
            value = m.read(path) | {"tampered": True}
        elif mutation == "claim":
            path = paths["claim"]
            value = m.read(path) | {"committed_attempt_budget": 1}
        else:
            path = root / "RESERVATIONS.json"
            value = m.read(path)
            if mutation == "reservations":
                value["reserved"] = 22
            else:
                value["trial_ids"]["response-82"] = "missing-native-trial"
                value["native_trial_ids_sha256"] = sha256_json(value["trial_ids"])
        path.write_text(json.dumps(value), encoding="utf-8")
        m.run_stage("backend", operation=root, worktree=paths["worktree"])
        raise AssertionError("corrupted launch evidence reached the end")

    monkeypatch.setattr(m, "supervise", intervene)
    with pytest.raises(ValueError):
        m.launch(plan_path, comment_id=1, worktree=paths["worktree"])
    assert numeric == []
    assert m.read(paths["claim"].with_name("once.terminal.json"))["native_reserved"] == 23


def test_preregistration_success_and_network_failure_are_not_caller_callbacks(
    tmp_path, monkeypatch
):
    payload = {
        "id": 99,
        "issue_url": m.ISSUE_URL,
        "body": "Discussion\nV11.21-PREREGISTRATION-SHA256: " + "a" * 64,
        "created_at": "2022-01-01T00:00:00Z",
        "updated_at": "2022-01-01T00:00:00Z",
    }
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: json.dumps(payload).encode())
    evidence = m.fetch_preregistration(99, "a" * 64, tmp_path)
    assert evidence["comment"] == payload and evidence["plan_sha256"] == "a" * 64
    assert evidence["fetched_at"].endswith("+00:00")

    def unavailable(*args, **kwargs):
        raise OSError("synthetic offline")

    monkeypatch.setattr(subprocess, "check_output", unavailable)
    with pytest.raises(ValueError, match="no launch"):
        m.fetch_preregistration(99, "a" * 64, tmp_path)


def test_real_git_worktrees_share_the_claim_location(tmp_path):
    import shutil

    if shutil.which("git") is None:
        pytest.skip("Git is unavailable")
    repository, second = tmp_path / "repository", tmp_path / "second"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=Synthetic Test",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "worktree",
            "add",
            "-q",
            "-b",
            "synthetic-second",
            str(second),
        ],
        check=True,
        capture_output=True,
    )
    assert m.layout(repository)["claim"] == m.layout(second)["claim"]
