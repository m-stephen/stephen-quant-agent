"""External artifact-integrity acceptance, not another numerical run or launch.

Caller supplies independently frozen inputs, calendar and producer/reference code.
This layer never decodes history, executes an account, or certifies source truth.
"""

import json
import math
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_evidence import GROUPS, bind_files, verify_unchanged
from .account_forensics_inputs import execution_calendar
from .search_power_dsl import sha256_json

STATUS = "SAVED_REPORT_INDEPENDENTLY_VERIFIED_NOT_LAUNCH_ACCEPTED"
SOURCE_STATES = {"UNKNOWN", "IMPLEMENTATION_MISMATCH", "EXPLAINED_BY_FROZEN_SOURCE",
                 "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS"}
SCORES_UNAVAILABLE = "UNAVAILABLE_ONLY_SCORE_HASH_SAVED_NO_PREDICTION_RECOMPUTATION"


def exact(actual, expected):
    """Unlike numeric comparisons, bool/int/float are never interchangeable here."""
    if type(actual) is not type(expected):
        raise ValueError("artifact contract type mismatch")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError("artifact contract field mismatch")
        for key in expected:
            exact(actual[key], expected[key])
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError("artifact contract coverage mismatch")
        for a, b in zip(actual, expected, strict=True):
            exact(a, b)
    elif actual != expected:
        raise ValueError("artifact contract value mismatch")


def digest(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("canonical digest required")
    return value


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative integer required")
    return value


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("nonfinite JSON value: " + value)

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            invalid(value)
        return parsed

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=invalid, parse_float=finite_float)


def check_fields(value, expected):
    for key, item in expected.items():
        exact(value[key], item)


def expected_outputs():
    names = sorted(f"{g}/{p}-{c}" for g, policies in GROUPS.items()
                   for p in policies for c in (82, 164))
    files = {f"{d}/{n.replace('/', '--')}.json" for n in names
             for d in ("chains", "exposures", "details", "verification")}
    files.update(f"membership/{p}.json" for p in GROUPS["construction"])
    files.add("VERIFICATION.json")
    return names, files


def accept_saved_artifacts(output, *, evidence, source_calendar, calendar_binding,
                           producer_code, code_root):
    """Frozen-plan roots must come from launcher, never from the outputs themselves.

    For old artifacts, use their original runtime bindings. The acceptor's own
    code identity is recorded separately; no claim that old runs tested new code.
    File checks are explicit allowlists, not directory scans or dataset queries.
    """
    root = Path(output).resolve()
    names, files = expected_outputs()
    for binding in evidence["bindings"].values():
        source = Path(binding["root"]).resolve()
        if root == source or source in root.parents or root in source.parents:
            raise ValueError("output must be disjoint from original inputs")
    before = verify_unchanged(evidence)
    bind_files(code_root, producer_code)
    dates = execution_calendar(source_calendar, frozen=calendar_binding)
    check_fields(evidence, {"account_count": 12, "raw_global_trial_lower_bound": 3737,
                           "new_accounts": 0, "new_fits": 0, "new_predictions": 0,
                           "validated_alpha": False})
    for key, value in (("source_sessions", 726), ("execution_sessions", 484)):
        if key in evidence:
            exact(evidence[key], value)
    for group, policies in GROUPS.items():
        binding = evidence["bindings"][group]
        exact(set(binding["accounts"]), {f"{group}/{p}-{c}" for p in policies for c in (82, 164)})
        required = {"RESULT.json"} | {f"targets/{p}.json" for p in policies}
        required |= {f"{d}/{p}-{c}.{ext}" for p in policies for c in (82, 164)
                     for d, ext in (("accounts", "jsonl"), ("account_reports", "json"))}
        exact(set(binding["files"]), required)
    # These fixed paths must not be replaced with symlink escapes either.
    controls = {"START.json", "INPUT_BINDINGS.json", "BEFORE.json", "AFTER.json",
                "SUMMARY.json", "TERMINAL.json"}
    for rel in files | controls:
        if not (root / rel).resolve().is_relative_to(root):
            raise ValueError("resolved artifact path escapes report root")
    initial = {rel: file_sha(root / rel) for rel in files | controls}
    summary, verification = read(root / "SUMMARY.json"), read(root / "VERIFICATION.json")
    exact(set(summary["output_files"]), files)
    bind_files(root, summary["output_files"])
    exact(read(root / "INPUT_BINDINGS.json"), evidence)
    for rel in ("BEFORE.json", "AFTER.json"):
        exact(read(root / rel), before)
    check_fields(read(root / "START.json"), {"scope": "saved_report_component",
                                            "new_accounts": 0, "new_predictions": 0})
    check_fields(read(root / "TERMINAL.json"), {
        "outcome": STATUS, "summary_sha256": initial["SUMMARY.json"],
        "completed_account_keys": names, "automatic_retry": False, "validated_alpha": False})
    check_fields(summary, {
        "account_count": 12, "execution_calendar": dates, "component_status": STATUS,
        "input_evidence_sha256": before["evidence_sha256"], "source_truth_verified": False,
        "raw_global_trial_lower_bound": 3737, "new_accounts": 0, "new_fits": 0,
        "new_predictions": 0, "statistics_status": "NOT_IDENTIFIABLE",
        "dsr": None, "pbo": None, "placebo_pvalue": None, "validated_alpha": False})
    check_fields(verification, {"account_keys": names, "account_count": 12,
        "code": producer_code, "input_evidence_sha256": before["evidence_sha256"],
        "status": STATUS, "validated_alpha": False})
    for key in ("history_memory_sha256", "source_lookup_memory_sha256"):
        digest(verification[key])
    for key in ("accounts", "source_status"):
        exact(set(summary[key]), set(names))
    for name in names:
        _account(root, name, summary, evidence, producer_code, dates)
    _global(root, summary, verification, dates)
    exact(verify_unchanged(evidence), before)
    bind_files(code_root, producer_code)
    exact({rel: file_sha(root / rel) for rel in initial}, initial)
    return {"status": "ARTIFACT_INTEGRITY_ACCEPTED_NOT_LAUNCH_ACCEPTED",
            "account_count": 12, "output_count": 51, "input_evidence_sha256": before["evidence_sha256"],
            "producer_code_sha256": sha256_json(producer_code),
            "acceptor_file_sha256": file_sha(Path(__file__)),
            "verified_artifact_files": initial, "numerical_reexecution": False,
            "source_truth_verified": False, "validated_alpha": False}


def _account(root, name, summary, evidence, code, dates):
    group, key = name.split("/")
    policy = key.rsplit("-", 1)[0]
    binding = evidence["bindings"][group]
    item = {"key": key, "report": f"account_reports/{key}.json",
            "ledger": f"accounts/{key}.jsonl", "target": f"targets/{policy}.json"}
    exact(binding["accounts"][name], item)
    portable = name.replace("/", "--") + ".json"
    receipt = read(root / "verification" / portable)
    check_fields(receipt, {"account": name, "status": "ACCOUNT_CHECKS_PASSED_PENDING_GLOBAL_ACCEPTANCE",
        "input_evidence_sha256": summary["input_evidence_sha256"],
        "code_sha256": sha256_json(code), "summary_sha256": sha256_json(summary["accounts"][name]),
        "input_files": {rel: binding["files"][rel] for rel in
                        (item["report"], item["ledger"], item["target"], "RESULT.json")},
        "shared_inputs": {k: evidence["bindings"][k] for k in ("history", "sources")},
        "output_files": {f"{d}/{portable}": summary["output_files"][f"{d}/{portable}"]
                         for d in ("chains", "exposures", "details")}, "validated_alpha": False})
    checks = receipt["checks"]
    exact(set(checks), {"compact_sessions", "events", "metrics", "exposure", "source",
                        "original_report_memory_sha256"})
    exact(checks["compact_sessions"], 484)
    digest(checks["original_report_memory_sha256"])
    exact(checks["metrics"], {"arithmetic_verified": True, "sessions": 484, "validated_alpha": False})
    exact(checks["exposure"], {"exposure_arithmetic_verified": True, "sessions": 484})
    events = checks["events"]
    totals = {k: integer(events[k]) for k in ("writeoff_events", "recovery_events", "open_stale_chains")}
    exact(events, {**totals, "saved_event_identities_verified": True, "sessions": 484,
                   "source_truth_verified": False, "validated_alpha": False})
    state = summary["source_status"][name]
    if state not in SOURCE_STATES:
        raise ValueError("unrecognized source state")
    exact(checks["source"], {"independent_source_explanations_verified": True,
        "source_explanation_status": state, "events": totals["writeoff_events"] + totals["recovery_events"],
        "open_stale_chains": totals["open_stale_chains"],
        "actual_suspension_or_delisting_verified": False, "validated_alpha": False})
    identities_by_file, tails_by_file = {}, {}
    for directory in ("chains", "details"):
        saved = read(root / directory / portable)
        check_fields(saved, {"account": name, "sessions_checked": 484,
            "ledger_chain_pass": True, "saved_account_reconciled": True, "new_accounts": 0,
            "counterfactual_nav_generated": False, "source_truth_verified": False})
        identities = [(e["account"], e["date"], e["instrument"], e["event_type"]) for e in saved["events"]]
        if (len(set(identities)) != len(identities)
                or any(n != name or dt not in dates or k not in ("writeoff", "recovery")
                       for n, dt, _, k in identities)):
            raise ValueError("actual event identity coverage mismatch")
        for kind in ("writeoff", "recovery"):
            exact(sum(k == kind for _, _, _, k in identities), totals[kind + "_events"])
        identities_by_file[directory] = set(identities)
        exact(len(saved["open_stale_chains"]), totals["open_stale_chains"])
        tails = [(t["account"], t["instrument"], t["through_date"]) for t in saved["open_stale_chains"]]
        if len(set(tails)) != len(tails) or any(n != name or d != dates[-1] for n, _, d in tails):
            raise ValueError("actual tail identity coverage mismatch")
        tails_by_file[directory] = set(tails)
        if directory == "details":
            exact(saved["source_explanation_status"], state)
            states = {e["source_explanation_status"] for e in saved["events"] + saved["open_stale_chains"]}
            if not states <= {"UNKNOWN", "IMPLEMENTATION_MISMATCH", "EXPLAINED_BY_FROZEN_SOURCE"}:
                raise ValueError("invalid actual source sub-event state")
            aggregate = ("IMPLEMENTATION_MISMATCH" if "IMPLEMENTATION_MISMATCH" in states else
                         "UNKNOWN" if "UNKNOWN" in states else "EXPLAINED_BY_FROZEN_SOURCE" if states else
                         "NO_WRITEOFF_RECOVERY_EVENTS_OR_OPEN_STALE_CHAINS")
            exact(state, aggregate)
    exact(identities_by_file["chains"], identities_by_file["details"])
    exact(tails_by_file["chains"], tails_by_file["details"])
    exposed = read(root / "exposures" / portable)
    check_fields(exposed, {"sessions": 484, "risk_neutrality_proven": False})
    exact([row["date"] for row in exposed["daily"]], dates)
    account = summary["accounts"][name]
    exact(account["validated_alpha"], False)
    exact(set(account["years"]), {"2023", "2024"})
    for window, selected in ((account["continuous"], dates), *(
            (account["years"][y], [d for d in dates if d.startswith(y)]) for y in ("2023", "2024"))):
        check_fields(window, {"start": selected[0], "end": selected[-1], "sessions": len(selected)})


def _global(root, summary, verification, dates):
    policies = set(GROUPS["construction"])
    exact(set(summary["membership"]), policies)
    exact(set(verification["membership"]), policies)
    schedule = [{"execution_date": dt, "signal_date": dates[i - 1], "phase": (i - 1) % 20}
                for i, dt in enumerate(dates) if i > 0 and (i - 1) % 20 in (0, 5, 10, 15)]
    exact(len(schedule), 97)
    for p in sorted(policies):
        check = verification["membership"][p]
        exact(check["membership"], {"independent_membership_verified": True, "maintenance_count": 97,
            "new_predictions": 0, "raw_scores_verified": False, "support_verified": False,
            "validated_alpha": False})
        exact(check["support"], {"independent_support_verified": True, "maintenance_count": 97,
                                "score_instability_verified": False, "validated_alpha": False})
        digest(check["original_target_memory_sha256"])
        exact(check["output_sha256"], summary["output_files"][f"membership/{p}.json"])
        exact(summary["membership"][p]["maintenance_count"], 97)
        saved = read(root / f"membership/{p}.json")
        exact(summary["membership"][p]["scores_status"], SCORES_UNAVAILABLE)
        exact(saved["membership"]["score_status"], SCORES_UNAVAILABLE)
        exact(saved["support"]["signal_instability_proven"], False)
        for kind in ("membership", "support"):
            check_fields(saved[kind], {"maintenance_count": 97, "new_predictions": 0,
                                      "name_churn_is_traded_turnover": False})
            exact(len(saved[kind]["maintenance_events"]), 97)
            exact([{key: event[key] for key in ("execution_date", "signal_date", "phase")}
                   for event in saved[kind]["maintenance_events"]], schedule)
    for obj in (summary, verification):
        exact(set(obj["primary"]), {"82", "164"})
    for cost in ("82", "164"):
        exact(verification["primary"][cost], {"primary_arithmetic_verified": True, "validated_alpha": False})
        p = summary["primary"][cost]
        check_fields(p, {"statistical_status": "DESCRIPTIVE_NOT_CERTIFIED", "dsr": None,
                         "pbo": None, "placebo_pvalue": None, "validated_alpha": False})
        exact(set(p["windows"]), {"continuous", "2023", "2024"})
        for key, window in p["windows"].items():
            exact(window["sessions"], len(dates) if key == "continuous" else
                  sum(d.startswith(key) for d in dates))
    q = {k: integer(summary["source_query"][k]) for k in ("requested_keys", "matched_rows", "absent_keys")}
    exact(q["requested_keys"], q["matched_rows"] + q["absent_keys"])
    if q["requested_keys"]:
        check_fields(summary["source_query"], {"input_bytes_unchanged": True,
            "query_projection": ["trade_date", "instrument", "name", "open", "close", "amount",
                                 "volume", "adjustment_factor", "available_at"]})
    exact(verification["source_query"], {**q, "independent_lookup_coverage_verified": True,
          "actual_suspension_or_delisting_verified": False, "validated_alpha": False})
