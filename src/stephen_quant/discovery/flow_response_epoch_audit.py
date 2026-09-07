"""Offline full numerical-pipeline audit; never Alpha Court or launch permission.

Reads immutable native results and actual saved reports. It does not execute a
new account, change targets, fit production models or modify RESULT/Trial state.
"""

from __future__ import annotations

import json
from pathlib import Path

from stephen_quant.baseline.stateful import (
    PositionMark,
    StatefulExecutionConfig,
    StatefulExecutionReport,
    StatefulMetrics,
    StatefulOrder,
    StatefulPeriod,
    TargetAllocation,
)
from stephen_quant.qmt.reliable_panel import file_sha

from .flow_response_history import read_verified_history
from .flow_response_model_audit import audit_models_targets
from .flow_response_protocol import contract, plans
from .flow_response_replay import audit_response_account
from .flow_response_source_audit import audit_source_history, compare
from .flow_response_views import HistoricalSessions
from .search_power_dsl import sha256_json


def read_bound_file(root, relative, expected):
    path = root / relative
    if root not in path.resolve(strict=True).parents or file_sha(path) != expected:
        raise ValueError("offline audit artifact path/bytes mismatch")
    return json.loads(path.read_bytes())


def _report(obj):
    return StatefulExecutionReport(
        obj["method_version"],
        StatefulExecutionConfig(**obj["config"]),
        StatefulMetrics(**obj["metrics"]),
        tuple(
            StatefulPeriod(
                **{
                    **p,
                    "orders": tuple(StatefulOrder(**o) for o in p["orders"]),
                    "marks": tuple(PositionMark(**m) for m in p["marks"]),
                }
            )
            for p in obj["periods"]
        ),
    )


def audit_complete_epoch(registry, *, operation, input_folder, original_tree):
    root = Path(operation).resolve(strict=True)
    if Path(registry.db_path).resolve() != root / "registry.sqlite3":
        raise ValueError("offline audit native registry mismatch")
    result_path = root / "RESULT.json"
    result_hash = file_sha(result_path)
    result = json.loads(result_path.read_bytes())
    spec = json.loads((root / "frozen_spec.json").read_bytes())
    tids = result["trial_ids"]
    if (
        sha256_json(spec) != result["spec_sha256"]
        or sha256_json(spec["contract"]) != sha256_json(contract())
        or spec["plans"] != plans()
        or set(tids) != {p["key"] for p in plans()}
        or len(set(tids.values())) != 23
        or registry.global_trial_count() != 23
        or result["reserved_trials"] != 23
        or result["raw_global_trial_lower_bound"] != 3683
        or set(result["records"]) != set(tids) - {"response-provider"}
    ):
        raise ValueError("offline audit complete frozen protocol mismatch")
    with registry.connect() as conn:
        for key, tid in tids.items():
            item = conn.execute(
                "SELECT t.result_json,e.search_space FROM trials t JOIN experiments e "
                "ON t.experiment_id=e.experiment_id WHERE t.trial_id=?",
                (tid,),
            ).fetchone()
            if (
                item is None
                or item[0] is None
                or sha256_json(json.loads(item[1])) != sha256_json(spec)
            ):
                raise ValueError("offline audit incomplete native operation")
            if key != "response-provider" and sha256_json(json.loads(item[0])) != sha256_json(
                result["records"][key]
            ):
                raise ValueError("offline audit account differs from native outcome")
    history_path = root / "history/history.json"
    source_audit = audit_source_history(
        registry, tids["response-82"], history_path=history_path, input_folder=input_folder
    )
    model_audit = audit_models_targets(registry, tids, history_path=history_path, operation=root)
    history, proof = read_verified_history(registry, tids["response-82"], history_path)
    if result["history_sha256"] != proof["history_artifact_sha256"]:
        raise ValueError("offline audit result history identity mismatch")
    original = Path(original_tree).resolve(strict=True)
    card = read_bound_file(
        original, "configs/v11.11-frozen-stability-observation.json", spec["anchor_card_sha256"]
    )
    for policy, old in (("original_lowvol", "lowvol"), ("original_stable", "stable_lowrisk")):
        original_values = read_bound_file(
            original,
            f"artifacts/temporal-increments/epoch-001/targets/{old}.json",
            card["targets_file_sha256"][old],
        )
        if (
            sha256_json(original_values) != card["targets_canonical_sha256"][old]
            or result["targets_sha256"][policy] != card["targets_file_sha256"][old]
        ):
            raise ValueError("offline audit original anchor identity mismatch")
    days = [d for d in history["calendar"] if d >= "2023-01-01"]
    sessions = HistoricalSessions(history["bars"], days)
    accounts, report_hashes = {}, {}
    for p in plans()[1:]:
        key, policy = p["key"], p["response_policy"]
        record = result["records"][key]
        if (
            record["key"] != key
            or record["trial_id"] != tids[key]
            or record["roundtrip_bps"] != p["roundtrip_bps"]
        ):
            raise ValueError("offline audit native account identity mismatch")
        raw_targets = read_bound_file(root, f"targets/{policy}.json", record["target_sha256"])
        if record["target_sha256"] != result["targets_sha256"][policy]:
            raise ValueError("offline audit target identity mismatch")
        targets = tuple(
            TargetAllocation(**{**t, "forced_exits": tuple(t["forced_exits"])}) for t in raw_targets
        )
        raw_report = read_bound_file(
            root, f"account_reports/{key}.json", record["full_account_sha256"]
        )
        saved = root / f"accounts/{key}.jsonl"
        if (
            root not in saved.resolve(strict=True).parents
            or file_sha(saved) != record["account_sha256"]
        ):
            raise ValueError("offline audit compact account evidence changed")
        report = _report(raw_report)
        with saved.open(encoding="utf-8") as stream:
            compact = [json.loads(line) for line in stream]
        expected_compact = [
            {
                "date": r["trade_date"],
                "nav": r["end_nav"],
                "return": r["net_return"],
                "cash": r["cash"],
                "cost": r["total_cost"],
                "stale_positions": r["stale_position_days"],
                "writeoff_loss": r["writeoff_loss"],
                "positions": r["marks"],
                "orders": r["orders"],
            }
            for r in raw_report["periods"]
        ]
        compare(compact, expected_compact, label=f"compact-full-report:{key}")
        compare(raw_report["metrics"], record["metrics"], label=f"native-metrics:{key}")
        accounts[key] = audit_response_account(
            report, sessions, targets, roundtrip_bps=p["roundtrip_bps"], mode=p["execution_mode"]
        )
        compare(accounts[key]["years"], record["years"], label=f"independent-years:{key}")
        compare(
            accounts[key]["pooled_sharpe"],
            record["pooled_sharpe"],
            label=f"independent-sharpe:{key}",
        )
        report_hashes[key] = record["full_account_sha256"]
    if file_sha(result_path) != result_hash:
        raise ValueError("offline audit result changed during verification")
    return {
        "pipeline_audit_pass": True,
        "validated_alpha": False,
        "result_sha256": result_hash,
        "native_registry_sha256": file_sha(registry.db_path),
        "source_audit": source_audit,
        "model_target_audit": model_audit,
        "accounts": accounts,
        "full_account_report_sha256": report_hashes,
        "statistics": spec["contract"]["statistics"],
        "interpretation": "independent reproduction of disclosed model;not first-seen/broker/Court certification",
    }
