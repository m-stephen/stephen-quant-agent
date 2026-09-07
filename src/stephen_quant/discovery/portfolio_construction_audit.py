"""Independent source -> global construction -> saved account reconciliation.

No production selector, sleeve combiner, predictor fit, or execution engine is
called. This numerical audit does not itself verify launch authority, and never
promotes these reused-history construction controls to validated Alpha.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_epoch_audit import audit_saved_accounts, read_bound_file
from .flow_response_launch import ReadOnlyRegistry, _bound, read
from .flow_response_source_audit import audit_source_history
from .portfolio_construction import BUDGET, POLICIES, PRIOR_DEBT, VERSION, contract
from .portfolio_construction_runtime import account_plans, check_native, open_history
from .search_power_dsl import sha256_json


def independent_targets(history, policy):
    """Separate date-major reference; never dispatch to the production selector."""
    if policy not in ("global_lowvol", "global_hash"):
        raise ValueError("unregistered diagnostic reference")
    calendar = list(history["calendar"])
    if (
        not calendar
        or calendar != sorted(set(calendar))
        or any(not "2022-01-01" <= d <= "2024-12-31" for d in calendar)
    ):
        raise ValueError("independent calendar contract mismatch")
    days = [d for d in calendar if d >= "2023-01-01"]
    if not days:
        raise ValueError("independent execution calendar missing")
    states = [() for _ in range(4)]
    targets, diagnostics = [], []
    for index, dt in enumerate(days):
        signal = days[index - 1] if index else None
        refreshed = False
        for sleeve, phase in enumerate((0, 5, 10, 15)):
            if index < phase + 1 or (index - phase - 1) % 20:
                continue
            refreshed = True
            rows = history["ranks"][signal]
            if policy == "global_lowvol":
                ranked = sorted(rows, key=lambda n: (rows[n]["vol"], n))
            else:
                ranked = sorted(
                    rows,
                    key=lambda n: (
                        -int.from_bytes(
                            hashlib.sha256(("v11.21:184:" + n).encode()).digest(), "big"
                        ),
                        n,
                    ),
                )
            prior = set(states[sleeve])
            retained = [n for n in ranked[:60] if n in prior][:40]
            selected = set(retained)
            for name in ranked:
                if len(selected) >= 40:
                    break
                selected.add(name)
            chosen = tuple(sorted(selected))
            diagnostics.append(
                {
                    "date": signal,
                    "execution_date": dt,
                    "phase": phase,
                    "eligible": len(rows),
                    "selected": len(chosen),
                    "new_members": len(selected - prior),
                    "selected_names_sha256": sha256_json(chosen),
                    "selected_mean_vol": sum(rows[n]["vol"] for n in chosen) / len(chosen)
                    if chosen
                    else None,
                    "selected_cell_counts": [
                        sum(rows[n]["cell"] == c for n in chosen) for c in range(20)
                    ],
                }
            )
            states[sleeve] = chosen
        weights = {}
        if refreshed:
            for cohort in states:
                for name in cohort:
                    weights[name] = weights.get(name, 0.0) + 0.00625
        targets.append(
            {
                "trade_date": dt,
                "decided_at": f"{signal}T23:59:59+08:00" if signal else f"{dt}T08:00:00+08:00",
                "weights": weights,
                "rebalance": refreshed,
                "forced_exits": [],
            }
        )
    # Production is phase-major, but chronological account targets are not reset.
    diagnostics.sort(key=lambda d: (d["phase"], d["execution_date"]))
    return targets, diagnostics


def audit_targets(root, result, history):
    fingerprints = {}
    for policy in POLICIES:
        expected, diagnostics = independent_targets(history, policy)
        digest = result["targets_sha256"][policy]
        actual = read_bound_file(root, f"targets/{policy}.json", digest)
        if sha256_json(actual) != sha256_json(expected) or (
            sha256_json(result["diagnostics"][policy]) != sha256_json(diagnostics)
        ):
            raise ValueError("independent global selection/calendar/membership/style mismatch")
        fingerprints[policy] = digest
    return fingerprints


def audit_complete_accounts(*, operation, input_folder):
    root = Path(operation).resolve(strict=True)
    before = {
        name: _bound(root, name) for name in ("RESULT.json", "frozen_spec.json", "registry.sqlite3")
    }
    result, spec = read(root / "RESULT.json"), read(root / "frozen_spec.json")
    registry = ReadOnlyRegistry(root / "registry.sqlite3")
    tids = result["trial_ids"]
    check_native(registry, root, spec, tids, result)
    old, history_path, cache, history, proof = open_history(spec, root)
    source_audit = audit_source_history(
        old,
        spec["history"]["consumer"],
        history_path=history_path,
        input_folder=input_folder,
        cache=cache,
    )
    targets = audit_targets(root, result, history)
    accounts, reports = audit_saved_accounts(root, result, tids, history, account_plans())
    for key, evidence in accounts.items():
        if sha256_json(evidence) != sha256_json(result["records"][key]["audit"]):
            raise ValueError(
                "saved construction account audit differs from independent reproduction"
            )
    cache.get(old, spec["history"]["consumer"], history_path)
    _bound(Path(spec["history"]["root"]), "registry.sqlite3", spec["history"]["registry_sha256"])
    if any(file_sha(root / name) != digest for name, digest in before.items()):
        raise ValueError("diagnostic control bytes changed during audit")
    return {
        "version": VERSION,
        "pipeline_audit_pass": True,
        "validated_alpha": False,
        "launch_authorization_verified": False,
        "new_native_accounts_checked": BUDGET,
        "raw_global_trial_lower_bound": PRIOR_DEBT + BUDGET,
        "new_fits": 0,
        "result_sha256": before["RESULT.json"],
        "native_registry_sha256": before["registry.sqlite3"],
        "spec_file_sha256": before["frozen_spec.json"],
        "spec_sha256": sha256_json(spec),
        "history_sha256": proof["history_artifact_sha256"],
        "completed_parent_evidence_sha256": spec["completed_parent_evidence_sha256"],
        "source_audit": source_audit,
        "independent_target_sha256": targets,
        "accounts": accounts,
        "full_account_report_sha256": reports,
        "statistics": contract()["statistics"],
        "interpretation": "construction diagnostic only; risk/retention jointly change; no new Alpha/Court/fresh OOS claim",
    }
