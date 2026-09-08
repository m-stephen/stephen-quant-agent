"""One owned forensic child, one shared deadline, one irreversible local claim.

No model fitting, predictions, native account reservations or source repairs.
The parent alone writes the final terminal after post-exit artifact verification.
"""

import faulthandler
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_acceptance import accept_saved_artifacts, check_fields, exact, read
from .account_forensics_evidence import bind_files, verify_unchanged
from .account_forensics_plan import (
    CLAIM_KEY,
    DRIVER,
    code_snapshot,
    fetch_preregistration,
    operation_path,
    paths,
    runtime_evidence,
    scope,
    validate_preregistration,
    verify_plan,
)
from .account_forensics_report import verify_reports, write_reports
from .account_forensics_runtime import build_saved_report
from .flow_response_launch import LIMITS, now, write
from .response_resources import process_memory
from .response_supervisor import ResourceLimits, _sha, supervise
from .search_power_dsl import sha256_json

SUCCESS = "COMPLETED_READONLY_FORENSICS"
CHILD_SUCCESS = "CHILD_FORENSICS_COMPLETE_PENDING_PARENT"


def require_host():
    if sys.platform != "win32" or sys.version_info[:3] != (3, 10, 9):
        raise ValueError("reviewed production host is Windows CPython3.10.9 only")


def resource_guard(started):
    """Parent checkpoints; the owned numerical child is continuously polled.

    This is not an OS-hard deadline or a cap on aggregate machine memory. A
    blocking final read may overrun, but it must never be accepted after expiry.
    """
    elapsed = monotonic() - started
    if elapsed >= LIMITS.wall_seconds:
        raise ValueError("shared forensic deadline exhausted")
    measured = process_memory()
    peak, free = measured.get("peak_private_commit_bytes"), measured.get("physical_available_bytes")
    if (type(peak) is not int or peak < 0 or peak >= LIMITS.private_commit_bytes
            or type(free) is not int or free < LIMITS.minimum_free_physical_bytes):
        raise ValueError("forensic memory guard refused")
    return measured


def _operation(operation, worktree):
    base = paths(worktree)["operations"].resolve()
    root = Path(operation).resolve()
    if root.parent != base or len(root.name) != 64 or any(c not in "0123456789abcdef" for c in root.name):
        raise ValueError("exact persistent forensic operation path required")
    return root


def _bindings(plan, claim_sha):
    return {"plan": sha256_json(plan), "claim": claim_sha,
            "code": sha256_json(plan["code"]), "runtime": sha256_json(plan["runtime"]),
            "inputs": sha256_json(plan["input_evidence"])}


def _check_envelope(root, worktree):
    launch = read(root / "LAUNCH.json")
    plan = launch["plan"]
    digest = sha256_json(plan)
    exact(operation_path(plan).resolve(), root)
    exact(root.name, digest)
    exact(plan["paths"], {k: str(v) for k, v in paths(worktree).items()})
    exact(plan["scope"], scope())
    exact(plan["claim_key"], CLAIM_KEY)
    exact(plan["limits"], asdict(LIMITS))
    claim_path = Path(plan["paths"]["claim"])
    claim = read(claim_path)
    prereg = read(root / "PREREGISTRATION.json")
    validate_preregistration(prereg["comment"], prereg["comment"]["id"], digest)
    exact(prereg["plan_sha256"], digest)
    check_fields(claim, {"version": "V12.3", "claim_key": CLAIM_KEY, "plan_sha256": digest,
        "operation": str(root), "preregistration_sha256": sha256_json(prereg),
        "scope": scope(), "automatic_retry": False})
    exact(launch["claim_sha256"], file_sha(claim_path))
    exact(launch["started_at"], claim["started_at"])
    started = datetime.fromisoformat(claim["started_at"])
    deadline = datetime.fromisoformat(launch["deadline_at"])
    if (started.utcoffset() is None or deadline.utcoffset() is None
            or deadline - started != timedelta(seconds=LIMITS.wall_seconds)):
        raise ValueError("one fixed aware total operation deadline required")
    limits = launch["child_limits"]
    exact({k: v for k, v in limits.items() if k != "wall_seconds"},
          {k: v for k, v in asdict(LIMITS).items() if k != "wall_seconds"})
    if type(limits["wall_seconds"]) not in (int, float) or not 0 < limits["wall_seconds"] <= LIMITS.wall_seconds:
        raise ValueError("child cannot obtain another full-stage budget")
    return launch, plan


def _artifact_acceptance(root, plan, worktree):
    return accept_saved_artifacts(root / "saved-report", evidence=plan["input_evidence"],
        source_calendar=plan["source_calendar"], calendar_binding=plan["calendar_binding"],
        producer_code=plan["package_code"], code_root=Path(worktree) / "src/stephen_quant")


def run_worker(operation, worktree):
    require_host()
    root = _operation(operation, worktree)
    launch, plan = _check_envelope(root, worktree)
    exact(os.getppid(), launch["launcher_pid"])
    command = [sys.executable, str(Path(worktree) / DRIVER), "worker", "--operation", str(root)]
    supervised = read(root / "supervisor/START.json")
    check_fields(supervised, {"command_sha256": _sha(command), "limits": launch["child_limits"],
        "evidence_hashes": _bindings(plan, launch["claim_sha256"]), "automatic_retry": False})
    if datetime.now(timezone.utc) >= datetime.fromisoformat(launch["deadline_at"]):
        raise ValueError("expired forensic child")
    if (root / "WORKER_TERMINAL.json").exists():
        raise FileExistsError("worker terminal already exists; no replay")
    # Consumed before history/account numerical decoding. An interrupted child
    # cannot be started again with the same operation, even without a terminal.
    write(root / "WORKER_STARTED.json", {"started_at": now(), "plan_sha256": sha256_json(plan),
                                         "pid": os.getpid(), "automatic_retry": False})
    stage = "verify_frozen_plan"
    try:
        faulthandler.cancel_dump_traceback_later()  # owned child only; no scheduled diagnostic timer.
        verify_plan(plan, worktree)
        stage = "saved_report"
        build_saved_report(plan["input_evidence"], calendar_binding=plan["calendar_binding"], output=root / "saved-report")
        stage = "external_artifact_acceptance"
        acceptance = _artifact_acceptance(root, plan, worktree)
        write(root / "ACCEPTANCE.json", acceptance)
        stage = "bilingual_report"
        write_reports(root / "saved-report", acceptance)
        stage = "report_readback"
        report = verify_reports(root / "saved-report", acceptance)
        write(root / "WORKER_TERMINAL.json", {"outcome": CHILD_SUCCESS, "finished_at": now(),
            "plan_sha256": sha256_json(plan), "acceptance_sha256": file_sha(root / "ACCEPTANCE.json"),
            "rendered_sha256": file_sha(root / "saved-report/reader-report/RENDERED.json"),
            "report": report, "automatic_retry": False, "validated_alpha": False})
    except BaseException as exc:
        write(root / "WORKER_TERMINAL.json", {"outcome": "FAILED", "stage": stage,
            "finished_at": now(), "error_type": type(exc).__name__, "automatic_retry": False,
            "validated_alpha": False})
        raise


def final_check(root, plan, worktree, supervisor, started):
    """Still-running parent checks the exited child's actual files, not flags alone."""
    resource_guard(started)
    launch, bound_plan = _check_envelope(root, worktree)
    exact(bound_plan, plan)
    exact(code_snapshot(worktree), plan["code"])
    exact(runtime_evidence(), plan["runtime"])
    verify_unchanged(plan["input_evidence"])
    stored = read(root / "supervisor/SUPERVISOR.json")
    exact(stored, supervisor)
    check_fields(stored, {"outcome": "COMPLETED", "exit_code": 0,
        "evidence_hashes": _bindings(plan, launch["claim_sha256"]),
        "automatic_retry": False, "validated_alpha": False})
    start = read(root / "supervisor/START.json")
    command = [sys.executable, str(Path(worktree) / DRIVER), "worker", "--operation", str(root)]
    check_fields(start, {"command_sha256": _sha(command), "limits": launch["child_limits"],
        "evidence_hashes": _bindings(plan, launch["claim_sha256"]), "automatic_retry": False})
    exact(stored["plan_sha256"], _sha(start))
    if (type(stored["samples"]) is not int or stored["samples"] < 1
            or stored["observed_peaks"]["peak_private_commit_bytes"] >= LIMITS.private_commit_bytes
            or stored["minimum_free_physical_bytes"] < LIMITS.minimum_free_physical_bytes):
        raise ValueError("complete bounded supervision measurements required")
    worker_start = read(root / "WORKER_STARTED.json")
    check_fields(worker_start, {"plan_sha256": sha256_json(plan), "pid": stored["pid"], "automatic_retry": False})
    if type(stored["pid"]) is not int or stored["pid"] <= 0:
        raise ValueError("actual owned child PID required")
    terminal = read(root / "WORKER_TERMINAL.json")
    check_fields(terminal, {"outcome": CHILD_SUCCESS, "plan_sha256": sha256_json(plan),
        "acceptance_sha256": file_sha(root / "ACCEPTANCE.json"),
        "rendered_sha256": file_sha(root / "saved-report/reader-report/RENDERED.json"),
        "automatic_retry": False, "validated_alpha": False})
    resource_guard(started)
    acceptance = _artifact_acceptance(root, plan, worktree)
    exact(read(root / "ACCEPTANCE.json"), acceptance)
    report = verify_reports(root / "saved-report", acceptance)
    exact(terminal["report"], report)
    bind_files(worktree, plan["code"]["files"])
    verify_unchanged(plan["input_evidence"])
    resource_guard(started)
    return {"acceptance_sha256": file_sha(root / "ACCEPTANCE.json"),
            "supervisor_sha256": file_sha(root / "supervisor/SUPERVISOR.json"), "report": report}


def launch(plan_path, *, comment_id, worktree):
    require_host()
    worktree = Path(worktree).resolve()
    plan = read(plan_path)
    digest = verify_plan(plan, worktree)
    prereg = fetch_preregistration(comment_id, digest, worktree)
    started = monotonic()
    resource_guard(started)
    root, claim_path = operation_path(plan), Path(plan["paths"]["claim"])
    if root.exists() or claim_path.exists() or claim_path.with_suffix(".terminal.json").exists():
        raise FileExistsError("operation or shared claim/terminal already exists; no replay")
    stamp = now()
    claim = {"version": "V12.3", "claim_key": CLAIM_KEY, "plan_sha256": digest,
        "operation": str(root), "preregistration_sha256": sha256_json(prereg), "scope": scope(),
        "started_at": stamp, "automatic_retry": False}
    write(claim_path, claim)  # atomic exclusive creation; any partial claim remains consumed.
    stage, outcome, checked, error, created = "operation_creation", "FAILED", None, None, False
    try:
        root.mkdir(parents=True, exist_ok=False)
        created = True
        remaining = LIMITS.wall_seconds - (monotonic() - started)
        child_limits = ResourceLimits(LIMITS.private_commit_bytes, LIMITS.minimum_free_physical_bytes,
                                      remaining, LIMITS.poll_seconds)
        child_limits.validate()
        write(root / "PREREGISTRATION.json", prereg)
        write(root / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim_path),
            "started_at": stamp, "deadline_at": (datetime.fromisoformat(stamp) + timedelta(seconds=LIMITS.wall_seconds)).isoformat(),
            "launcher_pid": os.getpid(), "child_limits": asdict(child_limits)})
        resource_guard(started)
        stage = "owned_forensic_child"
        supervisor = supervise([sys.executable, str(worktree / DRIVER), "worker", "--operation", str(root)],
            cwd=worktree, output=root / "supervisor", limits=child_limits,
            evidence_hashes=_bindings(plan, file_sha(claim_path)))
        stage = "parent_final_acceptance"
        checked = final_check(root, plan, worktree, supervisor, started)
        outcome = SUCCESS
    except BaseException as exc:  # noqa: BLE001 -- preserve canonical failure evidence, then re-raise.
        error = exc
    terminal = {"outcome": outcome, "stage": stage, "finished_at": now(),
        "plan_sha256": digest, "scope": scope(), "elapsed_seconds": monotonic() - started,
        "error_type": type(error).__name__ if error else None, "checks": checked,
        "automatic_retry": False, "validated_alpha": False}
    # The shared terminal is canonical even when operation directory creation failed.
    write(claim_path.with_suffix(".terminal.json"), terminal)
    if created:
        write(root / "FINAL.json", terminal)
    if error is not None:
        raise error
    return terminal
