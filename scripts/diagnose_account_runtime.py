"""One Linux synthetic account fixture per fixed V12.3 diagnostic cell, no retries."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import sys
import sysconfig
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SLOT = "v123-native-runtime-001"
NODE = ("tests/test_flow_response_epoch.py::"
        "test_construction_complete_four_accounts_source_target_account_audit")
SECONDS = 900
PACKAGES = {
    "duckdb": "1.5.5", "pytest": "9.1.1", "ruff": "0.16.6",
    "pytz": "2026.3.post1", "iniconfig": "2.3.0", "packaging": "26.3",
    "pluggy": "1.6.0", "pygments": "2.21.0",
}


def write(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write("\n")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expected_packages(version):
    if version not in ("3.10.21", "3.12.14"):
        raise ValueError("unapproved interpreter")
    result = dict(PACKAGES, numpy="2.2.6" if version == "3.10.21" else "2.5.3")
    if version == "3.10.21":
        result.update(exceptiongroup="1.3.1", tomli="2.4.1", **{"typing-extensions": "4.16.0"})
    return result


def snapshot(root, version):
    if platform.python_version() != version:
        raise ValueError("actual interpreter mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root).strip():
        raise ValueError("clean diagnostic commit required")
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "src", "tests", "scripts", "pyproject.toml",
         ".github/workflows/ci.yml"], cwd=root,
    ).decode().split("\0")
    sources = {name: sha(root / name) for name in names if name}
    dependencies = {}
    for name, expected in expected_packages(version).items():
        dist = importlib.metadata.distribution(name)
        if dist.version != expected:
            raise ValueError(f"dependency version mismatch: {name}")
        files = {}
        for item in dist.files or ():
            if str(item).endswith(".pyc"):
                continue
            path = Path(dist.locate_file(item))
            if path.is_file():
                files[str(item)] = sha(path)
        if not files:
            raise ValueError(f"missing installed dependency bytes: {name}")
        dependencies[name] = {"version": dist.version, "files": files,
                              "files_sha256": canonical(files)}
    library = Path(sysconfig.get_config_var("LIBDIR")) / sysconfig.get_config_var("LDLIBRARY")
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "sources": sources, "sources_sha256": canonical(sources),
        "dependencies": dependencies, "version": sys.version,
        "executable_sha256": sha(sys.executable), "libpython_sha256": sha(library),
        "platform": platform.platform(), "build": platform.python_build(),
        "config_args": sysconfig.get_config_var("CONFIG_ARGS"),
        "source_build_verified": False,
    }


def junit_one(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if len(suites) != 1:
        raise ValueError("exactly one completed suite required")
    suite = suites[0]
    cases = suite.findall("testcase")
    if (int(suite.attrib["tests"]) != 1 or len(cases) != 1
            or any(int(suite.attrib[key]) for key in ("failures", "errors", "skipped"))):
        raise ValueError("exactly one successful non-skipped test required")
    case = cases[0]
    if (case.attrib.get("classname") != "tests.test_flow_response_epoch"
            or case.attrib.get("name") != NODE.split("::")[1]
            or any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))):
        raise ValueError("exact successful original node required")
    return True


def session_members(session_id):
    """Linux /proc stat identities; debugger inferiors may have another PGID."""
    members = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[3]) == session_id and fields[0] != "Z":
                members[int(path.name)] = int(fields[19])  # starttime, not mutable command text
        except (OSError, ValueError, IndexError):
            continue
    return members


def signal_member(pid, starttime, session_id, sig):
    """Pin PID with pidfd; recheck session/starttime before signalling."""
    try:
        fd = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        if session_members(session_id).get(pid) == starttime:
            signal.pidfd_send_signal(fd, sig)
    except ProcessLookupError:
        pass
    finally:
        os.close(fd)


def terminate_session(child):
    """Own session includes time, GDB and separately grouped inferior processes."""
    identities = session_members(child.pid)
    for pid, started in identities.items():
        signal_member(pid, started, child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    deadline = time.monotonic() + 5
    remaining = session_members(child.pid)
    while remaining and time.monotonic() < deadline:
        identities.update(remaining)
        for pid, started in remaining.items():
            signal_member(pid, started, child.pid, signal.SIGKILL)
        time.sleep(0.05)
        remaining = session_members(child.pid)
    code = child.wait(timeout=5)
    return code, {"seen_pid_starttimes": identities, "remaining": remaining,
                  "session_cleanup_complete": not remaining}


def supervise(command, root, output, env):
    """Linux owned session: bound debugger and descendants, not only its parent."""
    started = time.monotonic()
    timed_out = False
    cleanup = None
    with (output / "pytest.log").open("x", encoding="utf-8") as log:
        child = subprocess.Popen(command, cwd=root, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            code, cleanup = terminate_session(child)
        if cleanup is None and session_members(child.pid):
            code, cleanup = terminate_session(child)
    import resource
    return {"returncode": code, "timed_out": timed_out,
            "elapsed_seconds": time.monotonic() - started,
            "cleanup": cleanup,
            "children_maxrss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}


def verdict(output, receipt, trace):
    log = (output / "pytest.log").read_text(encoding="utf-8", errors="replace")
    dumps = log.count("Timeout (")
    error = None
    try:
        junit_one(output / "pytest.xml")
    except (OSError, ValueError, KeyError, ET.ParseError) as exc:
        error = type(exc).__name__ + ": " + str(exc)
    native = any(token in log for token in ("SIGSEGV", "SIGABRT", "SIGBUS"))
    killed = "SIGKILL" in log or receipt["returncode"] in (-9, 137)
    if receipt.get("cleanup") and not receipt["cleanup"]["session_cleanup_complete"]:
        outcome = "OWNED_PROCESS_REMAINS"
    elif receipt["timed_out"]:
        outcome = "TIMEOUT"
    elif native:
        outcome = "NATIVE_FAILURE"
    elif killed:
        outcome = "KILLED_OOM_UNPROVEN"
    elif receipt["returncode"] != 0:
        outcome = "PROCESS_FAILURE"
    elif error is not None:
        outcome = "INCOMPLETE_OR_FAILED_JUNIT"
    elif trace == 120 and dumps == 0:
        outcome = "NO_TIMER_EXPOSURE"
    elif trace == 0 and dumps:
        outcome = "UNEXPECTED_TIMER_EXPOSURE"
    else:
        outcome = "NOT_REPRODUCED" if trace else "CONTROL_COMPLETED"
    return {**receipt, "outcome": outcome, "dump_count": dumps, "junit_error": error,
            "native_signal_observed": native, "oom_proven": False,
            "root_cause_proven": False, "market_trials": 0, "validated_alpha": False}


def run(output, version, trace):
    if sys.platform != "linux" or trace not in (0, 120):
        raise ValueError("fixed Linux diagnostic cells only")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("fresh reviewed dispatch only; automatic reruns refused")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    write(output / "START.json", {"slot": SLOT, "python": version, "trace": trace,
          "node": NODE, "process_budget": 1, "timeout_seconds": SECONDS,
          "allocator": "debug", "run_id": os.environ.get("GITHUB_RUN_ID"),
          "started_at": datetime.now(timezone.utc).isoformat()})
    try:
        before = snapshot(root, version)
        write(output / "BINDINGS.json", before)
        env = dict(os.environ, PYTHONMALLOC="debug")
        for name in ("ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL", "PYTEST_ADDOPTS"):
            env.pop(name, None)
        command = ["/usr/bin/time", "-v", "-o", str(output / "resources.log"),
                   "gdb", "--batch", "--nx", "--return-child-result",
                   "-ex", "set debuginfod enabled off", "-ex", "set print thread-events off",
                   "-ex", "set print frame-arguments none", "-ex", "run",
                   "-ex", "thread apply all bt 40", "--args", sys.executable, "-m", "pytest",
                   "-vv", "--durations=1", "-o", f"faulthandler_timeout={trace}",
                   f"--junitxml={output / 'pytest.xml'}", NODE]
        write(output / "COMMAND.json", command)
        result = verdict(output, supervise(command, root, output, env), trace)
        # Persist execution evidence before any fallible post-run byte check.
        write(output / "PROCESS.json", result)
        result["process_outcome"] = result["outcome"]
        try:
            after = snapshot(root, version)
            write(output / "AFTER_BINDINGS.json", after)
            result["bound_bytes_unchanged"] = after == before
            if after != before:
                result["outcome"] = "BOUND_BYTES_CHANGED"
        except (OSError, ValueError, subprocess.SubprocessError,
                importlib.metadata.PackageNotFoundError) as exc:
            result["bound_bytes_unchanged"] = False
            result["binding_error"] = type(exc).__name__ + ": " + str(exc)
            result["outcome"] = "AFTER_BINDING_FAILURE"
            write(output / "AFTER_ERROR.json", {"error": result["binding_error"]})
        result["artifacts"] = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(output / "RESULT.json", result)
        return 0 if result["outcome"] in ("NOT_REPRODUCED", "CONTROL_COMPLETED") else 1
    except Exception as exc:
        write(output / "FAILED.json", {"error": type(exc).__name__ + ": " + str(exc),
              "finished_at": datetime.now(timezone.utc).isoformat(), "automatic_retry": False})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", required=True, choices=("3.10.21", "3.12.14"))
    parser.add_argument("--trace", required=True, type=int, choices=(0, 120))
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.python, args.trace))
