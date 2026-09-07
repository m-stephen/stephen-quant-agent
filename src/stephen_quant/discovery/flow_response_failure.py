"""Read-only inheritance of the consumed epoch-1 source-join failure.

This is a finite correction, not a retry/reset knob. Hashes identify actual local
receipts; native rows separately prove the 23 reservations and absence of fits.
No financial source columns or credentials are read here.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .search_power_dsl import sha256_json

FAILED_PLAN_SHA = "14fb0a203d1c2524d4e6cfbe05bbfb91512a7b224faa1afc1a6a1bd336d374b9"
FAILED_CLAIM_KEY = "c6cdb872526de73594d2cbf82eb5b7857f0f2644a8fea7f12cde7d02668c7442"
FAILED_CODE_SHA = "54a5369af3e653d02890dc80d54bde8bc9b7e112a496d4d9b2bb0e68adbb3ba9"
FAILED_IDS_SHA = "d0c55a209ff5789d70fac4e5923f4cd32d2e1d2032d95b84e44ba46b74bf33d3"
CLAIM_SHA = "2289f6cba8ca450304a0d13df2af2198fafe5d50fc78e4ed27a618bf4f7a8fc2"
TERMINAL_SHA = "3d30d98533b45dccfb1c72816cdc06868b0e65eed08c76ce337ae67b8da90d4c"
FILES = {
    "LAUNCH.json": "06b3f86798aee2bf1d60580f36b72428f631be4f86027f562568afdc0d7c52e3",
    "registry.sqlite3": "47b756437b1c5e724fe817707fd4b24d72d9219556f6259688fa8c625815d364",
    "first_read_reservations.json": "c05f8f2f8b019a6b0df3dbbf97343d12cc65050d1d6ac52b46e7187a2e3aa9cc",
    "RESERVATIONS.json": "af2624c07d9cc414147af9af5f0779ed71780d9a4b124d308ca3c2f1b696f98e",
    "frozen_spec.json": "d27183155009c8c5fe8c7e4afbdda98f14841e3dc51ff4a17ebd94ea18cb75ee",
    "PREREGISTRATION.json": "887edace338343c87e8faa8c04e2140e7e562d1e2f88355ba56495b13933eabc",
    "CHILD_backend.json": "d006f5f303ac25cc47e0f3bb67b48a365de4e51966cd1882480f8c1613cee6a4",
    "supervisor-backend/SUPERVISOR.json": "624f483d58639ebef49378199be7919aca2db4785d4b92c79e67dca7495832b5",
    "supervisor-backend/process.log": "566187cb32a056cef7fad5c3e902193e0459081019deeb62cfdc919ad918a6f8",
}


def _read(path):
    return json.loads(path.read_bytes())


def _verify(root, relative, expected):
    path = root / relative
    if root not in path.resolve(strict=True).parents or file_sha(path) != expected:
        raise ValueError("consumed failed-epoch evidence changed")
    return expected


def failed_epoch_evidence(operation, claim_path):
    root, claim_path = Path(operation).resolve(strict=True), Path(claim_path)
    claim_root = claim_path.parent.resolve(strict=True)
    terminal_path = claim_path.with_name(claim_path.stem + ".terminal.json")
    files = {name: _verify(root, name, h) for name, h in FILES.items()}
    _verify(claim_root, claim_path.name, CLAIM_SHA)
    _verify(claim_root, terminal_path.name, TERMINAL_SHA)
    if any(
        (root / name).exists()
        for name in (
            "RESULT.json",
            "BACKEND_COMPLETED.json",
            "AUDIT.json",
            "ASSESSMENT.json",
            "CHILD_audit.json",
        )
    ):
        raise ValueError("failed pre-model epoch cannot contain completed outcomes")
    envelope, claim, terminal = _read(root / "LAUNCH.json"), _read(claim_path), _read(terminal_path)
    plan, spec = envelope["plan"], _read(root / "frozen_spec.json")
    reservation, first = (
        _read(root / "RESERVATIONS.json"),
        _read(root / "first_read_reservations.json"),
    )
    prereg, child = _read(root / "PREREGISTRATION.json"), _read(root / "CHILD_backend.json")
    supervisor = _read(root / "supervisor-backend/SUPERVISOR.json")
    tids = reservation["trial_ids"]
    if (
        sha256_json(plan) != FAILED_PLAN_SHA
        or envelope["claim_sha256"] != CLAIM_SHA
        or claim["plan_sha256"] != FAILED_PLAN_SHA
        or child["plan_sha256"] != FAILED_PLAN_SHA
        or terminal["plan_sha256"] != FAILED_PLAN_SHA
        or plan["claim_key"] != FAILED_CLAIM_KEY
        or Path(claim["operation"]).resolve() != root
        or Path(plan["paths"]["claim"]).resolve() != claim_path.resolve()
        or sha256_json(spec) != sha256_json(plan["spec"])
        or spec["runtime_code_sha256"] != FAILED_CODE_SHA
        or plan["evidence"]["code"]["sha256"] != FAILED_CODE_SHA
        or claim["preregistration_sha256"] != sha256_json(prereg)
        or prereg["plan_sha256"] != FAILED_PLAN_SHA
        or terminal["outcome"] != "FAILED"
        or terminal["last_stage"] != "backend"
        or terminal["native_reserved"] != 23
        or terminal["committed_attempt_budget"] != 23
        or terminal["raw_global_trial_lower_bound"] != 3683
        or claim["prior_debt"] != 3660
        or claim["committed_attempt_budget"] != 23
        or terminal["automatic_retry"] is not False
        or terminal["validated_alpha"] is not False
        or supervisor["outcome"] != "FAILED"
        or supervisor["exit_code"] != 1
        or supervisor["evidence_hashes"]
        != {"claim": CLAIM_SHA, "plan": FAILED_PLAN_SHA, "preregistration": sha256_json(prereg)}
        or len(tids) != 23
        or len(set(tids.values())) != 23
        or sha256_json(tids) != FAILED_IDS_SHA
        or reservation
        != {
            "trial_ids": tids,
            "native_trial_ids_sha256": FAILED_IDS_SHA,
            "reserved": 23,
            "prior_debt": 3660,
            "debt": 3683,
        }
        or first
        != {
            "trials": tids,
            "native_trial_ids_sha256": FAILED_IDS_SHA,
            "reserved": 23,
            "prior_debt": 3660,
            "debt": 3683,
        }
    ):
        raise ValueError("failed-epoch plan/claim/reservation/terminal binding mismatch")
    times = [
        datetime.fromisoformat(x)
        for x in (claim["claimed_at"], child["started_at"], terminal["finished_at"])
    ]
    if any(t.utcoffset() is None for t in times) or not times[0] <= times[1] <= times[2]:
        raise ValueError("failed epoch requires aware ordered actual lifecycle times")
    db = sqlite3.connect((root / "registry.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            "SELECT t.trial_id,t.hyperparams,t.result_json,e.code_version,e.search_space "
            "FROM trials t JOIN experiments e USING(experiment_id)"
        ).fetchall()
        if len(rows) != 23 or db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0]:
            raise ValueError("failed native epoch must retain exactly23 reservations and zero fits")
        expected = {p["key"]: p for p in spec["plans"]}
        seen = set()
        for tid, hp, result, code, space in rows:
            params = json.loads(hp)
            key = params["key"]
            if (
                key in seen
                or key not in expected
                or tids[key] != tid
                or result is not None
                or code != FAILED_CODE_SHA
                or sha256_json(json.loads(space)) != sha256_json(spec)
                or params
                != expected[key]
                | {
                    "response_history_version": "11.21-response-history-1",
                    "response_manifest_sha256": spec["manifest_sha256"],
                    "response_calendar_sha256": sha256_json(spec["calendar"]),
                }
            ):
                raise ValueError("failed native identities/code/source contracts changed")
            seen.add(key)
        if seen != set(tids):
            raise ValueError("failed native reservation set differs")
    finally:
        db.close()
    _verify(root, "registry.sqlite3", files["registry.sqlite3"])
    return {
        "failed_plan_sha256": FAILED_PLAN_SHA,
        "failed_claim_sha256": CLAIM_SHA,
        "terminal_sha256": TERMINAL_SHA,
        "files": files,
        "native_trial_ids_sha256": FAILED_IDS_SHA,
        "consumed_attempts": 23,
        "completed_results": 0,
        "actual_fits": 0,
        "prior_debt": 3660,
        "inherited_debt": 3683,
        "failure": "source key join, before model fitting; no automatic replay",
    }
