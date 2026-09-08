"""Explicit once-only synthetic launcher integration, never a production entrypoint.

Manual prepare freezes engineering inputs; run needs a separately reviewed slot.
Only provenance/path/preregistration boundaries are adapted. Numeric algorithms,
plan equality, process supervision, rendering and final acceptance stay real.
This module is deliberately outside pytest collection and the production CLI.
The production forensic chain retains its4h limit; outer setup and end-of-run
checkpoints additionally refuse success after4h. This is not continuous hard
supervision over fixture setup or a single OS-enforced whole-script deadline.
"""

import argparse
import sys
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from stephen_quant.discovery import account_forensics_launch as runner
from stephen_quant.discovery import account_forensics_plan as planner
from stephen_quant.discovery.account_forensics_acceptance import exact, read
from stephen_quant.discovery.account_forensics_evidence import bind_files, verify_unchanged
from stephen_quant.discovery.flow_response_launch import now, write
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha

SLOT = ROOT / "artifacts/v123-launcher-orchestration-once"
DRIVER = "tests/support/account_forensics_orchestration.py"
FIXTURES = (
    "tests/test_account_forensics_runtime.py",
    "tests/test_account_forensics_inputs.py",
    "tests/test_account_forensics_persistence.py",
)
BOUNDARIES = ["synthetic_parent_identity", "isolated_claim_and_operations",
              "frozen_test_code_manifest_not_git_cleanliness", "fixed_offline_preregistration",
              "test_only_worker_entrypoint"]


def code_bytes():
    files = {p.relative_to(ROOT).as_posix(): file_sha(p)
             for p in sorted((ROOT / "src/stephen_quant").rglob("*.py"))}
    files.update({name: file_sha(ROOT / name) for name in (DRIVER, *FIXTURES,
        "scripts/run_account_forensics.py", "scripts/run_flow_response.py")})
    return {"files": files, "sha256": sha256_json(files), "synthetic_not_git_cleanliness": True}


def frozen_start():
    snapshot = read(SLOT / "frozen/PREPARED.json")
    exact(snapshot["code"], code_bytes())
    exact(snapshot["runtime"], planner.runtime_evidence())
    exact(snapshot["slot"], str(SLOT))
    exact(snapshot["adapted_boundaries"], BOUNDARIES)
    exact(snapshot["limits"], planner.asdict(runner.LIMITS))
    exact(snapshot["synthetic_only"], True)
    exact(snapshot["automatic_retry"], False)
    return snapshot


def prepare():
    runner.require_host()
    # Metadata only. Existing slots are never overwritten or silently reused.
    if SLOT.exists():
        raise FileExistsError("synthetic orchestration slot already exists")
    snapshot = {"slot": str(SLOT), "prepared_at": now(), "code": code_bytes(),
                "runtime": planner.runtime_evidence(), "limits": planner.asdict(runner.LIMITS),
                "adapted_boundaries": BOUNDARIES, "synthetic_only": True,
                "automatic_retry": False, "validated_alpha": False}
    write(SLOT / "frozen/PREPARED.json", snapshot)
    print("PREPARED", sha256_json(snapshot), flush=True)


class PersistentFactory:
    """Minimal fixture factory; cannot delete or reuse a prior fixture directory."""

    def mktemp(self, name):
        if name != "forensic-synthetic":
            raise ValueError("fixed synthetic fixture directory required")
        root = SLOT / "fixture"
        root.mkdir(exist_ok=False)
        return root


def create_fixture():
    from test_account_forensics_inputs import synthetic_calendar
    from test_account_forensics_runtime import artifacts

    # This is new setup for the first complete launcher integration, not a
    # replay of the old17-test slot or an attempt to recreate its lost evidence.
    evidence, calendar_binding = artifacts.__wrapped__(PersistentFactory())
    parent = {"synthetic_only": True, "evidence": {"parent": {"calendar": synthetic_calendar()}},
              "spec": {"calendar": calendar_binding}}
    metadata = SLOT / "frozen"
    write(metadata / "LAUNCH.json", {"plan": parent})
    evidence["bindings"]["operation"] = bind_files(metadata, {
        "LAUNCH.json": file_sha(metadata / "LAUNCH.json")})
    manifest = {"input_evidence": evidence, "parent_sha256": sha256_json(parent),
                "calendar_binding": calendar_binding, "synthetic_only": True,
                "setup_native_cost_accounts": 2, "saved_account_identities": 12,
                "market_trial_delta": 0, "validated_alpha": False}
    write(SLOT / "frozen/FIXTURE.json", manifest)
    return manifest


def install_boundaries():
    """Parent and child install the same finite test-only metadata adapter.

    Neither prepare_plan nor verify_plan is replaced. There is no fit/predict,
    account/reference, supervisor, memory guard or report-return substitution.
    """
    frozen_start()
    fixture = read(SLOT / "frozen/FIXTURE.json")
    exact(fixture["synthetic_only"], True)
    planner.PLAN = fixture["parent_sha256"]
    planner.COMMIT = "SYNTHETIC_PARENT_NOT_A_GIT_COMMIT"
    planner.CLAIM_KEY = runner.CLAIM_KEY = sha256_json(planner.scope())
    planner.DRIVER = runner.DRIVER = DRIVER

    def paths(worktree):
        exact(Path(worktree).resolve(), ROOT)
        return {"worktree": ROOT, "operations": SLOT / "epochs",
                "claim": SLOT / "isolated-shared" / f"{planner.CLAIM_KEY}.json"}

    def code_snapshot(worktree):
        exact(Path(worktree).resolve(), ROOT)
        return frozen_start()["code"]

    def completed_inputs(worktree):
        exact(Path(worktree).resolve(), ROOT)
        actual = read(SLOT / "frozen/FIXTURE.json")
        exact(actual, fixture)
        verify_unchanged(actual["input_evidence"])
        # FIXTURE itself becomes a bound input, as do its explicit sources.
        evidence = actual["input_evidence"]
        evidence["bindings"]["synthetic_manifest"] = bind_files(SLOT / "frozen", {
            "FIXTURE.json": file_sha(SLOT / "frozen/FIXTURE.json"),
            "PREPARED.json": file_sha(SLOT / "frozen/PREPARED.json")})
        return evidence

    def preregistration(comment_id, plan_sha, worktree):
        exact(Path(worktree).resolve(), ROOT)
        exact(comment_id, 1)
        saved = read(SLOT / "OFFLINE_PREREGISTRATION.json")
        planner.validate_preregistration(saved["comment"], comment_id, plan_sha)
        exact(saved["plan_sha256"], plan_sha)
        exact(saved["synthetic_offline_not_github_approval"], True)
        return saved

    planner.paths = runner.paths = paths
    planner.code_snapshot = runner.code_snapshot = code_snapshot
    planner.completed_inputs = completed_inputs
    runner.fetch_preregistration = preregistration


def run():
    runner.require_host()
    snapshot = frozen_start()
    write(SLOT / "START.json", {"started_at": now(), "prepared_sha256": sha256_json(snapshot),
                               "synthetic_only": True, "automatic_retry": False})
    started, error, checked = monotonic(), None, None
    try:
        runner.resource_guard(started)
        create_fixture()
        runner.resource_guard(started)
        install_boundaries()
        plan = planner.prepare_plan(ROOT)  # Actual production comparison path.
        write(SLOT / "PLAN.json", plan)
        digest = planner.verify_plan(plan, ROOT)
        stamp = now()
        write(SLOT / "OFFLINE_PREREGISTRATION.json", {
            "plan_sha256": digest, "fetched_at": stamp,
            "synthetic_offline_not_github_approval": True, "comment": {
                "id": 1, "issue_url": planner.ISSUE_URL,
                "body": f"V12.3-FORENSICS-PLAN-SHA256: {digest}\n{planner.RISK_LINE}",
                "created_at": stamp, "updated_at": stamp}})
        result = runner.launch(SLOT / "PLAN.json", comment_id=1, worktree=ROOT)
        exact(result["outcome"], runner.SUCCESS)
        operation = planner.operation_path(plan)
        exact(read(operation / "FINAL.json"), result)
        exact(read(Path(plan["paths"]["claim"]).with_suffix(".terminal.json")), result)
        supervisor = read(operation / "supervisor/SUPERVISOR.json")
        exact(read(operation / "LAUNCH.json")["launcher_pid"], runner.os.getpid())
        exact(read(operation / "WORKER_STARTED.json")["pid"], supervisor["pid"])
        if supervisor["pid"] == runner.os.getpid():
            raise ValueError("actual separate child required")
        acceptance = read(operation / "ACCEPTANCE.json")
        exact(len(acceptance["verified_artifact_files"]), 57)
        summary = read(operation / "saved-report/SUMMARY.json")
        exact(summary["account_count"], 12)
        exact(summary["source_query"]["requested_keys"], 26)
        exact(summary["source_query"]["matched_rows"], 2)
        exact(summary["source_query"]["absent_keys"], 24)
        before = {p.relative_to(operation).as_posix(): file_sha(p)
                  for p in sorted(operation.rglob("*")) if p.is_file()}
        try:
            runner.launch(SLOT / "PLAN.json", comment_id=1, worktree=ROOT)
        except FileExistsError:
            pass
        else:
            raise AssertionError("consumed integration claim replay was accepted")
        exact(before, {p.relative_to(operation).as_posix(): file_sha(p)
                       for p in sorted(operation.rglob("*")) if p.is_file()})
        frozen_start()
        verify_unchanged(plan["input_evidence"])
        runner.resource_guard(started)
        checked = {"operation": str(operation), "operation_files": before,
                   "parent_pid": runner.os.getpid(), "child_pid": supervisor["pid"],
                   "replay_refused_without_output_change": True,
                   "supervisor_sha256": file_sha(operation / "supervisor/SUPERVISOR.json")}
    except BaseException as exc:  # noqa: BLE001 -- retain failure then re-raise, never retry.
        error = exc
    terminal = {"outcome": "SYNTHETIC_ORCHESTRATION_VERIFIED" if error is None else "FAILED",
                "finished_at": now(), "elapsed_seconds": monotonic() - started,
                "error_type": type(error).__name__ if error else None,
                "checks": checked, "prepared_sha256": sha256_json(snapshot),
                "adapted_boundaries": BOUNDARIES, "synthetic_only": True,
                "automatic_retry": False, "market_trial_delta": 0, "validated_alpha": False,
                "native_runtime_root_cause_fixed": False}
    write(SLOT / "FINAL.json", terminal)
    if error:
        raise error
    print(terminal["outcome"], flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    commands.add_parser("run")
    commands.add_parser("worker").add_argument("--operation", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run()
    else:
        install_boundaries()
        runner.run_worker(args.operation, ROOT)


if __name__ == "__main__":
    main()
