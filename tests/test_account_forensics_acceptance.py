"""Small artifact-contract fixtures only; no account execution or market reads."""

import json
from datetime import date, timedelta

import pytest

from stephen_quant.discovery.account_forensics_acceptance import (
    SCORES_UNAVAILABLE,
    STATUS,
    accept_saved_artifacts,
    exact,
    expected_outputs,
    read,
)
from stephen_quant.discovery.account_forensics_evidence import GROUPS
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def proof(tmp_path):
    root = tmp_path / "report"
    names, files = expected_outputs()
    code_root = tmp_path / "code"
    save(code_root / "frozen.py", "frozen code bytes fixture")
    code = {"frozen.py": file_sha(code_root / "frozen.py")}
    calendar = []
    for year, first in ((2022, date(2022, 1, 3)), (2023, date(2023, 1, 3)), (2024, date(2024, 1, 2))):
        days = [(first + timedelta(days=i)).isoformat() for i in range(241)]
        calendar += days + [f"{year}-12-31"]
    dates = calendar[242:]
    evidence = {"bindings": {}, "account_count": 12, "source_sessions": 726,
                "execution_sessions": 484, "raw_global_trial_lower_bound": 3737,
                "new_accounts": 0, "new_fits": 0, "new_predictions": 0, "validated_alpha": False}
    for label in ("history", "sources", *GROUPS):
        folder = tmp_path / "input" / label
        if label not in GROUPS:
            rels, accounts = ["fixture.json"], {}
        else:
            accounts, rels = {}, ["RESULT.json"]
            for p in GROUPS[label]:
                rels += [f"targets/{p}.json"]
                for c in (82, 164):
                    key = f"{p}-{c}"
                    accounts[f"{label}/{key}"] = {"key": key, "report": f"account_reports/{key}.json",
                        "ledger": f"accounts/{key}.jsonl", "target": f"targets/{p}.json"}
                    rels += [f"account_reports/{key}.json", f"accounts/{key}.jsonl"]
        for rel in rels:
            save(folder / rel, {"synthetic_metadata_only": True})
        evidence["bindings"][label] = {"root": str(folder), "files": {r: file_sha(folder / r) for r in rels}}
        if accounts:
            evidence["bindings"][label]["accounts"] = accounts
    identity = sha256_json(evidence)
    summary = {"account_count": 12, "execution_calendar": dates, "component_status": STATUS,
        "input_evidence_sha256": identity, "source_truth_verified": False,
        "raw_global_trial_lower_bound": 3737, "new_accounts": 0, "new_fits": 0,
        "new_predictions": 0, "statistics_status": "NOT_IDENTIFIABLE", "dsr": None,
        "pbo": None, "placebo_pvalue": None, "validated_alpha": False,
        "accounts": {}, "source_status": {}, "membership": {}, "primary": {},
        "source_query": {"requested_keys": 0, "matched_rows": 0, "absent_keys": 0}}
    verification = {"account_keys": names, "account_count": 12, "code": code,
        "input_evidence_sha256": identity, "status": STATUS, "validated_alpha": False,
        "history_memory_sha256": "a" * 64, "source_lookup_memory_sha256": "b" * 64,
        "membership": {}, "primary": {}, "source_query": {**summary["source_query"],
            "independent_lookup_coverage_verified": True,
            "actual_suspension_or_delisting_verified": False, "validated_alpha": False}}
    def window(ds):
        return {"start": ds[0], "end": ds[-1], "sessions": len(ds)}
    for rel in files:
        save(root / rel, {})
    for name in names:
        group, key = name.split("/")
        binding = evidence["bindings"][group]
        item = binding["accounts"][name]
        portable = name.replace("/", "--") + ".json"
        for directory in ("chains", "details"):
            save(root / directory / portable, {"account": name, "sessions_checked": 484,
                "ledger_chain_pass": True, "saved_account_reconciled": True, "new_accounts": 0,
                "counterfactual_nav_generated": False, "source_truth_verified": False,
                "events": [{"account": name, "date": dates[30], "instrument": "S1",
                            "event_type": "writeoff", "source_explanation_status": "UNKNOWN"}],
                "open_stale_chains": [{"account": name, "instrument": "S2", "through_date": dates[-1],
                                       "source_explanation_status": "UNKNOWN"}],
                "source_explanation_status": "UNKNOWN"})
        save(root / "exposures" / portable, {"sessions": 484, "risk_neutrality_proven": False,
                                           "daily": [{"date": d} for d in dates]})
        summary["accounts"][name] = {"continuous": window(dates), "years": {
            y: window([d for d in dates if d.startswith(y)]) for y in ("2023", "2024")},
            "validated_alpha": False}
        summary["source_status"][name] = "UNKNOWN"
        checks = {"compact_sessions": 484, "original_report_memory_sha256": "c" * 64,
            "metrics": {"arithmetic_verified": True, "sessions": 484, "validated_alpha": False},
            "exposure": {"exposure_arithmetic_verified": True, "sessions": 484},
            "events": {"writeoff_events": 1, "recovery_events": 0, "open_stale_chains": 1,
                "saved_event_identities_verified": True, "sessions": 484,
                "source_truth_verified": False, "validated_alpha": False},
            "source": {"independent_source_explanations_verified": True,
                "source_explanation_status": "UNKNOWN", "events": 1, "open_stale_chains": 1,
                "actual_suspension_or_delisting_verified": False, "validated_alpha": False}}
        save(root / "verification" / portable, {"account": name, "checks": checks,
            "status": "ACCOUNT_CHECKS_PASSED_PENDING_GLOBAL_ACCEPTANCE",
            "input_evidence_sha256": identity, "code_sha256": sha256_json(code),
            "summary_sha256": sha256_json(summary["accounts"][name]),
            "input_files": {r: binding["files"][r] for r in (item["report"], item["ledger"], item["target"], "RESULT.json")},
            "shared_inputs": {k: evidence["bindings"][k] for k in ("history", "sources")},
            "output_files": {f"{d}/{portable}": file_sha(root / d / portable) for d in ("chains", "details", "exposures")},
            "validated_alpha": False})
    for p in GROUPS["construction"]:
        schedule = [{"execution_date": dt, "signal_date": dates[i - 1], "phase": (i - 1) % 20}
                    for i, dt in enumerate(dates) if i > 0 and (i - 1) % 20 in (0, 5, 10, 15)]
        save(root / f"membership/{p}.json", {k: {"score_status": SCORES_UNAVAILABLE, "maintenance_count": 97,
            "new_predictions": 0, "name_churn_is_traded_turnover": False,
            "maintenance_events": schedule, "signal_instability_proven": False} for k in ("membership", "support")})
        summary["membership"][p] = {"maintenance_count": 97, "scores_status": SCORES_UNAVAILABLE}
        verification["membership"][p] = {
            "membership": {"independent_membership_verified": True, "maintenance_count": 97,
                "new_predictions": 0, "raw_scores_verified": False, "support_verified": False, "validated_alpha": False},
            "support": {"independent_support_verified": True, "maintenance_count": 97,
                "score_instability_verified": False, "validated_alpha": False},
            "original_target_memory_sha256": "d" * 64,
            "output_sha256": file_sha(root / f"membership/{p}.json")}
    for c in ("82", "164"):
        summary["primary"][c] = {"statistical_status": "DESCRIPTIVE_NOT_CERTIFIED", "dsr": None,
            "pbo": None, "placebo_pvalue": None, "validated_alpha": False,
            "windows": {"continuous": {"sessions": 484}, "2023": {"sessions": 242}, "2024": {"sessions": 242}}}
        verification["primary"][c] = {"primary_arithmetic_verified": True, "validated_alpha": False}
    save(root / "VERIFICATION.json", verification)
    save(root / "START.json", {"scope": "saved_report_component", "new_accounts": 0, "new_predictions": 0})
    save(root / "INPUT_BINDINGS.json", evidence)
    for rel in ("BEFORE.json", "AFTER.json"):
        save(root / rel, {"input_bytes_unchanged": True, "evidence_sha256": identity})
    summary["output_files"] = {r: file_sha(root / r) for r in files}
    save(root / "SUMMARY.json", summary)
    save(root / "TERMINAL.json", {"outcome": STATUS, "summary_sha256": file_sha(root / "SUMMARY.json"),
        "completed_account_keys": names, "automatic_retry": False, "validated_alpha": False})
    return root, {"evidence": evidence, "source_calendar": calendar,
                  "calendar_binding": {"count": 726, "sha256": sha256_json(calendar)},
                  "producer_code": code, "code_root": code_root}


def rebind(root, rel, obj):
    save(root / rel, obj)
    summary = read(root / "SUMMARY.json") if rel != "SUMMARY.json" else obj
    if rel in summary["output_files"]:
        summary["output_files"][rel] = file_sha(root / rel)
    save(root / "SUMMARY.json", summary)
    terminal = read(root / "TERMINAL.json")
    terminal["summary_sha256"] = file_sha(root / "SUMMARY.json")
    save(root / "TERMINAL.json", terminal)


def test_complete_metadata_contract_only(proof):
    root, kwargs = proof
    result = accept_saved_artifacts(root, **kwargs)
    assert result["output_count"] == 51
    assert result["validated_alpha"] is False
    assert result["numerical_reexecution"] is False


@pytest.mark.parametrize("case", ["missing_account", "missing_cost", "missing_policy", "alpha", "stats",
    "float_count", "bool_count", "source_status", "receipt_summary", "receipt_code", "receipt_identity",
    "receipt_field", "terminal_failed", "input_bytes", "code_bytes", "output_bytes", "missing_output",
    "calendar", "before", "query", "receipt_float", "input_extra_identity"])
def test_tampering_even_with_local_manifest_rehash_refused(proof, case):
    root, kwargs = proof
    receipt = "verification/construction--global_response-82.json"
    rel = "SUMMARY.json"
    obj = read(root / rel)
    if case == "missing_account":
        obj["accounts"].pop("construction/global_response-82")
    elif case == "missing_cost":
        obj["primary"].pop("164")
    elif case == "missing_policy":
        obj["membership"].pop("global_risk")
    elif case == "alpha":
        obj["validated_alpha"] = True
    elif case == "stats":
        obj["dsr"] = 0.96
    elif case in ("float_count", "bool_count"):
        obj["new_accounts"] = 0.0 if case == "float_count" else False
    elif case == "source_status":
        obj["source_status"]["construction/global_response-82"] = "EXPLAINED_BY_FROZEN_SOURCE"
    elif case.startswith("receipt_"):
        rel, obj = receipt, read(root / receipt)
        if case == "receipt_summary":
            obj["summary_sha256"] = "a" * 64
        elif case == "receipt_code":
            obj["code_sha256"] = "a" * 64
        elif case == "receipt_identity":
            obj["account"] = "construction/global_risk-82"
        elif case == "receipt_field":
            obj["checks"].pop("events")
        else:
            obj["checks"]["events"]["sessions"] = 484.0
    elif case == "terminal_failed":
        rel, obj = "TERMINAL.json", read(root / "TERMINAL.json")
        obj["outcome"] = "FAILED"
    elif case in ("input_bytes", "code_bytes", "output_bytes"):
        from pathlib import Path
        path = (Path(kwargs["evidence"]["bindings"]["history"]["root"]) / "fixture.json"
                if case == "input_bytes" else kwargs["code_root"] / "frozen.py" if case == "code_bytes"
                else root / "chains/construction--global_response-82.json")
        save(path, {"changed": True})
    elif case == "missing_output":
        (root / receipt).unlink()
    elif case == "calendar":
        kwargs["source_calendar"][0] = "2022-01-02"
    elif case == "before":
        rel, obj = "BEFORE.json", {"input_bytes_unchanged": True, "evidence_sha256": "a" * 64}
    elif case == "query":
        obj["source_query"]["requested_keys"] = 1
    elif case == "input_extra_identity":
        kwargs["evidence"]["bindings"]["construction"]["accounts"]["construction/extra-82"] = {}
    if case not in ("input_bytes", "code_bytes", "output_bytes", "missing_output", "calendar", "input_extra_identity"):
        rebind(root, rel, obj)
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        accept_saved_artifacts(root, **kwargs)


@pytest.mark.parametrize("payload", ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": Infinity}', '{"x": 1e999}'])
def test_strict_json(tmp_path, payload):
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        read(path)


@pytest.mark.parametrize("value", [False, 0.0, "0"])
def test_strict_types(value):
    with pytest.raises(ValueError):
        exact(value, 0)


@pytest.mark.parametrize("case", ["duplicate_date", "wrong_phase", "wrong_signal", "empty_event",
    "score_claim", "support_claim", "event_identity", "tail_identity", "hidden_unknown"])
def test_cross_file_contract_refuses_fully_rehashed_local_links(proof, case):
    root, kwargs = proof
    policy = "global_response"
    name = "construction/global_response-82"
    portable = "construction--global_response-82.json"
    if case in ("event_identity", "tail_identity", "hidden_unknown"):
        rel = f"details/{portable}"
        obj = read(root / rel)
        if case == "event_identity":
            obj["events"][0]["instrument"] = "SWAPPED"
        elif case == "tail_identity":
            obj["open_stale_chains"][0]["instrument"] = "SWAPPED"
        else:
            obj["source_explanation_status"] = "EXPLAINED_BY_FROZEN_SOURCE"
        rebind(root, rel, obj)
        receipt_rel = f"verification/{portable}"
        receipt = read(root / receipt_rel)
        receipt["output_files"][rel] = file_sha(root / rel)
        if case == "hidden_unknown":
            receipt["checks"]["source"]["source_explanation_status"] = "EXPLAINED_BY_FROZEN_SOURCE"
            summary = read(root / "SUMMARY.json")
            summary["source_status"][name] = "EXPLAINED_BY_FROZEN_SOURCE"
            rebind(root, "SUMMARY.json", summary)
        rebind(root, receipt_rel, receipt)
    else:
        rel = f"membership/{policy}.json"
        obj = read(root / rel)
        events = obj["membership"]["maintenance_events"]
        if case == "duplicate_date":
            events[1] = events[0]
        elif case == "wrong_phase":
            events[1]["phase"] = 0
        elif case == "wrong_signal":
            events[1]["signal_date"] = events[1]["execution_date"]
        elif case == "empty_event":
            events[0] = {}
        elif case == "support_claim":
            obj["support"]["signal_instability_proven"] = True
        else:
            obj["membership"]["score_status"] = "AVAILABLE"
            summary = read(root / "SUMMARY.json")
            summary["membership"][policy]["scores_status"] = "AVAILABLE"
            rebind(root, "SUMMARY.json", summary)
        rebind(root, rel, obj)
        verification = read(root / "VERIFICATION.json")
        verification["membership"][policy]["output_sha256"] = file_sha(root / rel)
        rebind(root, "VERIFICATION.json", verification)
    with pytest.raises((KeyError, ValueError)):
        accept_saved_artifacts(root, **kwargs)


def test_old_optional_session_declarations_not_invented(proof):
    root, kwargs = proof
    evidence = kwargs["evidence"]
    evidence.pop("source_sessions")
    evidence.pop("execution_sessions")
    identity = sha256_json(evidence)
    save(root / "INPUT_BINDINGS.json", evidence)
    for rel in ("BEFORE.json", "AFTER.json"):
        save(root / rel, {"input_bytes_unchanged": True, "evidence_sha256": identity})
    names, _ = expected_outputs()
    for name in names:
        rel = "verification/" + name.replace("/", "--") + ".json"
        obj = read(root / rel)
        obj["input_evidence_sha256"] = identity
        rebind(root, rel, obj)
    for rel in ("VERIFICATION.json", "SUMMARY.json"):
        obj = read(root / rel)
        obj["input_evidence_sha256"] = identity
        rebind(root, rel, obj)
    assert accept_saved_artifacts(root, **kwargs)["account_count"] == 12
