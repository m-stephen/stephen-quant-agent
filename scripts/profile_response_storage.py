"""Bounded, synthetic-only JSON storage stress test; never an empirical launch.

Expand a fixed previously generated synthetic history, not market observations.
Both implementations use identical canonical fixture bytes. This profiles only
loading/freezing/hashing, not source processing, model fitting or Alpha power.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.flow_response_storage import (
    FrozenDict,
    load_json,
    streaming_sha256_json,
)
from stephen_quant.discovery.response_resources import child_process_memory, process_memory
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

SOURCE = (
    ROOT
    / "artifacts/flow-response/source-power/b5b-paired-001/planted/operation/history/history.json"
)
SOURCE_SHA = "13fc4f5e5c8b405d222ec7b32f631e748abe9cd13496acc06f71033143b705b1"
SCALES = (1, 32)
MODES = ("legacy", "lower-copy")
COMMIT_LIMIT = 10 * 1024**3
FREE_FLOOR = 4 * 1024**3
TIME_LIMIT = 1200


def plan():
    return {
        "synthetic_only": True,
        "source_sha256": SOURCE_SHA,
        "source_kind": "previous synthetic planted history;not market or native evidence",
        "scales": list(SCALES),
        "modes": list(MODES),
        "limits": {
            "private_commit_bytes": COMMIT_LIMIT,
            "minimum_free_physical_bytes": FREE_FLOOR,
            "child_seconds": TIME_LIMIT,
            "poll_seconds": 0.2,
        },
        "code_sha256": {
            name: file_sha(ROOT / name)
            for name in (
                "scripts/profile_response_storage.py",
                "src/stephen_quant/discovery/flow_response_storage.py",
                "src/stephen_quant/discovery/response_resources.py",
            )
        },
        "checks": "same canonical content hash as fixture bytes; no altered models or outcomes",
        "empirical_trial_delta": 0,
        "validated_alpha": False,
        "scope": "JSON decode/freeze/canonical-hash only;not full-pipeline memory guarantee",
    }


def fixture(output, scale):
    if scale not in SCALES or file_sha(SOURCE) != SOURCE_SHA:
        raise ValueError("fixed synthetic source and scale required")
    source = load_json(SOURCE)
    names = sorted({n for rows in source["bars"].values() for n in rows})
    if len(names) != 160 or len(source["calendar"]) != 782:
        raise ValueError("unexpected synthetic source shape")
    ordinal = {n: i for i, n in enumerate(names)}
    path = output / f"fixture-{scale}.json"
    counts = {}
    dump_options = {"ensure_ascii": False, "sort_keys": True, "separators": (",", ":")}
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("{")
        # Canonical top-level order makes the file SHA an independent expected
        # canonical-content SHA. There are no provider, fit or approval claims.
        for key_index, key in enumerate(("bars", "calendar", "ranks", "synthetic_only")):
            if key_index:
                stream.write(",")
            json.dump(key, stream, **dump_options)
            stream.write(":")
            if key in ("bars", "ranks"):
                counts[key] = 0
                stream.write("{")
                for day_index, day in enumerate(sorted(source[key])):
                    if day_index:
                        stream.write(",")
                    json.dump(day, stream, **dump_options)
                    stream.write(":")
                    # One synthetic market day at a time; shared immutable value
                    # objects need no deep clone while serializing replicated IDs.
                    rows = {
                        f"synthetic-{copy * len(names) + ordinal[name]:06d}": value
                        for copy in range(scale)
                        for name, value in source[key][day].items()
                    }
                    counts[key] += len(rows)
                    json.dump(rows, stream, **dump_options)
                stream.write("}")
            else:
                json.dump(source["calendar"] if key == "calendar" else True, stream, **dump_options)
        stream.write("}")
    return {"file": path.name, "sha256": file_sha(path), "bytes": path.stat().st_size, **counts}


def legacy_freeze(value):
    # Exact prior whole-tree conversion, retained locally as a measurement control.
    if isinstance(value, dict):
        return FrozenDict({k: legacy_freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(legacy_freeze(v) for v in value)
    return value


def child(output, scale, mode):
    if load_json(output / "RESOURCE_PLAN.json") != plan():
        raise ValueError("resource plan or code changed")
    manifest = load_json(output / f"fixture-{scale}.manifest.json")
    path = output / manifest["file"]
    if file_sha(path) != manifest["sha256"] or path.stat().st_size != manifest["bytes"]:
        raise ValueError("resource fixture bytes changed")
    root = output / f"scale-{scale}-{mode}"
    start = time.perf_counter()

    def mark(stage):
        value = {"seconds": time.perf_counter() - start, **process_memory()}
        write_json(root / f"{stage}.json", value)
        return value

    mark("start")
    if mode == "legacy":
        document = json.loads(path.read_bytes())
        mark("decode")
        document = legacy_freeze(document)
    elif mode == "lower-copy":
        document = load_json(path, immutable=True)
    else:
        raise ValueError("fixed implementation required")
    mark("immutable")
    if mode == "legacy":
        digest = hashlib.sha256(
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
    else:
        digest = streaming_sha256_json(document)
    resources = mark("hashed")
    if digest != manifest["sha256"]:
        raise ValueError("canonical content differs from fixture bytes")
    write_json(
        root / "RESULT.json",
        {
            "mode": mode,
            "scale": scale,
            "content_sha256": digest,
            "resources": resources,
            "content_equal": True,
            "synthetic_only": True,
            "empirical_trial_delta": 0,
            "validated_alpha": False,
        },
    )


def supervised_child(output, scale, mode):
    root = output / f"scale-{scale}-{mode}"
    root.mkdir(exist_ok=False)
    env = {
        k: v for k, v in os.environ.items() if k not in ("ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL")
    }
    samples, reason, max_memory = 0, None, {}
    started = time.perf_counter()
    with (root / "process.log").open("x", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--output",
                str(output),
                "--scale",
                str(scale),
                "--mode",
                mode,
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            while process.poll() is None:
                try:
                    memory = child_process_memory(process)
                except OSError:
                    if process.poll() is not None:
                        break
                    raise
                samples += 1
                for key in ("peak_rss_bytes", "peak_private_commit_bytes"):
                    max_memory[key] = max(max_memory.get(key, 0), memory[key])
                if memory["peak_private_commit_bytes"] >= COMMIT_LIMIT:
                    reason = "private_commit_limit"
                elif memory["physical_available_bytes"] is None:
                    reason = "free_memory_measurement_unavailable"
                elif memory["physical_available_bytes"] < FREE_FLOOR:
                    reason = "free_physical_floor"
                elif time.perf_counter() - started > TIME_LIMIT:
                    reason = "time_limit"
                if reason:
                    process.terminate()  # Only this owned synthetic child.
                    break
                time.sleep(0.2)
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    receipt = {
        "scale": scale,
        "mode": mode,
        "exit_code": code,
        "stopped_by_guard": reason,
        "samples": samples,
        "seconds_including_hash_preflight": time.perf_counter() - started,
        **max_memory,
        "synthetic_only": True,
        "empirical_trial_delta": 0,
    }
    write_json(root / "SUPERVISOR.json", receipt)
    print(json.dumps(receipt), flush=True)
    return receipt


def run(output):
    if os.name != "nt":
        raise OSError("this bounded owned-child resource probe requires Windows")
    if shutil.disk_usage(ROOT).free < 12 * 1024**3:
        raise OSError("resource fixture needs12GiB free disk safety margin")
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "RESOURCE_PLAN.json", plan())
    receipts = []
    for scale in SCALES:
        manifest = fixture(output, scale)
        write_json(output / f"fixture-{scale}.manifest.json", manifest)
        print(json.dumps({"fixture": manifest}), flush=True)
        for mode in MODES:
            receipts.append(supervised_child(output, scale, mode))
    write_json(
        output / "RESOURCE_RESULT.json",
        {
            "children": receipts,
            "all_lower_copy_content_checks_pass": all(
                r["exit_code"] == 0 and r["stopped_by_guard"] is None
                for r in receipts
                if r["mode"] == "lower-copy"
            ),
            "synthetic_only": True,
            "empirical_trial_delta": 0,
            "validated_alpha": False,
            "scope": "storage only;no models or accounts rerun;not fullpipelineboundedmemory",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=MODES, help=argparse.SUPPRESS)
    parser.add_argument("--scale", type=int, choices=SCALES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    target = Path(args.output).resolve()
    if (ROOT / "artifacts/flow-response/resources").resolve() not in target.parents:
        raise ValueError("dedicated synthetic-resource subdirectory required")
    if args.mode is not None:
        if args.scale is None:
            raise ValueError("internal mode requires scale")
        child(target, args.scale, args.mode)
    else:
        if args.scale is not None:
            raise ValueError("scales are frozen; no individual scale search")
        run(target)
