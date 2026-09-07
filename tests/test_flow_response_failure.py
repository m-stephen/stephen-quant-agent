import json
import sqlite3

import pytest

from stephen_quant.discovery import flow_response_failure as m
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def put(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def failed_fixture(tmp_path, monkeypatch):
    """Synthetic lifecycle, no real sources, and real read-only SQLite verification."""
    root, claim = tmp_path / "failed", tmp_path / "common/failed.json"
    root.mkdir(parents=True)
    spec = {
        "runtime_code_sha256": "f" * 64,
        "manifest_sha256": "d" * 64,
        "calendar": ["2022-01-03", "2023-01-03", "2024-01-02"],
        "plans": [{"key": f"synthetic-{i}"} for i in range(23)],
    }
    plan = {
        "spec": spec,
        "paths": {"claim": str(claim)},
        "claim_key": "c" * 64,
        "evidence": {"code": {"sha256": "f" * 64}},
    }
    digest = sha256_json(plan)
    prereg = {"plan_sha256": digest, "comment": "synthetic only"}
    put(
        claim,
        {
            "operation": str(root),
            "plan_sha256": digest,
            "preregistration_sha256": sha256_json(prereg),
            "prior_debt": 3660,
            "committed_attempt_budget": 23,
            "claimed_at": "2026-09-07T01:00:00+00:00",
        },
    )
    claim_sha = file_sha(claim)
    put(root / "LAUNCH.json", {"plan": plan, "claim_sha256": claim_sha})
    put(root / "frozen_spec.json", spec)
    put(root / "PREREGISTRATION.json", prereg)
    tids = {p["key"]: f"trial-{i}" for i, p in enumerate(spec["plans"])}
    proof = {
        "native_trial_ids_sha256": sha256_json(tids),
        "reserved": 23,
        "prior_debt": 3660,
        "debt": 3683,
    }
    put(root / "RESERVATIONS.json", proof | {"trial_ids": tids})
    put(root / "first_read_reservations.json", proof | {"trials": tids})
    put(
        root / "CHILD_backend.json",
        {"plan_sha256": digest, "started_at": "2026-09-07T01:00:01+00:00"},
    )
    put(
        root / "supervisor-backend/SUPERVISOR.json",
        {
            "outcome": "FAILED",
            "exit_code": 1,
            "evidence_hashes": {
                "claim": claim_sha,
                "plan": digest,
                "preregistration": sha256_json(prereg),
            },
        },
    )
    put(root / "supervisor-backend/process.log", "synthetic source-join failure")
    terminal = claim.with_name("failed.terminal.json")
    put(
        terminal,
        {
            "plan_sha256": digest,
            "outcome": "FAILED",
            "last_stage": "backend",
            "native_reserved": 23,
            "committed_attempt_budget": 23,
            "raw_global_trial_lower_bound": 3683,
            "automatic_retry": False,
            "validated_alpha": False,
            "finished_at": "2026-09-07T01:01:00+00:00",
        },
    )
    with sqlite3.connect(root / "registry.sqlite3") as db:
        db.executescript("""
            CREATE TABLE trials(trial_id TEXT,hyperparams TEXT,result_json TEXT,experiment_id TEXT);
            CREATE TABLE experiments(experiment_id TEXT,code_version TEXT,search_space TEXT);
            CREATE TABLE trial_model_fits(trial_id TEXT);
        """)
        db.execute("INSERT INTO experiments VALUES (?,?,?)", ("e", "f" * 64, json.dumps(spec)))
        for p in spec["plans"]:
            params = p | {
                "response_history_version": "11.21-response-history-1",
                "response_manifest_sha256": spec["manifest_sha256"],
                "response_calendar_sha256": sha256_json(spec["calendar"]),
            }
            db.execute(
                "INSERT INTO trials VALUES (?,?,?,?)",
                (tids[p["key"]], json.dumps(params), None, "e"),
            )
    for name, value in {
        "FAILED_PLAN_SHA": digest,
        "FAILED_CLAIM_KEY": "c" * 64,
        "FAILED_CODE_SHA": "f" * 64,
        "FAILED_IDS_SHA": sha256_json(tids),
        "CLAIM_SHA": claim_sha,
        "TERMINAL_SHA": file_sha(terminal),
        "FILES": {n: file_sha(root / n) for n in m.FILES},
    }.items():
        monkeypatch.setattr(m, name, value)
    return root, claim


def test_failed_native_inheritance_is_readonly_and_never_resets_debt(tmp_path, monkeypatch):
    root, claim = failed_fixture(tmp_path, monkeypatch)
    before = file_sha(root / "registry.sqlite3")
    evidence = m.failed_epoch_evidence(root, claim)
    assert (
        evidence["prior_debt"] + evidence["consumed_attempts"] == evidence["inherited_debt"] == 3683
    )
    assert evidence["actual_fits"] == evidence["completed_results"] == 0
    assert file_sha(root / "registry.sqlite3") == before


@pytest.mark.parametrize("name", list(m.FILES))
def test_changed_failed_evidence_bytes_rejected(tmp_path, monkeypatch, name):
    root, claim = failed_fixture(tmp_path, monkeypatch)
    path = root / name
    path.write_bytes(path.read_bytes() + b"mutated")
    with pytest.raises(ValueError, match="evidence changed"):
        m.failed_epoch_evidence(root, claim)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "result", "fit", "source", "code"])
def test_native_crosschecks_even_if_database_hash_is_reissued(tmp_path, monkeypatch, kind):
    root, claim = failed_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(root / "registry.sqlite3") as db:
        if kind == "missing":
            db.execute("DELETE FROM trials WHERE trial_id='trial-0'")
        elif kind == "duplicate":
            db.execute("UPDATE trials SET trial_id='trial-0' WHERE trial_id='trial-1'")
        elif kind == "result":
            db.execute("UPDATE trials SET result_json='{}' WHERE trial_id='trial-0'")
        elif kind == "fit":
            db.execute("INSERT INTO trial_model_fits VALUES ('trial-0')")
        elif kind == "source":
            raw = db.execute("SELECT hyperparams FROM trials WHERE trial_id='trial-0'").fetchone()[
                0
            ]
            p = json.loads(raw)
            p["response_manifest_sha256"] = "0" * 64
            db.execute("UPDATE trials SET hyperparams=? WHERE trial_id='trial-0'", (json.dumps(p),))
        else:
            db.execute("UPDATE experiments SET code_version='changed'")
    monkeypatch.setattr(
        m, "FILES", m.FILES | {"registry.sqlite3": file_sha(root / "registry.sqlite3")}
    )
    with pytest.raises(ValueError, match="failed native"):
        m.failed_epoch_evidence(root, claim)


@pytest.mark.parametrize("kind", ["debt", "success", "naive", "completed_file", "ids"])
def test_inconsistent_failure_receipts_rejected(tmp_path, monkeypatch, kind):
    root, claim = failed_fixture(tmp_path, monkeypatch)
    terminal = claim.with_name("failed.terminal.json")
    if kind == "completed_file":
        put(root / "RESULT.json", {})
    elif kind == "ids":
        path = root / "first_read_reservations.json"
        p = json.loads(path.read_bytes())
        p["trials"].pop("synthetic-0")
        put(path, p)
        monkeypatch.setattr(m, "FILES", m.FILES | {path.name: file_sha(path)})
    else:
        p = json.loads(terminal.read_bytes())
        if kind == "debt":
            p["raw_global_trial_lower_bound"] = 3660
        elif kind == "success":
            p["outcome"] = "COMPLETED"
        else:
            p["finished_at"] = "2026-09-07T01:01:00"
        put(terminal, p)
        monkeypatch.setattr(m, "TERMINAL_SHA", file_sha(terminal))
    with pytest.raises(ValueError):
        m.failed_epoch_evidence(root, claim)
