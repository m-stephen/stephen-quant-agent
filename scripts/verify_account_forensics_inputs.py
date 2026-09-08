"""V12.3 metadata/hash-only preflight, not the numerical forensic report runner."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stephen_quant.discovery.account_forensics_evidence import (
    completed_inputs,
    verify_unchanged,
)
from stephen_quant.discovery.flow_response_launch import _git, now, write
from stephen_quant.qmt.reliable_panel import file_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    allowed = (ROOT / "artifacts/account-forensics").resolve()
    if output == allowed or not output.is_relative_to(allowed):
        raise ValueError("exclusive child of this worktree's forensic artifact folder required")
    if _git(ROOT, "status", "--porcelain"):
        raise ValueError("commit the reviewed metadata checker before verification")
    output.mkdir(parents=True, exist_ok=False)
    write(output / "START.json", {
        "started_at": now(), "scope": "metadata_hash_only",
        "code_commit": _git(ROOT, "rev-parse", "HEAD"),
        "driver_sha256": file_sha(Path(__file__)),
    })
    try:
        evidence = completed_inputs(ROOT)
        write(output / "INPUTS.json", evidence)
        receipt = verify_unchanged(evidence)
        write(output / "VERIFICATION.json", receipt)
    except BaseException as exc:
        write(output / "TERMINAL.json", {
            "finished_at": now(), "outcome": "FAILED", "error_type": type(exc).__name__,
            "scope": "metadata_hash_only", "new_accounts": 0, "new_predictions": 0})
        raise
    write(output / "TERMINAL.json", {
        "finished_at": now(), "outcome": "INPUT_BINDINGS_VERIFIED",
        "scope": "metadata_hash_only", "new_accounts": 0, "new_predictions": 0,
        "raw_global_trial_lower_bound": 3737, "validated_alpha": False})
    print("INPUT_BINDINGS_VERIFIED;12 saved accounts;0 new accounts;0 predictions;not Alpha")


if __name__ == "__main__":
    main()
