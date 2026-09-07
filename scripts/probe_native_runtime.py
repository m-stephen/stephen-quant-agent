"""One fixed synthetic diagnostic, not a retry-until-green stress test."""

import argparse
import faulthandler
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

SECONDS = 5
PROCESS_TIMEOUT = 15
PLAN = tuple(
    {"workload": workload, "timer": timer, "replicate": replicate}
    for workload in ("frames", "variance")
    for timer in (0, 0.05)
    for replicate in (1, 2, 3)
)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def file_identity(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def metadata():
    library = Path(sysconfig.get_config_var("LIBDIR") or ".") / (
        sysconfig.get_config_var("LDLIBRARY") or "not-present"
    )
    return {
        "executable": file_identity(sys.executable),
        "libpython": file_identity(library) if library.is_file() else None,
        "version": sys.version,
        "python_vv": subprocess.check_output([sys.executable, "-VV"], text=True).strip(),
        "build": platform.python_build(),
        "platform": platform.platform(),
        "config_args": sysconfig.get_config_var("CONFIG_ARGS"),
        "dependencies": {
            package: importlib.metadata.version(package)
            for package in ("numpy", "duckdb", "pytest", "ruff", "pytz")
        },
        "source_build_verified": False,
    }


def frame_work(value):
    def inner(number):
        return sum(i * number for i in range(32))

    return inner(value % 17)


def child(workload, timer):
    # Imports precede the five-second workload/timer interval in both arms.
    if workload == "variance":
        import numpy as np

        values = np.arange(65536, dtype=float)
        work = lambda value: float(np.var(values))
    else:
        work = frame_work
    faulthandler.enable()
    if timer:
        faulthandler.dump_traceback_later(timer, repeat=True)
    start = time.monotonic()
    iterations = 0
    value = 0
    try:
        while time.monotonic() - start < SECONDS:
            value = work(value)
            iterations += 1
    finally:
        if timer:
            faulthandler.cancel_dump_traceback_later()
    print(json.dumps({"completed": True, "iterations": iterations,
                      "elapsed_seconds": time.monotonic() - start}), flush=True)


def run_probe(output, index, arm):
    stdout = output / f"probe-{index:02d}.stdout.log"
    stderr = output / f"probe-{index:02d}.stderr.log"
    started = time.monotonic()
    timed_out = False
    error = None
    returncode = None
    with stdout.open("x", encoding="utf-8") as out, stderr.open("x", encoding="utf-8") as err:
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child",
                 "--workload", arm["workload"], "--timer", str(arm["timer"])],
                stdout=out, stderr=err, timeout=PROCESS_TIMEOUT, check=False,
            )
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            # subprocess.run kills/waits only for its own direct child.
            timed_out = True
        except OSError as exc:
            error = type(exc).__name__ + ": " + str(exc)
    completed = False
    try:
        completion = json.loads(stdout.read_text(encoding="utf-8"))
        completed = (completion.get("completed") is True
                     and completion.get("elapsed_seconds", 0) >= SECONDS
                     and completion.get("iterations", 0) > 0)
    except (ValueError, AttributeError, TypeError):
        pass
    trace = stderr.read_text(encoding="utf-8", errors="replace")
    observed = trace.count("Timeout (")
    result = {
        **arm, "returncode": returncode, "timed_out": timed_out, "error": error,
        "completed": completed, "elapsed_seconds": time.monotonic() - started,
        "dump_count": observed, "stdout": file_identity(stdout), "stderr": file_identity(stderr),
        "execution_ok": (returncode == 0 and completed and not timed_out and error is None
                         and (observed > 0 if arm["timer"] else observed == 0)),
    }
    write_json(output / f"probe-{index:02d}.json", result)
    return result


def run(output):
    # Exclusive directory is the local once-only claim. Never overwrite failed evidence.
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", {
        "arms": PLAN, "workload_seconds": SECONDS, "owned_process_timeout": PROCESS_TIMEOUT,
        "process_budget": 12, "adaptive_retries": 0, "market_trials": 0,
    })
    write_json(output / "runtime.json", metadata())
    results = [run_probe(output, index, arm) for index, arm in enumerate(PLAN, 1)]
    all_ok = all(item["execution_ok"] for item in results)
    write_json(output / "result.json", {
        "results": results, "executed": len(results), "all_execution_ok": all_ok,
        "root_cause_proven": False, "market_alpha": False,
    })
    return 0 if all_ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--workload", choices=("frames", "variance"))
    parser.add_argument("--timer", type=float, choices=(0, 0.05))
    args = parser.parse_args()
    if args.child:
        if args.workload is None or args.timer is None or args.output is not None:
            parser.error("child requires workload/timer, no output")
        child(args.workload, args.timer)
    else:
        if args.output is None or args.workload is not None or args.timer is not None:
            parser.error("parent requires output only")
        raise SystemExit(run(args.output))
