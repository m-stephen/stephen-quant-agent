"""Read-only integration over frozen saved artifacts; not a launch authorization.

The future once-only supervised launcher must freeze code/runtime and validate its
plan before calling this component. It never fits, predicts or executes accounts.
"""

from pathlib import Path
from time import monotonic

from stephen_quant.qmt.reliable_panel import file_sha

from .account_forensics_chain import reconcile_chain
from .account_forensics_evidence import GROUPS, verify_unchanged
from .account_forensics_inputs import event_source_keys, execution_calendar, read_daily_lookups
from .account_forensics_memory import (
    assert_lookups_unchanged,
    assert_memory_unchanged,
    lookup_fingerprint,
    memory_fingerprint,
)
from .account_forensics_metrics import account_summary, primary_difference
from .account_forensics_persistence import saved_membership
from .account_forensics_source import explain_event_sources
from .account_forensics_structure import prior_day_exposures, support_persistence
from .account_forensics_verify import (
    verify_compact,
    verify_exposures,
    verify_metrics,
    verify_primary,
)
from .account_forensics_verify_events import derive_events, verify_derived_events
from .account_forensics_verify_keys import required_source_keys, verify_lookup_coverage
from .account_forensics_verify_members import verify_membership
from .account_forensics_verify_source import verify_source_details
from .account_forensics_verify_support import verify_support
from .flow_response_launch import now, write
from .flow_response_storage import load_json
from .search_power_dsl import sha256_json

STATUS = "SAVED_REPORT_INDEPENDENTLY_VERIFIED_NOT_LAUNCH_ACCEPTED"


def code_bindings():
    root = Path(__file__).resolve().parents[1]
    return {p.relative_to(root).as_posix(): file_sha(p) for p in sorted(root.rglob("*.py"))}


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
    if (set(accounts) != expected or type(evidence["account_count"]) is not int
            or evidence["account_count"] != 12):
        raise ValueError("exactly12 predeclared saved accounts required")
    if (type(evidence["raw_global_trial_lower_bound"]) is not int
            or evidence["raw_global_trial_lower_bound"] != 3737
            or any(type(evidence[k]) is not int or evidence[k] != 0
                   for k in ("new_accounts", "new_fits", "new_predictions"))
            or evidence["validated_alpha"] is not False):
        raise ValueError("read-only debt and noncertification contract required")
    return accounts


def build_saved_report(evidence, *, calendar_binding, output):
    """One history decode, fixed12 accounts, exclusive partial/final artifacts.

    Reference paths consume original files/history, not producer reference JSON.
    The renderer, external final checks and once-only supervised launcher are
    still required before declaring the complete V12.3 operation accepted.
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
    started = monotonic()

    def announce(value):
        print(f"FORENSICS_STAGE {value} elapsed={monotonic() - started:.3f}", flush=True)
        return value

    try:
        code = code_bindings()
        before = verify_unchanged(evidence)
        write(output / "INPUT_BINDINGS.json", evidence)
        write(output / "BEFORE.json", before)
        history_binding = evidence["bindings"]["history"]
        if set(history_binding["files"]) != {"history/history.json"}:
            raise ValueError("exact single frozen history binding required")
        stage = announce("single_history_decode")
        history = load_json(Path(history_binding["root"]) / "history/history.json")
        calendar = list(history["calendar"])
        execution = execution_calendar(calendar, frozen=calendar_binding)
        if set(history["bars"]) != set(calendar) or set(history["ranks"]) != set(calendar):
            raise ValueError("history dates must exactly cover the complete source calendar")
        stage = announce("original_history_memory_fingerprint")
        history_memory = memory_fingerprint(history)
        chains, references, summaries, outputs, checks = {}, {}, {}, {}, {}
        for directory in ("chains", "exposures", "details", "membership", "verification"):
            (output / directory).mkdir()
        for name in sorted(accounts):
            stage = announce("saved_account:" + name)
            binding, item = accounts[name]
            report = load_json(Path(binding["root"]) / item["report"])
            report_memory = memory_fingerprint(report)
            references[name] = derive_events(name, report, calendar=execution, bars=history["bars"])
            chains[name] = reconcile_chain(name, report, calendar=execution, saved_bars=history["bars"])
            summaries[name] = account_summary(report, calendar=execution)
            exposures = prior_day_exposures(report, source_calendar=calendar, ranks=history["ranks"])
            portable = name.replace("/", "--") + ".json"
            for directory, value in (("chains", chains[name]), ("exposures", exposures)):
                path = output / directory / portable
                write(path, value)
                outputs[f"{directory}/{portable}"] = file_sha(path)
            stage = announce("independent_saved_account:" + name)
            assert_memory_unchanged(report, report_memory)
            checks[name] = {
                "compact_sessions": verify_compact(report, Path(binding["root"]) / item["ledger"]),
                "events": verify_derived_events(references[name], load_json(output / "chains" / portable)),
                "metrics": verify_metrics(report, summaries[name], calendar=execution),
                "exposure": verify_exposures(report, load_json(output / "exposures" / portable),
                                              source_calendar=calendar, ranks=history["ranks"]),
                "original_report_memory_sha256": assert_memory_unchanged(report, report_memory),
            }
            finished.append(name)
            del report, exposures
        stage = announce("maintenance_support")
        binding = evidence["bindings"]["construction"]
        result = load_json(Path(binding["root"]) / "RESULT.json")
        result_memory = memory_fingerprint(result)
        persistence, maintenance_checks = {}, {}
        for policy in GROUPS["construction"]:
            targets = load_json(Path(binding["root"]) / f"targets/{policy}.json")
            target_memory = memory_fingerprint(targets)
            if [t["trade_date"] for t in targets] != execution:
                raise ValueError("exact complete target calendar required")
            membership = saved_membership(targets, result["diagnostics"][policy])
            support = support_persistence(membership, source_calendar=calendar, ranks=history["ranks"])
            path = output / "membership" / f"{policy}.json"
            write(path, {"membership": membership, "support": support})
            outputs[f"membership/{policy}.json"] = file_sha(path)
            assert_memory_unchanged(targets, target_memory)
            saved = load_json(path)
            maintenance_checks[policy] = {
                "membership": verify_membership(targets, result["diagnostics"][policy],
                                                 saved["membership"], calendar=execution),
                "support": verify_support(targets, result["diagnostics"][policy], saved["support"],
                                           source_calendar=calendar, ranks=history["ranks"]),
                "original_target_memory_sha256": assert_memory_unchanged(targets, target_memory),
                "output_sha256": file_sha(path),
            }
            persistence[policy] = {"maintenance_count": support["maintenance_count"],
                                   "scores_status": membership["score_status"]}
            del targets, membership, support
        assert_memory_unchanged(result, result_memory)
        del result
        stage = announce("explicit_frozen_source_keys")
        keys = event_source_keys(chains.values())
        if keys != required_source_keys(references.values()):
            raise ValueError("producer source query differs from independently derived complete keys")
        lookups, source_receipt = read_daily_lookups(evidence["bindings"]["sources"], keys)
        lookup_memory = lookup_fingerprint(lookups)
        query_check = verify_lookup_coverage(references.values(), keys, lookups, source_receipt)
        source_status = {}
        for name, chain in chains.items():
            stage = announce("source_explanation:" + name)
            detail = explain_event_sources(chain, source_lookups=lookups, saved_bars=history["bars"])
            path = output / "details" / (name.replace("/", "--") + ".json")
            write(path, detail)
            outputs["details/" + path.name] = file_sha(path)
            checks[name]["source"] = verify_source_details(
                references[name], load_json(path), lookups=lookups, bars=history["bars"])
            source_status[name] = detail["source_explanation_status"]
            del detail
        assert_lookups_unchanged(lookups, lookup_memory)
        stage = announce("original_history_after_fingerprint")
        assert_memory_unchanged(history, history_memory)
        del history, lookups, chains, references
        stage = announce("primary_paired_comparison")
        primary, primary_checks = {}, {}
        for cost in (82, 164):
            root = Path(evidence["bindings"]["construction"]["root"])
            response = load_json(root / f"account_reports/global_response-{cost}.json")
            risk = load_json(root / f"account_reports/global_risk-{cost}.json")
            original_pair = memory_fingerprint([response, risk])
            primary[str(cost)] = primary_difference(response, risk, calendar=execution)
            assert_memory_unchanged([response, risk], original_pair)
            primary_checks[str(cost)] = verify_primary(response, risk, primary[str(cost)], calendar=execution)
            assert_memory_unchanged([response, risk], original_pair)
            del response, risk
        stage = announce("after_input_verification")
        after = verify_unchanged(evidence)
        if before != after:
            raise ValueError("frozen input identity changed during reporting")
        if code_bindings() != code:
            raise ValueError("producer/reference code changed during reporting")
        for rel, digest in outputs.items():
            if file_sha(output / rel) != digest:
                raise ValueError("saved output changed after independent checks")
        write(output / "AFTER.json", after)
        stage = announce("complete_account_receipts")
        for name in sorted(accounts):
            binding, item = accounts[name]
            portable = name.replace("/", "--") + ".json"
            receipt = {
                "account": name, "status": "ACCOUNT_CHECKS_PASSED_PENDING_GLOBAL_ACCEPTANCE",
                "checks": checks[name], "input_evidence_sha256": before["evidence_sha256"],
                "input_files": {rel: binding["files"][rel] for rel in
                                (item["report"], item["ledger"], item["target"], "RESULT.json")},
                "shared_inputs": {label: evidence["bindings"][label]
                                  for label in ("history", "sources")},
                "output_files": {f"{d}/{portable}": outputs[f"{d}/{portable}"]
                                 for d in ("chains", "exposures", "details")},
                "summary_sha256": sha256_json(summaries[name]), "code_sha256": sha256_json(code),
                "validated_alpha": False,
            }
            path = output / "verification" / portable
            write(path, receipt)
            outputs["verification/" + portable] = file_sha(path)
        write(output / "VERIFICATION.json", {
            "account_keys": sorted(checks), "account_count": len(checks), "code": code,
            "history_memory_sha256": history_memory, "source_lookup_memory_sha256": lookup_memory,
            "membership": maintenance_checks, "primary": primary_checks, "source_query": query_check,
            "input_evidence_sha256": before["evidence_sha256"], "validated_alpha": False,
            "status": STATUS,
        })
        outputs["VERIFICATION.json"] = file_sha(output / "VERIFICATION.json")
        summary = {
            "account_count": len(summaries), "execution_calendar": execution,
            "accounts": summaries, "primary": primary, "source_status": source_status,
            "source_query": source_receipt, "membership": persistence,
            "output_files": outputs, "input_evidence_sha256": before["evidence_sha256"],
            "component_status": STATUS,
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
        "outcome": STATUS, "finished_at": now(),
        "summary_sha256": file_sha(output / "SUMMARY.json"),
        "completed_account_keys": finished, "automatic_retry": False, "validated_alpha": False})
    return summary
