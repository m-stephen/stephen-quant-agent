"""Read-only integration over frozen saved artifacts; not a launch authorization.

The future once-only supervised launcher must freeze code/runtime and validate its
plan before calling this component. It never fits, predicts or executes accounts.
"""

from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_chain import reconcile_chain
from .account_forensics_evidence import GROUPS, verify_unchanged
from .account_forensics_inputs import event_source_keys, execution_calendar, read_daily_lookups
from .account_forensics_metrics import account_summary, primary_difference
from .account_forensics_persistence import saved_membership
from .account_forensics_source import explain_event_sources
from .account_forensics_structure import prior_day_exposures, support_persistence
from .flow_response_launch import now, write
from .flow_response_storage import load_json


def _accounts(evidence):
    expected = {f"{group}/{policy}-{cost}" for group, policies in GROUPS.items()
                for policy in policies for cost in (82, 164)}
    accounts = {}
    for group in GROUPS:
        binding = evidence["bindings"][group]
        keys = {f"{group}/{p}-{c}" for p in GROUPS[group] for c in (82, 164)}
        if set(binding["accounts"]) != keys:
            raise ValueError("all fixed accounts required; no selection of successful subset")
        selected_files = {"RESULT.json"}
        for policy in GROUPS[group]:
            selected_files.add(f"targets/{policy}.json")
            for cost in (82, 164):
                selected_files.add(f"account_reports/{policy}-{cost}.json")
                selected_files.add(f"accounts/{policy}-{cost}.jsonl")
        if set(binding["files"]) != selected_files:
            raise ValueError("exact11 selected file bindings including RESULT.json required")
        for name, row in binding["accounts"].items():
            key = name.split("/", 1)[1]
            policy = key.rsplit("-", 1)[0]
            if row != {"key": key, "report": f"account_reports/{key}.json",
                       "ledger": f"accounts/{key}.jsonl", "target": f"targets/{policy}.json"}:
                raise ValueError("fixed account relative-path identities required")
            if not {row["report"], row["ledger"], row["target"]} <= binding["files"].keys():
                raise ValueError("full report, compact ledger and target byte bindings required")
            accounts[name] = (binding, row)
    if set(accounts) != expected or evidence["account_count"] != 12:
        raise ValueError("exactly12 predeclared saved accounts required")
    if (evidence["raw_global_trial_lower_bound"] != 3737
            or any(evidence[k] != 0 for k in ("new_accounts", "new_fits", "new_predictions"))
            or evidence["validated_alpha"] is not False):
        raise ValueError("read-only debt and noncertification contract required")
    return accounts


def build_saved_report(evidence, *, calendar_binding, output):
    """One history decode, fixed12 accounts, exclusive partial/final artifacts.

    This component's terminal describes report construction only. A separate
    independent arithmetic verifier, renderer and supervised launcher are still
    required before declaring the complete V12.3 operation accepted.
    """
    accounts = _accounts(evidence)
    output = Path(output).resolve()
    for binding in evidence["bindings"].values():
        source = Path(binding["root"]).resolve()
        if output == source or source in output.parents or output in source.parents:
            raise ValueError("report output and every input tree must be disjoint")
    output.mkdir(parents=True, exist_ok=False)
    write(output / "START.json", {"started_at": now(), "scope": "saved_report_component",
                                   "new_accounts": 0, "new_predictions": 0})
    stage, finished = "input_verification", []
    try:
        before = verify_unchanged(evidence)
        write(output / "INPUT_BINDINGS.json", evidence)
        write(output / "BEFORE.json", before)
        history_binding = evidence["bindings"]["history"]
        if set(history_binding["files"]) != {"history/history.json"}:
            raise ValueError("exact single frozen history binding required")
        stage = "single_history_decode"
        history = load_json(Path(history_binding["root"]) / "history/history.json")
        calendar = list(history["calendar"])
        execution = execution_calendar(calendar, frozen=calendar_binding)
        if set(history["bars"]) != set(calendar) or set(history["ranks"]) != set(calendar):
            raise ValueError("history dates must exactly cover the complete source calendar")
        chains, summaries, outputs = {}, {}, {}
        for directory in ("chains", "exposures", "details", "membership"):
            (output / directory).mkdir()
        for name in sorted(accounts):
            stage = "saved_account:" + name
            binding, item = accounts[name]
            report = load_json(Path(binding["root"]) / item["report"])
            chains[name] = reconcile_chain(name, report, calendar=execution, saved_bars=history["bars"])
            summaries[name] = account_summary(report, calendar=execution)
            exposures = prior_day_exposures(report, source_calendar=calendar, ranks=history["ranks"])
            portable = name.replace("/", "--") + ".json"
            for directory, value in (("chains", chains[name]), ("exposures", exposures)):
                path = output / directory / portable
                write(path, value)
                outputs[f"{directory}/{portable}"] = file_sha(path)
            finished.append(name)
            del report, exposures
        stage = "maintenance_support"
        binding = evidence["bindings"]["construction"]
        result = load_json(Path(binding["root"]) / "RESULT.json")
        persistence = {}
        for policy in GROUPS["construction"]:
            targets = load_json(Path(binding["root"]) / f"targets/{policy}.json")
            if [t["trade_date"] for t in targets] != execution:
                raise ValueError("exact complete target calendar required")
            membership = saved_membership(targets, result["diagnostics"][policy])
            support = support_persistence(membership, source_calendar=calendar, ranks=history["ranks"])
            path = output / "membership" / f"{policy}.json"
            write(path, {"membership": membership, "support": support})
            outputs[f"membership/{policy}.json"] = file_sha(path)
            persistence[policy] = {"maintenance_count": support["maintenance_count"],
                                   "scores_status": membership["score_status"]}
            del targets, membership, support
        del result
        stage = "explicit_frozen_source_keys"
        keys = event_source_keys(chains.values())
        lookups, source_receipt = read_daily_lookups(evidence["bindings"]["sources"], keys)
        source_status = {}
        for name, chain in chains.items():
            detail = explain_event_sources(chain, source_lookups=lookups, saved_bars=history["bars"])
            path = output / "details" / (name.replace("/", "--") + ".json")
            write(path, detail)
            outputs["details/" + path.name] = file_sha(path)
            source_status[name] = detail["source_explanation_status"]
            del detail
        del history, lookups, chains
        stage = "primary_paired_comparison"
        primary = {}
        for cost in (82, 164):
            root = Path(evidence["bindings"]["construction"]["root"])
            response = load_json(root / f"account_reports/global_response-{cost}.json")
            risk = load_json(root / f"account_reports/global_risk-{cost}.json")
            primary[str(cost)] = primary_difference(response, risk, calendar=execution)
            del response, risk
        stage = "after_input_verification"
        after = verify_unchanged(evidence)
        if before != after:
            raise ValueError("frozen input identity changed during reporting")
        write(output / "AFTER.json", after)
        summary = {
            "account_count": len(summaries), "execution_calendar": execution,
            "accounts": summaries, "primary": primary, "source_status": source_status,
            "source_query": source_receipt, "membership": persistence,
            "output_files": outputs, "input_evidence_sha256": before["evidence_sha256"],
            "component_status": "SAVED_REPORT_BUILT_NOT_INDEPENDENTLY_VERIFIED",
            "source_truth_verified": False, "new_accounts": 0, "new_fits": 0,
            "new_predictions": 0, "raw_global_trial_lower_bound": 3737,
            "statistics_status": "NOT_IDENTIFIABLE", "dsr": None, "pbo": None,
            "placebo_pvalue": None, "validated_alpha": False,
        }
        write(output / "SUMMARY.json", summary)
    except BaseException as exc:
        write(output / "TERMINAL.json", {"outcome": "FAILED", "stage": stage,
              "finished_at": now(), "error_type": type(exc).__name__,
              "completed_account_keys": finished, "automatic_retry": False,
              "validated_alpha": False})
        raise
    write(output / "TERMINAL.json", {
        "outcome": "SAVED_REPORT_BUILT_NOT_INDEPENDENTLY_VERIFIED", "finished_at": now(),
        "summary_sha256": file_sha(output / "SUMMARY.json"),
        "completed_account_keys": finished, "automatic_retry": False, "validated_alpha": False})
    return summary
