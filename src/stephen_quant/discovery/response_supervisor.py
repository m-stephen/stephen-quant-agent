"""Owned-child resource supervision with terminal failure evidence.

This is not an empirical launch authorization. The production launcher must bind
and verify its fixed command, parent/source/code evidence and full Trial budget
before calling it. It never retries a child or changes a completed operation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .response_resources import child_process_memory, process_memory

_WINDOWS = os.name == "nt"
_SECRET_ENV = {"ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL"}


@dataclass(frozen=True)
class ResourceLimits:
    private_commit_bytes: int
    minimum_free_physical_bytes: int
    wall_seconds: float
    poll_seconds: float = 0.2

    def validate(self):
        if any(
            type(v) is not int or v <= 0
            for v in (self.private_commit_bytes, self.minimum_free_physical_bytes)
        ):
            raise ValueError("positive integer memory limits required")
        if (
            any(
                type(v) not in (int, float) or not math.isfinite(v) or v <= 0
                for v in (self.wall_seconds, self.poll_seconds)
            )
            or not 0.05 <= self.poll_seconds <= 1.0
        ):
            raise ValueError("finite positive runtime and0.05–1second polling required")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _free_reason(memory, floor):
    free = memory.get("physical_available_bytes")
    if type(free) is not int or free < 0:
        return "free_memory_measurement_unavailable"
    return "free_physical_floor" if free < floor else None


def supervise(command, *, cwd, output, limits, evidence_hashes):
    """Run one owned Windows child; return success, refusal, stop or failure.

    Measurement errors, nonzero exits and cleanup failures retain a terminal
    receipt. KeyboardInterrupt/SystemExit are recorded, then propagated. A
    machine power loss can still leave only START/log/samples. Polling is not an
    OS-enforced memory limit; this function is not a multi-user permission layer.
    """
    if type(limits) is not ResourceLimits:
        raise ValueError("explicit frozen resource limits required")
    limits.validate()
    if (
        not isinstance(command, (tuple, list))
        or not command
        or any(not isinstance(v, str) or not v or "\0" in v for v in command)
    ):
        raise ValueError("explicit argument vector required; no shell command")
    if (
        not evidence_hashes
        or not isinstance(evidence_hashes, dict)
        or any(
            not isinstance(k, str)
            or not k
            or not isinstance(v, str)
            or re.fullmatch("[a-f0-9]{64}", v) is None
            for k, v in evidence_hashes.items()
        )
    ):
        raise ValueError("explicit named SHA256 evidence bindings required")
    working, root = Path(cwd).resolve(strict=True), Path(output).resolve()
    if not working.is_dir():
        raise ValueError("existing child working directory required")
    root.mkdir(parents=True, exist_ok=False)
    started, clock = _now(), time.perf_counter()
    plan = {
        "command_sha256": _sha(list(command)),
        "limits": asdict(limits),
        "evidence_hashes": dict(sorted(evidence_hashes.items())),
        "started_at": started,
        "permission": "supervision only; not empirical authorization",
        "automatic_retry": False,
    }
    _write(root / "START.json", plan)
    process, code, error, reason, outcome = None, None, None, None, "FAILED"
    samples, peaks, minimum_free = 0, {}, None
    raised, stage, error_stage = None, "capability", None
    try:
        if not _WINDOWS:
            reason, outcome = "owned_measurement_requires_windows", "PRELAUNCH_REFUSED"
        else:
            stage = "prelaunch_resources"
            reason = _free_reason(process_memory(), limits.minimum_free_physical_bytes)
            if reason:
                outcome = "PRELAUNCH_REFUSED"
            else:
                env = {k: v for k, v in os.environ.items() if k.upper() not in _SECRET_ENV}
                with (
                    (root / "process.log").open("x", encoding="utf-8") as log,
                    (root / "samples.jsonl").open(
                        "x", encoding="utf-8", newline="\n"
                    ) as sample_log,
                ):
                    stage = "spawn"
                    process = subprocess.Popen(
                        list(command),
                        cwd=working,
                        env=env,
                        shell=False,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    while process.poll() is None:
                        stage = "owned_measurement"
                        memory = child_process_memory(process)
                        elapsed = time.perf_counter() - clock
                        for key in ("peak_private_commit_bytes", "peak_rss_bytes"):
                            value = memory.get(key)
                            if type(value) is not int or value < 0:
                                raise OSError("owned peak measurement unavailable")
                            peaks[key] = max(peaks.get(key, 0), value)
                        free = memory.get("physical_available_bytes")
                        if type(free) is int and free >= 0:
                            minimum_free = free if minimum_free is None else min(minimum_free, free)
                        samples += 1
                        sample_log.write(json.dumps({"elapsed_seconds": elapsed, **memory}) + "\n")
                        sample_log.flush()
                        reason = _free_reason(memory, limits.minimum_free_physical_bytes)
                        if memory["peak_private_commit_bytes"] >= limits.private_commit_bytes:
                            reason = "private_commit_limit"
                        elif elapsed >= limits.wall_seconds:
                            reason = "time_limit"
                        if reason:
                            outcome = "GUARD_STOPPED"
                            break
                        stage = "poll_wait"
                        time.sleep(limits.poll_seconds)
                    code = process.poll()
                    if reason is None:
                        if code != 0:
                            reason = "child_exit_nonzero"
                        elif samples == 0:
                            reason = "no_owned_memory_sample"
                        else:
                            outcome = "COMPLETED"
    except BaseException as exc:  # noqa: BLE001 -- Own the child and retain a terminal receipt.
        raised, error = exc, type(exc).__name__
        error_stage = stage
        reason = "supervisor_exception"
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()  # Never opens or terminates an unrelated PID.
                code = process.wait(timeout=10)
            except BaseException as exc:  # noqa: BLE001 -- Cleanup errors must not lose evidence.
                outcome, reason, error = "TERMINATION_FAILED", "cleanup_failed", type(exc).__name__
                error_stage = "cleanup"
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raised = exc
        receipt = {
            "outcome": outcome,
            "reason": reason,
            "exception_type": error,
            "exception_stage": error_stage,
            "started_at": started,
            "finished_at": _now(),
            "seconds": time.perf_counter() - clock,
            "plan_sha256": _sha(plan),
            "evidence_hashes": plan["evidence_hashes"],
            "pid": process.pid if process is not None else None,
            "exit_code": code,
            "samples": samples,
            "observed_peaks": peaks,
            "minimum_free_physical_bytes": minimum_free,
            "automatic_retry": False,
            "validated_alpha": False,
        }
        _write(root / "SUPERVISOR.json", receipt)
    if isinstance(raised, (KeyboardInterrupt, SystemExit)):
        raise raised
    return receipt
