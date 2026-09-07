"""Bind the frozen market run to its immutable Git source, not a later hotfix."""

import hashlib
import json
import subprocess
from pathlib import Path

from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.workflows.v114_reliable_epoch import runtime_code_hash, write_json

COMMIT = "9bd9eaeaa8405272593227cb588ed6968d3d279d"
ROOT = Path("artifacts/stability-attribution/epoch-001")


def verify():
    names = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", COMMIT, "src/stephen_quant"], text=True
    ).splitlines()
    names = sorted(n for n in names if n.endswith(".py"))
    raw = subprocess.check_output(
        ["git", "cat-file", "--batch"], input="".join(f"{COMMIT}:{n}\n" for n in names).encode()
    )
    offset, hashes = 0, {}
    for name in names:
        newline = raw.index(b"\n", offset)
        size = int(raw[offset:newline].split()[-1])
        blob = raw[newline + 1 : newline + 1 + size]
        offset = newline + 1 + size + 1
        normalized = blob.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        hashes[name.removeprefix("src/stephen_quant/")] = hashlib.sha256(
            normalized.encode()
        ).hexdigest()
    frozen_hash = sha256_json(hashes)
    result = json.loads((ROOT / "RESULT.json").read_text(encoding="utf-8"))
    if frozen_hash != result["spec"]["runtime_code_sha256"]:
        raise ValueError("market run source commit mismatch")
    counts = {
        k: {f: r["metrics"][f] for f in ("writeoff_events", "recovery_events")}
        for k, r in result["records"].items()
    }
    if any(any(v.values()) for v in counts.values()):
        raise ValueError(
            "real accounts may exercise fixed writeoff branch; new registered run required"
        )
    evidence = {
        "pass": True,
        "market_runtime_commit": COMMIT,
        "market_runtime_sha256": frozen_hash,
        "post_run_patch_runtime_sha256": runtime_code_hash(),
        "market_accounts_rerun": False,
        "new_trials": 0,
        "actual_writeoff_recovery_counts": counts,
        "basis": "Frozen source reconstructed from Git; zero writeoff/recovery events in all12accounts. Patch only retains pending intent for written-down positions. Synthetic recovery/capacity regression passes;not an empirical rerun of patched code.",
    }
    write_json(ROOT / "CODE_REVISION_AUDIT.json", evidence)
    write_json(Path("docs/V11_13_1_CODE_REVISION.json"), evidence)
    print(json.dumps({k: v for k, v in evidence.items() if k != "actual_writeoff_recovery_counts"}))


if __name__ == "__main__":
    verify()
