"""Once-only frozen risk-82 failure diagnosis, not another factor search.

The old operation is read-only. One new native no-fit replay is counted before
decoding its history/targets; no other policy outcome is decoded or selected.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.reliable_panel import file_sha

from . import flow_response_replay
from .flow_response_accounts import execute_response_account
from .flow_response_failure import failed_epoch_evidence
from .flow_response_history import read_verified_history
from .flow_response_launch import (
    ISSUE_URL,
    LIMITS,
    ReadOnlyRegistry,
    _bound,
    _env,
    _resource_preflight,
    code_evidence,
    fetch_preregistration,
    layout,
    now,
    parent_evidence,
    read,
    write,
)
from .flow_response_views import HistoricalSessions
from .gross_net_attribution import frozen_targets
from .response_supervisor import supervise
from .search_power_dsl import sha256_json

VERSION = "11.21-risk-account-diagnostic-1"
FAILED_PLAN = "5f1ed422c1397eec233421adbc8bd2ab8275c855791db6444f455f5f38776c6d"
FAILED_CLAIM = "108769778429696edeb7a144ba545af01af277f4f722bbb15794b2f3808e8478"
INVENTORY_SHA = "e16af5320d5b0367437540ef0319f5f7e20d1983c56e30e5a25f57ee4da22946"
OLD_COMMIT = "3e9fd0d3678f7982438b21388f08cd520e448c46"
REPLAY_FILE = "src/stephen_quant/discovery/flow_response_replay.py"
OLD_REPLAY_SHA = "747b1416cf78877ce0971decb3553fd503d59edb4b22177a109c9e526b638a1b"
DRIVER = "scripts/diagnose_flow_response_account.py"
CLAIM_KEY = sha256_json({"version": VERSION, "failed_plan": FAILED_PLAN})
PRIOR_DEBT, BUDGET = 3706, 1


def old_auditor_bytes(root):
    raw = subprocess.check_output(
        ["git", "-C", str(root), "show", f"{OLD_COMMIT}:{REPLAY_FILE}"],
        env=_env(),
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if hashlib.sha256(raw).hexdigest() != OLD_REPLAY_SHA:
        raise ValueError("actual original auditor bytes required")
    return raw


def verify_only_fill_condition_changed(old, current):
    before, after = "if abs(amount) > 1e-12:", "if amount != 0.0:"
    text = old.decode("utf-8")
    if text.count(before) != 1 or ast.dump(ast.parse(text.replace(before, after))) != ast.dump(
        ast.parse(current.decode("utf-8"))
    ):
        raise ValueError("auditors must differ only in nonzero-fill condition")


def _paths(worktree):
    paths = layout(worktree)
    common_artifacts = paths["claim"].parents[1]
    paths["old_operation"] = (
        common_artifacts
        / f"worktrees/v11.21-flow-response/artifacts/flow-response/epochs/{FAILED_PLAN}"
    )
    paths["inventory"] = (
        common_artifacts
        / "worktrees/v11.21-flow-response/artifacts/flow-response/checkpoints/b16-failed-account-inventory.json"
    )
    paths["old_claim"] = paths["claim"].with_name(FAILED_CLAIM + ".json")
    paths["claim"] = paths["claim"].with_name(CLAIM_KEY + ".json")
    return paths


def failed_account_evidence(paths):
    root, inventory_path = paths["old_operation"], paths["inventory"]
    if file_sha(inventory_path) != INVENTORY_SHA:
        raise ValueError("fixed failed-account inventory required")
    inventory = read(inventory_path)
    for name, item in inventory["files"].items():
        _bound(root, name, item["sha256"])
        if (root / name).stat().st_size != item["bytes"]:
            raise ValueError("failed-account evidence size changed")
    claim_path = paths["old_claim"]
    terminal_path = claim_path.with_name(claim_path.stem + ".terminal.json")
    _bound(claim_path.parent, claim_path.name, inventory["claim_sha256"])
    _bound(claim_path.parent, terminal_path.name, inventory["terminal_sha256"])
    terminal, launch = read(terminal_path), read(root / "LAUNCH.json")
    reservation = read(root / "RESERVATIONS.json")
    if (
        sha256_json(launch["plan"]) != FAILED_PLAN
        or terminal["outcome"] != "FAILED"
        or terminal["raw_global_trial_lower_bound"] != PRIOR_DEBT
        or terminal["native_reserved"] != 23
        or terminal["committed_attempt_budget"] != 23
        or (root / "RESULT.json").exists()
        or (root / "CHILD_audit.json").exists()
    ):
        raise ValueError("consumed partial failure with full inherited debt required")
    registry = ReadOnlyRegistry(root / "registry.sqlite3")
    with registry.connect() as db:
        rows = db.execute(
            "SELECT trial_id,hyperparams,result_json IS NOT NULL FROM trials"
        ).fetchall()
        fits = db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]
    keys = {json.loads(hp)["key"]: (tid, complete) for tid, hp, complete in rows}
    if (
        len(rows) != 23
        or len(keys) != 23
        or fits != 692
        or sorted(k for k, (_, complete) in keys.items() if complete)
        != inventory["completed_native_keys"]
        or {k: v[0] for k, v in keys.items()} != reservation["trial_ids"]
        or keys["risk-82"][1]
    ):
        raise ValueError("fixed native23 reservations/692 bindings/5 results required")
    consumer = keys["risk-82"][0]
    lineage, sources = registry.fit_lineage(consumer), registry.feature_sources(consumer)
    if len(lineage["fits"]) != 2 or len(sources["providers"]) != 1:
        raise ValueError("frozen risk consumer lineage missing")
    return {
        "inventory_sha256": INVENTORY_SHA,
        "files": inventory["files"],
        "claim_sha256": inventory["claim_sha256"],
        "terminal_sha256": inventory["terminal_sha256"],
        "old_consumer": consumer,
        "fit_lineage": lineage,
        "feature_sources": sources,
        "native_count": len(rows),
        "fit_bindings": fits,
        "debt": PRIOR_DEBT,
    }


def prepare_diagnostic(worktree):
    paths = _paths(worktree)
    code = code_evidence(paths["worktree"])
    code["files"][DRIVER] = _bound(paths["worktree"], DRIVER)
    code["sha256"] = sha256_json(code["files"])
    old = old_auditor_bytes(paths["worktree"])
    verify_only_fill_condition_changed(old, (paths["worktree"] / REPLAY_FILE).read_bytes())
    # Execution, session conversion and account configuration stay byte-identical.
    previous = read(paths["old_operation"] / "LAUNCH.json")["plan"]["evidence"]["code"]["files"]
    for name in (
        "baseline/stateful.py",
        "discovery/flow_response_accounts.py",
        "discovery/flow_response_views.py",
    ):
        _bound(
            paths["worktree"], "src/stephen_quant/" + name, previous["src/stephen_quant/" + name]
        )
    parent = parent_evidence(paths["parent"])
    first_failure = failed_epoch_evidence(paths["failed_epoch"], paths["failed_claim"])
    failure = failed_account_evidence(paths)
    if first_failure["inherited_debt"] + failure["native_count"] != PRIOR_DEBT:
        raise ValueError("both failures must augment the verified parent debt")
    return {
        "version": VERSION,
        "claim_key": CLAIM_KEY,
        "paths": {k: str(v) for k, v in paths.items()},
        "code": code,
        "parent": parent,
        "failed002": first_failure,
        "failed003": failure,
        "old_auditor_commit": OLD_COMMIT,
        "old_auditor_sha256": OLD_REPLAY_SHA,
        "limits": asdict(LIMITS),
        "prior_debt": PRIOR_DEBT,
        "budget": BUDGET,
        "preregistration_issue": ISSUE_URL,
        "contract": {
            "key": "risk-82",
            "capital_cny": 3000000,
            "roundtrip_bps": 82,
            "mode": "target_changes",
            "execution_years": [2023, 2024],
            "history_years": [2022, 2023, 2024],
            "refits": 0,
            "retargeting": False,
            "inputs": ["history/history.json", "targets/risk.json"],
            "purpose": "reproduce first actual held-set failure and reconcile one frozen account",
            "read_other_account_metrics": False,
            "new_sources": False,
            "read_2025_2026": False,
            "usable_alpha": False,
        },
        "automatic_retry": False,
        "validated_alpha": False,
    }


def verify_diagnostic(plan, worktree):
    if sha256_json(plan) != sha256_json(prepare_diagnostic(worktree)):
        raise ValueError("diagnostic plan differs from fixed code/evidence/contract")
    return sha256_json(plan)


def _operation(plan, digest):
    return Path(plan["paths"]["worktree"]) / f"artifacts/flow-response/account-diagnostics/{digest}"


def reserve_diagnostic(output, plan):
    path = output / "registry.sqlite3"
    if path.exists():
        raise FileExistsError("diagnostic native database already exists")
    registry = ExperimentRegistry(path)
    snapshot = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {
                "inherited_inventory": plan["failed003"]["inventory_sha256"],
                "history": plan["failed003"]["files"]["history/history.json"]["sha256"],
                "targets": plan["failed003"]["files"]["targets/risk.json"]["sha256"],
                "native_parent": plan["failed003"]["files"]["registry.sqlite3"]["sha256"],
            }
        )
    )
    eid = registry.create_experiment_deterministic(
        ExperimentSpec(
            VERSION,
            "Frozen no-refit account failure diagnosis, not Alpha selection",
            snapshot,
            plan["code"]["sha256"],
            json.dumps(plan, sort_keys=True),
        ),
        sha256_json(plan),
    )
    tid, _ = registry.create_trial_deterministic(
        TrialSpec(
            eid,
            "risk-82-frozen-diagnostic",
            "inherited_native_frozen_target_replay",
            json.dumps(plan["contract"], sort_keys=True),
            184,
            "unused-no-refit",
            "unused-no-refit",
            "2023-01-01",
            "2024-12-31",
            "unused",
            "unused",
            fit_stages=(),
        ),
        sha256_json(plan["contract"]),
    )
    registry.declare_feature_sources(
        tid, ()
    )  # Inherited bytes are snapshot-bound, no new provider.
    return registry, tid


def launch_diagnostic(plan_path, *, comment_id, worktree):
    plan = read(plan_path)
    digest = verify_diagnostic(plan, worktree)
    comment = fetch_preregistration(comment_id, digest, worktree)
    memory = _resource_preflight()
    output, claim_path = _operation(plan, digest), Path(plan["paths"]["claim"])
    if output.exists():
        raise FileExistsError("diagnostic operation exists; no replay")
    write(
        claim_path,
        {
            "version": VERSION,
            "plan_sha256": digest,
            "operation": str(output),
            "preregistration_sha256": sha256_json(comment),
            "prior_debt": PRIOR_DEBT,
            "committed_attempt_budget": BUDGET,
            "claimed_at": now(),
            "prelaunch_memory": memory,
        },
    )
    outcome, error, native_count = "FAILED", None, 0
    try:
        output.mkdir(parents=True, exist_ok=False)
        write(output / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim_path)})
        write(output / "PREREGISTRATION.json", comment)
        registry, tid = reserve_diagnostic(output, plan)
        native_count = registry.global_trial_count()
        if native_count != 1:
            raise ValueError("exactly one native account attempt required")
        write(output / "RESERVATIONS.json", {"trial_id": tid, "reserved": 1, "debt": 3707})
        stage = supervise(
            [sys.executable, str(Path(worktree) / DRIVER), "child", "--operation", str(output)],
            cwd=worktree,
            output=output / "supervisor",
            limits=LIMITS,
            evidence_hashes={"plan": digest, "claim": file_sha(claim_path)},
        )
        if stage["outcome"] != "COMPLETED":
            raise RuntimeError("diagnostic child failed; retain attempt, no retry")
        result = read(output / "RESULT.json")
        if result["validated_alpha"] is not False:
            raise ValueError("account diagnosis cannot certify Alpha")
        verify_diagnostic(plan, worktree)
        outcome = "DIAGNOSED" if result["engineering_pass"] else "UNRESOLVED"
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        native_error = None
        if (output / "registry.sqlite3").exists():
            try:
                native_count = ReadOnlyRegistry(output / "registry.sqlite3").global_trial_count()
            except (OSError, ValueError, sqlite3.Error) as exc:
                native_count, native_error = None, type(exc).__name__
        write(
            claim_path.with_name(claim_path.stem + ".terminal.json"),
            {
                "outcome": outcome,
                "exception_type": error,
                "finished_at": now(),
                "plan_sha256": digest,
                "native_reserved": native_count,
                "native_count_error": native_error,
                "committed_attempt_budget": BUDGET,
                "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
                "automatic_retry": False,
                "validated_alpha": False,
            },
        )
    return {"outcome": outcome, "debt": 3707, "validated_alpha": False}


def _first_divergence(exc, function):
    tb = exc.__traceback__
    while tb and tb.tb_frame.f_code is not function.__code__:
        tb = tb.tb_next
    if tb is None or str(exc) != "held-name set differs from fill reconstruction":
        return {"explained": False, "error": str(exc), "exception_type": type(exc).__name__}
    values = tb.tb_frame.f_locals
    day, shares, marks, bars = (values[k] for k in ("day", "shares", "marks", "by_name"))
    missing = {n for n, q in shares.items() if q > 1e-12} ^ set(marks)
    rows = []
    for name in sorted(missing):
        small = [
            o for o in day.orders if o.instrument == name and 0 < abs(o.executed_notional) <= 1e-12
        ]
        corrected = shares.get(name, 0.0)
        for order in small:
            corrected += order.executed_notional / bars[name].open_price
        marked = marks[name].shares if name in marks else 0.0
        explained = (
            bool(small)
            and ((corrected > 1e-12) == (name in marks))
            and (name not in marks or math.isclose(corrected, marked, rel_tol=0, abs_tol=1e-12))
        )
        rows.append(
            {
                "instrument": name,
                "old_shares": shares.get(name, 0.0),
                "marked_shares": marked,
                "after_tiny_fills": corrected,
                "open_price": bars[name].open_price if name in bars else None,
                "tiny_notionals": [o.executed_notional for o in small],
                "explained": explained,
            }
        )
    return {
        "date": day.trade_date,
        "error": str(exc),
        "names": rows,
        "explained": bool(rows) and all(r["explained"] for r in rows),
    }


def compare_auditors(report, sessions, targets, old_source):
    module = ModuleType("stephen_quant.discovery._frozen_diagnostic_auditor")
    module.__package__ = "stephen_quant.discovery"
    # Production passes only hash-pinned bytes from our fixed original Git commit.
    exec(compile(old_source, "<frozen-original-auditor>", "exec"), module.__dict__)  # noqa: S102
    old = {"reproduced": False, "first_divergence": None}
    try:
        module.audit_response_account(report, sessions, targets, roundtrip_bps=82)
    except ValueError as exc:
        first = _first_divergence(exc, module.audit_response_account)
        old = {
            "reproduced": first.get("error") == "held-name set differs from fill reconstruction",
            "first_divergence": first,
        }
    try:
        corrected = flow_response_replay.audit_response_account(
            report, sessions, targets, roundtrip_bps=82
        )
    except ValueError as exc:
        corrected = {"pass": False, "error": str(exc), "exception_type": type(exc).__name__}
    tiny = [
        {"date": d.trade_date, "instrument": o.instrument, "notional": o.executed_notional}
        for d in report.periods
        for o in d.orders
        if 0 < abs(o.executed_notional) <= 1e-12
    ]
    passed = old["reproduced"] and old["first_divergence"]["explained"] and corrected["pass"]
    return {
        "engineering_pass": bool(passed),
        "original_audit": old,
        "corrected_audit": corrected,
        "tiny_fills": tiny,
        "validated_alpha": False,
        "scope": "first old stopping point explained; corrected full account reconciled; no source/model/target selection or Alpha Court certification",
    }


def run_diagnostic_child(operation, worktree):
    output = Path(operation).resolve(strict=True)
    launch = read(output / "LAUNCH.json")
    plan = launch["plan"]
    digest = verify_diagnostic(plan, worktree)
    claim_path = Path(plan["paths"]["claim"])
    claim, comment = read(claim_path), read(output / "PREREGISTRATION.json")
    if (
        output != _operation(plan, digest).resolve()
        or file_sha(claim_path) != launch["claim_sha256"]
        or claim["plan_sha256"] != digest
        or claim["operation"] != str(output)
        or claim["preregistration_sha256"] != sha256_json(comment)
        or claim["prior_debt"] != PRIOR_DEBT
        or claim["committed_attempt_budget"] != 1
        or claim_path.with_name(claim_path.stem + ".terminal.json").exists()
    ):
        raise ValueError("active bound diagnostic claim required")
    reservation = read(output / "RESERVATIONS.json")
    if not (output / "registry.sqlite3").is_file() or reservation != {
        "trial_id": reservation.get("trial_id"),
        "reserved": 1,
        "debt": 3707,
    }:
        raise ValueError("existing complete diagnostic reservation receipt required")
    registry = ExperimentRegistry(output / "registry.sqlite3")
    tid = reservation["trial_id"]
    with registry.connect() as db:
        rows = db.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,e.search_space FROM trials t JOIN experiments e USING(experiment_id)"
        ).fetchall()
    if (
        len(rows) != 1
        or rows[0][0] != tid
        or rows[0][2] is not None
        or json.loads(rows[0][1]) != plan["contract"]
        or json.loads(rows[0][3]) != plan
        or registry.fit_lineage(tid)["stages"]
        or registry.feature_sources(tid)["providers"]
    ):
        raise ValueError("one uncompleted native no-fit diagnostic reservation required")
    write(output / "CHILD.json", {"started_at": now(), "plan_sha256": digest, "trial_id": tid})
    # All claims/native contracts precede numeric decode. No source refit occurs.
    old_root = Path(plan["paths"]["old_operation"])
    history, proof = read_verified_history(
        ReadOnlyRegistry(old_root / "registry.sqlite3"),
        plan["failed003"]["old_consumer"],
        old_root / "history/history.json",
        immutable=True,
    )
    days = [d for d in history["calendar"] if "2023-01-01" <= d <= "2024-12-31"]
    raw = read(old_root / "targets/risk.json")
    targets = frozen_targets(raw, sha256_json(raw), days)  # Exact raw hash already plan-bound.
    sessions = HistoricalSessions(history["bars"], days)
    print("frozen history and targets verified; beginning one account", flush=True)
    report = execute_response_account(sessions, targets, roundtrip_bps=82)
    write(output / "UNVERIFIED_ACCOUNT.json", asdict(report))
    result = compare_auditors(report, sessions, targets, old_auditor_bytes(worktree))
    result.update(
        {
            "version": VERSION,
            "trial_id": tid,
            "plan_sha256": digest,
            "history_proof": proof,
            "account_sha256": file_sha(output / "UNVERIFIED_ACCOUNT.json"),
            "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
            "new_fits": 0,
        }
    )
    verify_diagnostic(plan, worktree)
    registry.record_trial_result(tid, json.dumps(result, sort_keys=True, allow_nan=False))
    write(output / "RESULT.json", result)
    print(
        json.dumps({"engineering_pass": result["engineering_pass"], "validated_alpha": False}),
        flush=True,
    )
