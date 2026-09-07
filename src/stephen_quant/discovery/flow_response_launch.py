"""Once-only, evidence-bound V11.21 launch; no factor/threshold search knobs.

Prepare reads frozen hashes, prior evidence and DATE-only coverage. Only launch
can claim this parent/version, reserve the complete budget and start numerical
children. Local integrity receipts are not a multi-user security boundary.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.qmt.data_warehouse import _duckdb
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_failure import FAILED_CLAIM_KEY, FAILED_PLAN_SHA, failed_epoch_evidence
from .flow_response_protocol import (
    BASE_DEBT,
    BUDGET,
    DEBT,
    VERSION,
    candidate_packet,
    check_complete_reservations,
    contract,
    plans,
    reserve_trials,
    screen_records,
)
from .response_resources import process_memory
from .response_supervisor import ResourceLimits, supervise
from .search_power_dsl import sha256_json

PARENT_SHA = "04dbbf1224bd50016d33d30cec145ffbbdefa0649a118c215bd1110d846f83fe"
AUDIT_SHA = "43808b722f9c0c30ccd09b24b4ef8b2b5fe0e733bafa005aeab444d958cedba5"
SNAPSHOT_SHA = "b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51"
CARD_SHA = "c854fad704e08902051a3c4f2f25fdaeb8c9e7d32cda6b69bb76bf3fc6302134"
REPO = "m-stephen/stephen-quant-agent"
ISSUE_URL = f"https://api.github.com/repos/{REPO}/issues/184"
# Fixed before any empirical read. Each stage has at most four hours, not a
# speed guarantee derived from the much smaller B5b synthetic population.
LIMITS = ResourceLimits(10 * 1024**3, 4 * 1024**3, 14400, 0.2)
DRIVER = "scripts/run_flow_response.py"
CLAIM_KEY = sha256_json({"version": VERSION, "parent": PARENT_SHA})
_SECRETS = {"ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL"}


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def now():
    return datetime.now(timezone.utc).isoformat()


def _env():
    return {k: v for k, v in os.environ.items() if k.upper() not in _SECRETS}


def _git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args],
        text=True,
        env=_env(),
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).strip()


def layout(worktree):
    root = Path(worktree).resolve(strict=True)
    if Path(_git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("exact current worktree root required")
    common = Path(_git(root, "rev-parse", "--git-common-dir"))
    common = (root / common).resolve(strict=True)
    if common.name != ".git" or not common.is_dir():
        raise ValueError("expected shared repository .git directory")
    base = common.parent / "artifacts/worktrees"
    return {
        "worktree": root,
        "parent": base / "v11.20-gross-net-attribution/artifacts/gross-net/epoch-001",
        "inputs": base / "v11.4-research-reliability/artifacts/reliable-research/epoch-002/inputs",
        "original": base / "v11.11-temporal-increments",
        "claim": common.parent / f"artifacts/flow-response-global-claims/{CLAIM_KEY}.json",
        "failed_epoch": base
        / f"v11.21-flow-response/artifacts/flow-response/epochs/{FAILED_PLAN_SHA}",
        "failed_claim": common.parent
        / f"artifacts/flow-response-global-claims/{FAILED_CLAIM_KEY}.json",
    }


def _bound(root, relative, expected=None):
    root = Path(root).resolve(strict=True)
    path = root / relative
    if root not in path.resolve(strict=True).parents or not path.is_file():
        raise ValueError("frozen evidence path escape or non-file")
    digest = file_sha(path)
    if expected is not None and digest != expected:
        raise ValueError("frozen evidence bytes changed")
    return digest


class ReadOnlyRegistry(ExperimentRegistry):
    """Reuse native query methods without schema initialization or DB writes."""

    def initialize(self):
        if not self.db_path.is_file():
            raise ValueError("existing native database required")

    @contextmanager
    def connect(self):
        self.initialize()
        connection = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            yield connection
        finally:
            connection.close()


def parent_evidence(root):
    files = {
        "RESULT.json": _bound(root, "RESULT.json", PARENT_SHA),
        "INDEPENDENT_AUDIT.json": _bound(root, "INDEPENDENT_AUDIT.json", AUDIT_SHA),
    }
    result, audit = read(root / "RESULT.json"), read(root / "INDEPENDENT_AUDIT.json")
    if (
        audit["pass"] is not True
        or result["raw_global_trial_lower_bound"] != BASE_DEBT
        or result["completed_trials"] != 12
        or result["reserved_trials"] != 12
        or result["engineering_pass"] is not True
        or result["protected_unchanged"] is not True
        or result["validated_alpha"] is not False
        or result["screen_survived"] != {"linear": False, "quadratic": False}
    ):
        raise ValueError("fixed completed parent debt/verdict/audit required")
    for name in (
        "RESULT.json",
        "registry.sqlite3",
        "inherited_lineage.json",
        "frozen_spec.json",
        "first_read_reservations.json",
    ):
        files[name] = _bound(root, name, audit["evidence_hashes"][name])
    expected = {p["key"] for p in result["spec"]["plans"]}
    if len(expected) != 12 or set(result["records"]) != expected:
        raise ValueError("all twelve parent outcomes required")
    with ReadOnlyRegistry(root / "registry.sqlite3").connect() as db:
        rows = db.execute(
            "SELECT t.hyperparams,t.result_json,c.stages_json,e.code_version,e.search_space "
            "FROM trials t JOIN trial_fit_contracts c USING(trial_id) "
            "JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(rows) != 12 or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("parent requires twelve replays and zero new fits")
        seen = set()
        for hp, raw, stages, code, space in rows:
            p, record = json.loads(hp), json.loads(raw)
            if (
                p not in result["spec"]["plans"]
                or record != result["records"][p["key"]]
                or json.loads(stages) != []
                or code != result["spec"]["runtime_code_sha256"]
                or sha256_json(json.loads(space)) != sha256_json(result["spec"])
                or record["inherited_receipt_sha256"] != files["inherited_lineage.json"]
                or record["fit_lineage_sha256"] != sha256_json([])
            ):
                raise ValueError("parent native result/contract/lineage mismatch")
            seen.add(p["key"])
        if seen != expected:
            raise ValueError("duplicate or omitted native parent outcome")
    if file_sha(root / "registry.sqlite3") != files["registry.sqlite3"]:
        raise ValueError("parent native database changed during preflight")
    return files


def source_evidence(root):
    manifest_hash = _bound(root, "manifest.json")
    manifest = read(root / "manifest.json")
    sources = manifest["sources"]
    if (
        len(sources) != 5
        or {s["source"] for s in sources} != {"daily", "fund_flow", "auction", "chip", "minute"}
        or sha256_json(sources) != SNAPSHOT_SHA
        or manifest["snapshot_sha256"] != SNAPSHOT_SHA
        or manifest["exposed_sealed_rows"] != 0
    ):
        raise ValueError("original five-source manifest required; only two files may be read")
    declared = {s["source"]: s for s in sources}
    files = {"manifest.json": manifest_hash}
    for name in ("daily", "fund_flow"):
        item = declared[name]
        if item["file"] != name + ".parquet" or item["max_date"] >= "2025-01-01":
            raise ValueError("fixed daily/flow filename and pre-2025 coverage required")
        files[item["file"]] = _bound(root, item["file"], item["sha256"])
    # Only a date column is projected before reservation, never financial values.
    with _duckdb().connect(":memory:") as db:
        calendar = [
            str(r[0])
            for r in db.execute(
                "SELECT DISTINCT trade_date FROM read_parquet(?) "
                "WHERE trade_date BETWEEN DATE '2022-01-01' AND DATE '2024-12-31' "
                "ORDER BY trade_date",
                [str(root / "daily.parquet")],
            ).fetchall()
        ]
    if {d[:4] for d in calendar} != {"2022", "2023", "2024"}:
        raise ValueError("all three frozen calendar years required")
    return files, calendar


def original_evidence(root):
    name = "configs/v11.11-frozen-stability-observation.json"
    files = {name: _bound(root, name, CARD_SHA)}
    card = read(root / name)
    for policy in ("lowvol", "stable_lowrisk"):
        name = f"artifacts/temporal-increments/epoch-001/targets/{policy}.json"
        # Hash raw target bytes; do not decode portfolio weights at prepare time.
        files[name] = _bound(root, name, card["targets_file_sha256"][policy])
    return files


def code_evidence(root):
    if _git(root, "status", "--porcelain"):
        raise ValueError("clean committed runtime required")
    commit = _git(root, "rev-parse", "HEAD")
    files = {
        p.relative_to(root).as_posix(): file_sha(p)
        for p in sorted((root / "src/stephen_quant").rglob("*.py"))
    }
    files[DRIVER] = _bound(root, DRIVER)
    return {
        "commit": commit,
        "files": files,
        "sha256": sha256_json(files),
        "python": sys.version,
        "executable_sha256": file_sha(sys.executable),
        "packages": {n: version(n) for n in ("numpy", "duckdb")},
    }


def prepare_plan(worktree):
    paths = layout(worktree)
    code = code_evidence(paths["worktree"])
    parent = parent_evidence(paths["parent"])
    failure = failed_epoch_evidence(paths["failed_epoch"], paths["failed_claim"])
    if failure["prior_debt"] != BASE_DEBT or failure["inherited_debt"] != DEBT:
        raise ValueError("verified failed-epoch debt must augment fixed parent debt")
    original = original_evidence(paths["original"])
    sources, calendar = source_evidence(paths["inputs"])
    spec = {
        "calendar": calendar,
        "contract": contract(),
        "plans": plans(),
        "packet": candidate_packet(),
        "manifest_sha256": SNAPSHOT_SHA,
        "anchor_card_sha256": CARD_SHA,
        "runtime_code_sha256": code["sha256"],
        "failed_epoch_evidence_sha256": sha256_json(failure),
    }
    return {
        "version": VERSION,
        "claim_key": CLAIM_KEY,
        "paths": {k: str(p) for k, p in paths.items()},
        "spec": spec,
        "evidence": {
            "code": code,
            "parent": parent,
            "sources": sources,
            "original": original,
            "failed_epoch": failure,
        },
        "limits": asdict(LIMITS),
        "parent_debt": DEBT,
        "committed_attempt_budget": BUDGET,
        "preregistration_issue": ISSUE_URL,
        "automatic_retry": False,
        "validated_alpha": False,
    }


def verify_plan(plan, worktree):
    if sha256_json(plan) != sha256_json(prepare_plan(worktree)):
        raise ValueError("plan differs from actual frozen evidence/code/protocol")
    return sha256_json(plan)


def fetch_preregistration(comment_id, plan_sha256, worktree):
    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("actual positive Issue184 preregistration comment ID required")
    try:
        raw = subprocess.check_output(
            ["gh", "api", "--hostname", "github.com", f"repos/{REPO}/issues/comments/{comment_id}"],
            cwd=worktree,
            env=_env(),
            stderr=subprocess.PIPE,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("GitHub preregistration verification unavailable; no launch") from exc
    obj = json.loads(raw)
    marker = f"V11.21-PREREGISTRATION-SHA256: {plan_sha256}"
    created = datetime.fromisoformat(obj["created_at"].replace("Z", "+00:00"))
    updated = datetime.fromisoformat(obj["updated_at"].replace("Z", "+00:00"))
    if (
        obj["id"] != comment_id
        or obj["issue_url"] != ISSUE_URL
        or marker not in obj["body"].splitlines()
        or created.utcoffset() is None
        or updated.utcoffset() is None
        or not created <= updated <= datetime.now(timezone.utc)
    ):
        raise ValueError("preregistration identity/plan/time mismatch")
    return {"comment": obj, "fetched_at": now(), "plan_sha256": plan_sha256}


def _resource_preflight():
    if os.name != "nt":
        raise ValueError("owned production resource measurement requires Windows")
    limits = LIMITS
    limits.validate()
    memory = process_memory()
    free = memory.get("physical_available_bytes")
    if type(free) is not int or free < limits.minimum_free_physical_bytes:
        raise ValueError("free physical RAM is unavailable or below the frozen floor")
    return memory


def _operation(plan, digest):
    return Path(plan["paths"]["worktree"]) / f"artifacts/flow-response/epochs/{digest}"


def launch(plan_path, *, comment_id, worktree):
    plan = read(plan_path)
    digest = verify_plan(plan, worktree)
    comment = fetch_preregistration(comment_id, digest, worktree)
    memory = _resource_preflight()
    output, claim_path = _operation(plan, digest), Path(plan["paths"]["claim"])
    if output.exists():
        raise FileExistsError("operation exists; no automatic replay")
    claim = {
        "version": VERSION,
        "parent_sha256": PARENT_SHA,
        "plan_sha256": digest,
        "operation": str(output),
        "preregistration_sha256": sha256_json(comment),
        "committed_attempt_budget": BUDGET,
        "prior_debt": DEBT,
        "claimed_at": now(),
        "prelaunch_memory": memory,
        "automatic_retry": False,
    }
    write(claim_path, claim)  # Shared git-common-dir, not a worktree-local claim.
    stage, outcome, receipts = "reservation", "FAILED", {}
    error_type, native_error = None, None
    native_count = 0
    try:
        output.mkdir(parents=True, exist_ok=False)
        write(output / "LAUNCH.json", {"plan": plan, "claim_sha256": file_sha(claim_path)})
        write(output / "PREREGISTRATION.json", comment)
        registry, tids = reserve_trials(output, plan["spec"])
        proof = check_complete_reservations(registry, tids)
        native_count = registry.global_trial_count()
        write(output / "RESERVATIONS.json", {"trial_ids": tids, **proof})
        hashes = {
            "plan": digest,
            "claim": file_sha(claim_path),
            "preregistration": sha256_json(comment),
        }
        for stage in ("backend", "audit"):
            receipts[stage] = supervise(
                [sys.executable, str(Path(worktree) / DRIVER), stage, "--operation", str(output)],
                cwd=worktree,
                output=output / f"supervisor-{stage}",
                limits=LIMITS,
                evidence_hashes=hashes,
            )
            if receipts[stage]["outcome"] != "COMPLETED":
                raise RuntimeError("owned stage did not complete; budget preserved, no retry")
            if stage == "backend":
                result = read(output / "RESULT.json")
                if result["status"] != "COMPLETE_PENDING_INDEPENDENT_AUDIT":
                    raise ValueError("complete backend result required before audit")
                write(
                    output / "BACKEND_COMPLETED.json",
                    {
                        "result_sha256": file_sha(output / "RESULT.json"),
                        "registry_sha256": file_sha(output / "registry.sqlite3"),
                        "supervisor_sha256": file_sha(
                            output / "supervisor-backend/SUPERVISOR.json"
                        ),
                    },
                )
            else:
                if read(output / "AUDIT.json")["pipeline_audit_pass"] is not True:
                    raise ValueError("complete independent audit required")
                if read(output / "ASSESSMENT.json")["validated_alpha"] is not False:
                    raise ValueError("exploratory screen cannot certify Alpha")
        verify_plan(plan, worktree)
        outcome = "COMPLETE_EXPLORATORY_AUDITED"
    except BaseException as exc:
        error_type = type(exc).__name__
        raise
    finally:
        # A claimed attempt never vanishes even if reservation/launch failed.
        if (output / "registry.sqlite3").is_file():
            try:
                native_count = ReadOnlyRegistry(output / "registry.sqlite3").global_trial_count()
            except (OSError, sqlite3.Error, ValueError) as exc:
                native_count, native_error = None, type(exc).__name__
        receipt = {
            "outcome": outcome,
            "last_stage": stage,
            "plan_sha256": digest,
            "native_reserved": native_count,
            "committed_attempt_budget": BUDGET,
            "raw_global_trial_lower_bound": DEBT + BUDGET,
            "finished_at": now(),
            "automatic_retry": False,
            "validated_alpha": False,
            "stages": receipts,
            "exception_type": error_type,
            "native_count_error": native_error,
        }
        write(claim_path.with_name(claim_path.stem + ".terminal.json"), receipt)
    return receipt


def run_stage(stage, *, operation, worktree):
    if stage not in ("backend", "audit"):
        raise ValueError("only backend/audit stages exist")
    root = Path(operation).resolve(strict=True)
    envelope = read(root / "LAUNCH.json")
    plan = envelope["plan"]
    digest = verify_plan(plan, worktree)
    if root != _operation(plan, digest).resolve():
        raise ValueError("operation is not the bound launch path")
    claim_path = Path(plan["paths"]["claim"])
    if file_sha(claim_path) != envelope["claim_sha256"]:
        raise ValueError("shared global claim changed")
    claim, comment = read(claim_path), read(root / "PREREGISTRATION.json")
    if (
        claim["operation"] != str(root)
        or claim["plan_sha256"] != digest
        or claim["preregistration_sha256"] != sha256_json(comment)
        or claim["committed_attempt_budget"] != BUDGET
        or claim["prior_debt"] != DEBT
        or claim["parent_sha256"] != PARENT_SHA
        or claim_path.with_name(claim_path.stem + ".terminal.json").exists()
    ):
        raise ValueError("complete active global launch evidence required")
    reservation = read(root / "RESERVATIONS.json")
    tids = reservation["trial_ids"]
    if (
        sha256_json(tids) != reservation["native_trial_ids_sha256"]
        or reservation["reserved"] != BUDGET
    ):
        raise ValueError("complete native reservation receipt required")
    write(root / f"CHILD_{stage}.json", {"started_at": now(), "plan_sha256": digest})
    if stage == "backend":
        from stephen_quant.workflows.flow_response_epoch import execute_reserved_epoch

        registry = ExperimentRegistry(root / "registry.sqlite3")
        check_complete_reservations(registry, tids)
        execute_reserved_epoch(
            registry,
            tids,
            plan["spec"],
            output=root,
            input_folder=plan["paths"]["inputs"],
            original_tree=plan["paths"]["original"],
        )
    else:
        from .flow_response_epoch_audit import audit_complete_epoch

        completed = read(root / "BACKEND_COMPLETED.json")
        supervisor = read(root / "supervisor-backend/SUPERVISOR.json")
        if (
            supervisor["outcome"] != "COMPLETED"
            or supervisor["exit_code"] != 0
            or supervisor["samples"] < 1
            or file_sha(root / "supervisor-backend/SUPERVISOR.json")
            != completed["supervisor_sha256"]
            or file_sha(root / "RESULT.json") != completed["result_sha256"]
            or file_sha(root / "registry.sqlite3") != completed["registry_sha256"]
        ):
            raise ValueError("verified producer exit and immutable outputs required before audit")
        audit = audit_complete_epoch(
            ReadOnlyRegistry(root / "registry.sqlite3"),
            operation=root,
            input_folder=plan["paths"]["inputs"],
            original_tree=plan["paths"]["original"],
        )
        verify_plan(plan, worktree)
        if (
            file_sha(root / "registry.sqlite3") != completed["registry_sha256"]
            or file_sha(root / "RESULT.json") != completed["result_sha256"]
            or audit["pipeline_audit_pass"] is not True
        ):
            raise ValueError("audit must preserve native outputs and pass every stage")
        write(root / "AUDIT.json", audit)
        result = read(root / "RESULT.json")
        assessment = screen_records(
            result["records"], result["diagnostics"], independent_audit_pass=True
        )
        write(
            root / "ASSESSMENT.json",
            {
                **assessment,
                "result_sha256": completed["result_sha256"],
                "audit_sha256": file_sha(root / "AUDIT.json"),
                "plan_sha256": digest,
                "statistics": plan["spec"]["contract"]["statistics"],
                "interpretation": "reused development evidence;not fresh OOS or Alpha Court",
            },
        )
