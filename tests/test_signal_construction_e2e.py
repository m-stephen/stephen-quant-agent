"""Complete native four-account backend -> independent audit, synthetic only.

The 726-session fictional weekday calendar is NOT an exchange calendar. All
sources,23 inherited identities,14 fitted model files and28 cost bindings are
generated in pytest temporary directories through original production APIs.
No empirical files, claims or ledgers are read. This is not launch approval.
"""

import copy
import gc

import pytest
from test_flow_response_history import frozen_sources
from test_flow_response_protocol import spec as original_spec

from stephen_quant.discovery import signal_construction_runtime as runtime
from stephen_quant.discovery.flow_response_history import (
    VerifiedHistoryCache,
    bind_shared_history_predictor,
    build_history_from_frozen,
    fit_history_predictor,
)
from stephen_quant.discovery.flow_response_predictor import POLICIES
from stephen_quant.discovery.flow_response_protocol import plans, reserve_trials
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.signal_construction_audit import audit_complete_accounts
from stephen_quant.qmt.reliable_panel import file_sha


def forbidden(*args, **kwargs):
    raise AssertionError("bridge/auditor called a forbidden production fit or numerical path")


@pytest.fixture(scope="module")
def complete_bridge(tmp_path_factory):
    root = tmp_path_factory.mktemp("SYNTHETIC-complete-signal-bridge")
    calendar, manifest = frozen_sources(root / "inputs", span_days=1016, stock_count=80)
    assert len(calendar) == 726 and calendar[-1] < "2025-01-01"
    proposal = original_spec()
    proposal.update(calendar=calendar, manifest_sha256=manifest)
    inherited = root / "inherited"
    inherited.mkdir()
    old, old_tids = reserve_trials(inherited, proposal)
    provider = old_tids["response-provider"]
    consumers = tuple(
        old_tids[p["key"]] for p in plans()[1:] if not p["response_policy"].startswith("original_")
    )
    history = build_history_from_frozen(
        old,
        provider,
        consumers,
        input_folder=root / "inputs",
        output_folder=inherited / "history",
        calendar=calendar,
        manifest_sha256=manifest,
    )
    cache = VerifiedHistoryCache(old, old_tids["response-82"], history)
    (inherited / "models").mkdir()
    for policy in POLICIES:
        for year in (2023, 2024):
            fit_history_predictor(
                old,
                old_tids[f"{policy}-82"],
                provider,
                history_path=history,
                year=year,
                policy=policy,
                model_path=inherited / f"models/{policy}-{year}.json",
                cache=cache,
            )
        for year in (2023, 2024):
            bind_shared_history_predictor(
                old,
                old_tids[f"{policy}-82"],
                old_tids[f"{policy}-164"],
                provider,
                history_path=history,
                model_path=inherited / f"models/{policy}-{year}.json",
                year=year,
                policy=policy,
                calendar=calendar,
            )
    del cache
    gc.collect()
    # Explicit required inventory, not a scan of any user directory.
    relative = ["registry.sqlite3", "history/history.json"] + [
        f"models/{p}-{year}.json" for p in POLICIES for year in (2023, 2024)
    ]
    files = {name: file_sha(inherited / name) for name in relative}
    spec = {
        "version": runtime.VERSION,
        "prior_debt": runtime.PRIOR_DEBT,
        "budget": runtime.BUDGET,
        "new_fits": 0,
        "validated_alpha": False,
        "research_contract": runtime.contract(),
        "runtime_code_sha256": sha256_json("SYNTHETIC-code-not-launch-authority"),
        "completed_parent_evidence_sha256": sha256_json("SYNTHETIC-parent-not-a-market-claim"),
        "inherited": {"root": str(inherited), "files": files, "trial_ids": old_tids},
        "calendar": {"count": len(calendar), "sha256": sha256_json(calendar)},
    }
    output = root / "bridge"
    reg, tids = runtime.reserve_accounts(output, spec)
    with pytest.MonkeyPatch.context() as patch:
        for name in (
            "flow_response_history.fit_history_predictor",
            "flow_response_history.build_history_from_frozen",
            "flow_response_history.bind_shared_history_predictor",
            "flow_response_predictor.fit_predictor",
        ):
            patch.setattr("stephen_quant.discovery." + name, forbidden)
        result = runtime.execute_accounts(reg, tids, spec, output=output)
    gc.collect()
    with pytest.MonkeyPatch.context() as patch:
        for name in (
            "signal_construction_runtime.frozen_targets",
            "signal_construction_runtime.execute_response_account",
            "signal_construction.frozen_targets",
            "signal_construction.select_global_signal",
            "flow_response_predictor.predict",
            "flow_response_predictor.guarded_predict",
        ):
            patch.setattr("stephen_quant.discovery." + name, forbidden)
        audit = audit_complete_accounts(operation=output, input_folder=root / "inputs")
    return root, reg, tids, spec, result, audit


def test_full_four_account_native_source_score_target_and_execution_audit(complete_bridge):
    root, reg, _, spec, result, audit = complete_bridge
    assert reg.global_trial_count() == result["reserved_trials"] == 4
    assert result["raw_global_trial_lower_bound"] == audit["raw_global_trial_lower_bound"] == 3737
    assert audit["pipeline_audit_pass"] and not audit["validated_alpha"]
    assert not audit["launch_authorization_verified"] and not result["validated_alpha"]
    assert result["new_fits"] == audit["new_fits"] == 0
    assert len(result["models_sha256"]) == 14
    assert audit["source_audit"]["sessions_checked"] == 726
    assert audit["source_audit"]["source_history_audit_pass"]
    assert len(audit["accounts"]) == len(result["records"]) == 4
    assert audit["independent_target_sha256"] == result["targets_sha256"]
    assert all(result["statistics"][k] is None for k in ("dsr", "pbo", "placebo"))
    with reg.connect() as db:
        assert db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 0
    for policy in ("global_response", "global_risk"):
        a, b = (result["records"][f"{policy}-{c}"] for c in (82, 164))
        assert a["target_sha256"] == b["target_sha256"]
        assert a["dates"] == b["dates"]
        assert set(a["years"]) == set(b["years"]) == {"2023", "2024"}
        for cost in (82, 164):
            assert audit["accounts"][f"{policy}-{cost}"]["pass"]
    for name, digest in spec["inherited"]["files"].items():
        assert file_sha(root / "inherited" / name) == digest


def test_full_completed_bridge_cannot_replay_or_refit(complete_bridge, monkeypatch):
    root, reg, tids, spec, _, _ = complete_bridge
    before = file_sha(root / "bridge/RESULT.json")
    monkeypatch.setattr(runtime, "open_inputs", forbidden)
    with pytest.raises(ValueError, match="native policy"):
        runtime.execute_accounts(reg, tids, spec, output=root / "bridge")
    assert before == file_sha(root / "bridge/RESULT.json")


@pytest.mark.parametrize("fault", ["model", "profit", "calendar"])
def test_full_native_result_binding_rejects_forgery(complete_bridge, fault):
    root, reg, tids, spec, result, _ = complete_bridge
    bad = copy.deepcopy(result)
    if fault == "model":
        bad["models_sha256"]["risk-2023"] = "a" * 64
    elif fault == "profit":
        bad["records"]["global_response-82"]["profit_cny"] += 1
    else:
        bad["calendar"]["sha256"] = "b" * 64
    with pytest.raises(ValueError):
        runtime.check_native(reg, root / "bridge", spec, tids, bad)


@pytest.fixture(scope="module")
def completed_audit_envelope(complete_bridge):
    from stephen_quant.discovery import signal_construction_launch as launch

    source, _, _, spec, _, audit = complete_bridge
    root = source / "bridge"
    plan = {
        "spec": spec,
        "evidence": {
            "sources": {
                n + ".parquet": file_sha(source / "inputs" / (n + ".parquet"))
                for n in ("daily", "fund_flow")
            }
        },
    }
    digest = sha256_json(plan)
    # Unit-test OS envelope only; numerical RESULT and AUDIT are actual fixture outputs.
    launch.write(root / "LAUNCH.json", {"plan": plan})
    launch.write(root / "AUDIT.json", audit)
    launch.write(
        root / "supervisor-backend/SUPERVISOR.json",
        {"outcome": "COMPLETED", "exit_code": 0, "samples": 1, "synthetic_os_envelope": True},
    )
    launch.write(
        root / "BACKEND_COMPLETED.json",
        {
            "result_sha256": file_sha(root / "RESULT.json"),
            "registry_sha256": file_sha(root / "registry.sqlite3"),
            "supervisor_sha256": file_sha(root / "supervisor-backend/SUPERVISOR.json"),
        },
    )
    launch.write(
        root / "ASSESSMENT.json",
        {
            "status": "COMPLETE_DIAGNOSTIC_AUDITED",
            "validated_alpha": False,
            "plan_sha256": digest,
            "result_sha256": file_sha(root / "RESULT.json"),
            "audit_sha256": file_sha(root / "AUDIT.json"),
            "statistics": launch.contract()["statistics"],
        },
    )
    launch.verify_audit(root, digest, spec)
    return root, digest, spec


@pytest.mark.parametrize(
    "fault",
    [
        "missing_source",
        "failed_source",
        "coverage",
        "years",
        "history",
        "source_hash",
        "full_report_hash",
        "compact_bytes",
        "report_bytes",
        "target_bytes",
    ],
)
def test_final_audit_rejects_rehashed_incomplete_or_changed_evidence(
    completed_audit_envelope, fault
):
    import json

    from stephen_quant.discovery import signal_construction_launch as launch

    root, digest, spec = completed_audit_envelope
    audit_file, assessment_file = root / "AUDIT.json", root / "ASSESSMENT.json"
    originals = {p: p.read_bytes() for p in (audit_file, assessment_file)}
    try:
        audit = launch.read(audit_file)
        if fault == "missing_source":
            del audit["source_audit"]
        elif fault == "full_report_hash":
            audit["full_account_report_sha256"]["global_response-82"] = "a" * 64
        elif fault.endswith("_bytes"):
            relative = {
                "compact_bytes": "accounts/global_response-82.jsonl",
                "report_bytes": "account_reports/global_risk-164.json",
                "target_bytes": "targets/global_response.json",
            }[fault]
            path = root / relative
            originals[path] = path.read_bytes()
            path.write_bytes(originals[path] + b"\n")
        else:
            key, value = {
                "failed_source": ("source_history_audit_pass", False),
                "coverage": ("sessions_checked", 725),
                "years": ("source_numeric_years", [2023, 2024]),
                "history": ("history_artifact_sha256", "a" * 64),
                "source_hash": ("source_sha256", {"daily": "b" * 64, "fund_flow": "c" * 64}),
            }[fault]
            audit["source_audit"][key] = value
        audit_file.write_text(json.dumps(audit))
        assessment = launch.read(assessment_file)
        assessment["audit_sha256"] = file_sha(audit_file)
        assessment_file.write_text(json.dumps(assessment))
        with pytest.raises((ValueError, KeyError)):
            launch.verify_audit(root, digest, spec)
    finally:
        for path, raw in originals.items():
            path.write_bytes(raw)
    launch.verify_audit(root, digest, spec)


def test_once_only_launcher_complete_synthetic_chain(complete_bridge, tmp_path, monkeypatch):
    from pathlib import Path

    from stephen_quant.discovery import signal_construction_launch as launch

    source, _, _, spec, _, _ = complete_bridge
    plan = {
        "version": launch.VERSION,
        "claim_key": launch.CLAIM_KEY,
        "evidence": {
            "sources": {
                name + ".parquet": file_sha(source / "inputs" / (name + ".parquet"))
                for name in ("daily", "fund_flow")
            }
        },
        "paths": {
            "worktree": str(tmp_path),
            "claim": str(tmp_path / "common/once.json"),
            "inputs": str(source / "inputs"),
        },
        "spec": spec,
        "prior_debt": 3733,
        "budget": 4,
        "validated_alpha": False,
    }
    monkeypatch.setattr(launch, "prepare_plan", lambda _: copy.deepcopy(plan))
    monkeypatch.setattr(
        launch, "fetch_preregistration", lambda i, d, _: {"id": i, "plan_sha256": d}
    )
    monkeypatch.setattr(launch, "_resource_preflight", lambda: {"synthetic": True})
    stages = []

    def child(command, **kw):
        # Only OS monitoring is stubbed here. Both full native numerical stages run.
        stage = command[2]
        stages.append(stage)
        launch.run_stage(stage, operation=command[-1], worktree=tmp_path)
        receipt = {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
        launch.write(Path(kw["output"]) / "SUPERVISOR.json", receipt)
        return receipt

    monkeypatch.setattr(launch, "supervise", child)
    path = tmp_path / "plan.json"
    launch.write(path, plan)
    terminal = launch.launch(path, comment_id=204, worktree=tmp_path)
    assert terminal["outcome"] == "COMPLETE_DIAGNOSTIC_AUDITED"
    assert terminal["native_reserved"] == 4 and terminal["raw_global_trial_lower_bound"] == 3737
    assert stages == ["backend", "audit"] and not terminal["validated_alpha"]
    output = launch.operation_path(plan, sha256_json(plan))
    before = {n: file_sha(output / n) for n in ("RESULT.json", "registry.sqlite3", "AUDIT.json")}
    assert launch.read(output / "AUDIT.json")["pipeline_audit_pass"]
    with pytest.raises(FileExistsError):
        launch.launch(path, comment_id=204, worktree=tmp_path)
    for stage in ("backend", "audit"):
        with pytest.raises(ValueError, match="active shared"):
            launch.run_stage(stage, operation=output, worktree=tmp_path)
    assert before == {n: file_sha(output / n) for n in before}
