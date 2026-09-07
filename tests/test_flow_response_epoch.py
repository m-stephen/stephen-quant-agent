import copy
import gc
import json
import weakref
from dataclasses import asdict

import pytest
from test_flow_response_history import frozen_sources
from test_flow_response_protocol import spec

from stephen_quant.baseline.stateful import TargetAllocation
from stephen_quant.discovery.flow_response_protocol import reserve_trials
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.flow_response_epoch import execute_reserved_epoch


def synthetic_anchors(root, calendar):
    folder = root / "artifacts/temporal-increments/epoch-001/targets"
    folder.mkdir(parents=True)
    (root / "configs").mkdir()
    card = {"targets_file_sha256": {}, "targets_canonical_sha256": {}}
    for offset, name in enumerate(("lowvol", "stable_lowrisk")):
        # Deterministic synthetic anchors; no price-dependent optimization.
        values = [
            asdict(
                TargetAllocation(
                    d,
                    d + "T08:00:00+08:00",
                    {str(600000 + n + offset): 0.025 for n in range(40)},
                    i % 20 == 0,
                )
            )
            for i, d in enumerate(calendar)
        ]
        path = folder / f"{name}.json"
        path.write_text(json.dumps(values, indent=3) + "\n", encoding="utf-8")
        card["targets_file_sha256"][name] = file_sha(path)
        card["targets_canonical_sha256"][name] = sha256_json(values)
    path = root / "configs/v11.11-frozen-stability-observation.json"
    path.write_text(json.dumps(card), encoding="utf-8")
    return file_sha(path)


@pytest.fixture(scope="module")
def epoch(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-response-epoch")
    calendar, manifest = frozen_sources(root / "inputs", span_days=770)
    plan = spec()
    plan.update(
        calendar=calendar,
        manifest_sha256=manifest,
        anchor_card_sha256=synthetic_anchors(
            root / "original", [d for d in calendar if d >= "2023-01-01"]
        ),
    )
    output = root / "operation"
    output.mkdir()
    reg, tids = reserve_trials(output, plan)
    # The later offline audit must not coexist with the producer's full cache.
    import stephen_quant.workflows.flow_response_epoch as module

    cache_type, cache_refs = module.VerifiedHistoryCache, []

    def capture(*args, **kwargs):
        cache = cache_type(*args, **kwargs)
        cache_refs.append(weakref.ref(cache))
        return cache

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "VerifiedHistoryCache", capture)
        result = execute_reserved_epoch(
            reg,
            tids,
            plan,
            output=output,
            input_folder=root / "inputs",
            original_tree=root / "original",
        )
    gc.collect()
    assert len(cache_refs) == 1 and cache_refs[0]() is None
    return root, reg, tids, plan, result


def test_complete_synthetic_epoch_all_accounts_fits_and_exact_original_bytes(
    epoch, record_testsuite_property
):
    root, reg, tids, plan, result = epoch
    assert reg.global_trial_count() == result["reserved_trials"] == 23
    assert len(result["records"]) == 22 and len(result["models_sha256"]) == 14
    assert result["raw_global_trial_lower_bound"] == 3706  # Hypothetical debt in temp fixture.
    assert not result["validated_alpha"] and not any(result["screen_survived"].values())
    assert result["independent_source_model_target_audit"] == "NOT_RUN"
    assert result["statistics"]["DSR"] is None
    with reg.connect() as conn:
        assert (
            conn.execute("SELECT count(*) FROM trials WHERE result_json IS NOT NULL").fetchone()[0]
            == 23
        )
    fits = [
        (tid, fit["artifact_sha256"])
        for tid in tids.values()
        for fit in reg.fit_lineage(tid)["fits"]
    ]
    supervised = [f for f in fits if f[0] != tids["response-provider"]]
    assert len(supervised) == 28 and len({f[1] for f in supervised}) == 14
    assert len(fits) - len(supervised) == len(plan["calendar"]) - 62
    for name, value in {
        "response_epoch_synthetic_stocks": 80,
        "response_epoch_synthetic_sessions": len(plan["calendar"]),
        "response_epoch_synthetic_history_bytes": (root / "operation/history/history.json")
        .stat()
        .st_size,
        "response_epoch_synthetic_bundle_bytes": sum(
            p.stat().st_size for p in (root / "operation/history").glob("response-*.json")
        ),
    }.items():
        record_testsuite_property(name, value)
    for row in result["records"].values():
        assert set(row["years"]) == {"2023", "2024"}
        assert row["audit"]["pass"] and not row["audit"]["independent_source_and_target_selection"]
        assert row["audit"]["maximum_balance_residual_cny"] < 1e-5
        assert row["account_sha256"] == file_sha(root / f"operation/accounts/{row['key']}.jsonl")
    for policy in (
        "response",
        "response_interaction",
        "risk",
        "raw_flow_return",
        "standardized_flow_return",
        "old_absorption",
        "shuffle",
        "hash",
        "lowvol",
        "original_lowvol",
        "original_stable",
    ):
        a, b = (result["records"][f"{policy}-{c}"] for c in (82, 164))
        assert a["target_sha256"] == b["target_sha256"] == result["targets_sha256"][policy]
        assert a["dates"] == b["dates"]
    for policy, old in (("original_lowvol", "lowvol"), ("original_stable", "stable_lowrisk")):
        assert (root / f"operation/targets/{policy}.json").read_bytes() == (
            root / f"original/artifacts/temporal-increments/epoch-001/targets/{old}.json"
        ).read_bytes()


def test_completed_backend_cannot_replay_or_overwrite(epoch, monkeypatch):
    root, reg, tids, plan, _ = epoch
    before = file_sha(root / "operation/RESULT.json")

    def poison(*args, **kwargs):
        raise AssertionError("no second numerical read")

    monkeypatch.setattr("stephen_quant.workflows.flow_response_epoch.load_original_targets", poison)
    with pytest.raises(ValueError):
        execute_reserved_epoch(
            reg,
            tids,
            plan,
            output=root / "operation",
            input_folder=root / "inputs",
            original_tree=root / "original",
        )
    assert before == file_sha(root / "operation/RESULT.json")


@pytest.fixture(scope="module")
def continued_epoch(epoch):
    from stephen_quant.discovery import flow_response_continuation as continuation

    root, inherited, old_tids, plan, original_result = epoch
    old = root / "operation"
    # Small synthetic artifacts only. Real launch uses an explicit frozen inventory.
    files = {
        p.relative_to(old).as_posix(): file_sha(p)
        for folder in (old / "models", old / "targets", old / "history")
        for p in folder.glob("*.json")
    }
    files["registry.sqlite3"] = file_sha(inherited.db_path)
    spec = {
        "version": continuation.VERSION,
        "prior_debt": 3707,
        "budget": 22,
        "new_fits": 0,
        "validated_alpha": False,
        "accounts": continuation.account_plans(),
        "research_contract": plan["contract"],
        "runtime_code_sha256": "1" * 64,
        "anchor_card_sha256": plan["anchor_card_sha256"],
        "consumed_evidence_sha256": "2" * 64,
        "inherited": {"root": str(old), "files": files, "trial_ids": old_tids},
    }
    output = root / "continuation"
    reg, tids = continuation.reserve_continuation(output, spec)

    def forbidden(*a, **kw):
        raise AssertionError("continuation must not refit production predictors/history")

    with pytest.MonkeyPatch.context() as patch:
        for target in (
            "stephen_quant.discovery.flow_response_history.fit_history_predictor",
            "stephen_quant.discovery.flow_response_history.build_history_from_frozen",
            "stephen_quant.discovery.flow_response_history.bind_shared_history_predictor",
            "stephen_quant.discovery.flow_response_predictor.fit_predictor",
        ):
            patch.setattr(target, forbidden)
        result = continuation.execute_continuation(
            reg, tids, spec, output=output, original_tree=root / "original"
        )
    return root, reg, tids, spec, result, original_result


def test_continuation_launch_complete_numerical_chain_stays_exploratory(
    continued_epoch, tmp_path, monkeypatch
):
    from pathlib import Path

    from stephen_quant.discovery import flow_response_continuation_launch as launch

    source, _, _, spec, reference, _ = continued_epoch
    root = tmp_path / "synthetic-tree"
    root.mkdir()
    plan = {
        "version": launch.VERSION,
        "claim_key": launch.CLAIM_KEY,
        "paths": {
            "worktree": str(root),
            "claim": str(tmp_path / "common/once.json"),
            "original": str(source / "original"),
            "inputs": str(source / "inputs"),
        },
        "spec": copy.deepcopy(spec),
        "prior_debt": 3707,
        "budget": 22,
        "validated_alpha": False,
    }
    frozen = copy.deepcopy(plan)
    monkeypatch.setattr(launch, "prepare_plan", lambda _: copy.deepcopy(frozen))
    monkeypatch.setattr(
        launch, "fetch_preregistration", lambda i, d, _: {"id": i, "plan_sha256": d}
    )
    monkeypatch.setattr(launch, "_resource_preflight", lambda: {"synthetic": True})
    calls = []

    def synthetic_supervisor(command, **kwargs):
        # The Windows supervisor/resource lifecycle is tested independently.
        # Here both actual numerical stages run, with only host orchestration stubbed.
        stage, output = command[2], Path(command[-1])
        calls.append(stage)
        assert launch.ReadOnlyRegistry(output / "registry.sqlite3").global_trial_count() == 22
        launch.run_stage(stage, operation=output, worktree=root)
        receipt = {"outcome": "COMPLETED", "exit_code": 0, "samples": 1}
        launch.write(kwargs["output"] / "SUPERVISOR.json", receipt)
        return receipt

    monkeypatch.setattr(launch, "supervise", synthetic_supervisor)
    path = root / "plan.json"
    launch.write(path, plan)
    terminal = launch.launch(path, comment_id=184, worktree=root)
    output = launch.operation_path(plan, sha256_json(plan))
    assert calls == ["backend", "audit"]
    assert terminal["outcome"] == "COMPLETE_EXPLORATORY_AUDITED"
    assert terminal["native_reserved"] == terminal["committed_attempt_budget"] == 22
    assert terminal["raw_global_trial_lower_bound"] == 3729
    assert not terminal["validated_alpha"]
    assessment = launch.read(output / "ASSESSMENT.json")
    assert not assessment["validated_alpha"]
    assert assessment["statistics"] == launch.contract()["statistics"]
    assert launch.read(output / "AUDIT.json")["pipeline_audit_pass"]
    result = launch.read(output / "RESULT.json")
    for key in reference["records"]:
        assert (
            result["records"][key]["account_sha256"] == reference["records"][key]["account_sha256"]
        )
    before = {
        name: file_sha(output / name) for name in ("RESULT.json", "registry.sqlite3", "AUDIT.json")
    }
    with pytest.raises(FileExistsError):
        launch.launch(path, comment_id=184, worktree=root)
    for stage in ("backend", "audit"):
        with pytest.raises(ValueError, match="active shared claim"):
            launch.run_stage(stage, operation=output, worktree=root)
    assert before == {name: file_sha(output / name) for name in before}


def test_complete_frozen_continuation_all22_no_new_fits(continued_epoch):
    from stephen_quant.discovery import flow_response_continuation as continuation

    root, reg, tids, spec, result, original_result = continued_epoch
    output, old = root / "continuation", root / "operation"
    assert result["reserved_trials"] == len(result["records"]) == 22
    assert result["new_fits"] == 0 and result["raw_global_trial_lower_bound"] == 3729
    assert result["inherited_supervised_models"] == 14
    assert result["inherited_native_bindings"] == 28
    assert not result["validated_alpha"]
    assert result["models_sha256"] == original_result["models_sha256"]
    for key, record in result["records"].items():
        original = original_result["records"][key]
        assert record["metrics"] == original["metrics"]
        assert record["audit"] == original["audit"]
        assert record["account_sha256"] == original["account_sha256"]
    for policy in result["targets_sha256"]:
        assert json.loads((output / f"targets/{policy}.json").read_bytes()) == json.loads(
            (old / f"targets/{policy}.json").read_bytes()
        )
    assert file_sha(old / "registry.sqlite3") == spec["inherited"]["files"]["registry.sqlite3"]
    for tid in tids.values():
        assert not reg.fit_lineage(tid)["fits"] and not reg.feature_sources(tid)["providers"]
    with pytest.raises(ValueError):
        continuation.execute_continuation(
            reg, tids, spec, output=output, original_tree=root / "original"
        )


def test_independent_mature_models_and_targets_from_both_years(epoch, monkeypatch):
    from stephen_quant.discovery.flow_response_model_audit import audit_models_targets

    root, reg, tids, _, _ = epoch

    def poison(*args, **kwargs):
        raise AssertionError("independent model/target audit used a production calculation")

    for target in (
        "stephen_quant.discovery.flow_response_predictor.fit_predictor",
        "stephen_quant.discovery.flow_response_predictor.pairs_for_year",
        "stephen_quant.discovery.flow_response_predictor.vector",
        "stephen_quant.discovery.flow_response_predictor.predict",
        "stephen_quant.discovery.flow_response_accounts.history_targets",
        "stephen_quant.discovery.pairwise_ranking.select",
        "stephen_quant.discovery.pairwise_ranking.leg_label",
        "stephen_quant.discovery.calendar_robustness.combine_sleeves",
    ):
        monkeypatch.setattr(target, poison)
    evidence = audit_models_targets(
        reg,
        tids,
        history_path=root / "operation/history/history.json",
        operation=root / "operation",
    )
    assert evidence["supervised_model_target_audit_pass"]
    assert evidence["models_checked"] == 14 and evidence["native_bindings_checked"] == 28
    assert evidence["policies_checked"] == 9
    assert not evidence["complete_pipeline_audit_pass"] and not evidence["validated_alpha"]


def test_complete_continuation_audit_is_independent_readonly_single_decode(
    continued_epoch, monkeypatch
):
    from stephen_quant.discovery import flow_response_continuation_audit as audit
    from stephen_quant.discovery import flow_response_history as history_module

    root, reg, _, _, result, _ = continued_epoch
    output = root / "continuation"
    files = [output / "RESULT.json", reg.db_path, root / "operation/registry.sqlite3"]
    before = [file_sha(p) for p in files]

    def forbidden(*a, **kw):
        raise AssertionError("independent audit called production numerical path or fit binding")

    for target in (
        "stephen_quant.discovery.flow_response_predictor.fit_predictor",
        "stephen_quant.discovery.flow_response_predictor.pairs_for_year",
        "stephen_quant.discovery.flow_response_predictor.vector",
        "stephen_quant.discovery.flow_response_predictor.predict",
        "stephen_quant.discovery.flow_response_accounts.history_targets",
        "stephen_quant.discovery.flow_response_accounts.execute_response_account",
        "stephen_quant.discovery.flow_response_series.fit_response_bundle",
        "stephen_quant.discovery.flow_response_series.bridge_source_rows",
        "stephen_quant.discovery.flow_response_history.fit_history_predictor",
        "stephen_quant.discovery.flow_response_history.build_history_from_frozen",
        "stephen_quant.qmt.flow_response_panel.build_response_panel",
        "stephen_quant.discovery.pairwise_ranking.select",
        "stephen_quant.discovery.pairwise_ranking.leg_label",
        "stephen_quant.discovery.calendar_robustness.combine_sleeves",
        "stephen_quant.baseline.stateful.run_stateful_execution",
        "stephen_quant.integrity.registry.ExperimentRegistry.record_model_fit",
    ):
        monkeypatch.setattr(target, forbidden)
    loader, loads = history_module.load_json, []

    def capture(path, **kw):
        loads.append((path, kw))
        return loader(path, **kw)

    monkeypatch.setattr(history_module, "load_json", capture)
    # A failed inherited epoch does not have RESULT.json. Do not manufacture it
    # merely to make the old completed-epoch auditor accept a continuation.
    old_result = root / "operation/RESULT.json"
    raw_old_result = old_result.read_bytes()
    old_result.unlink()  # Synthetic temporary fixture only.
    try:
        evidence = audit.audit_complete_continuation(
            operation=output, input_folder=root / "inputs", original_tree=root / "original"
        )
    finally:
        old_result.write_bytes(raw_old_result)
    assert len(loads) == 1 and loads[0][1] == {"immutable": True}
    assert evidence["pipeline_audit_pass"] and not evidence["validated_alpha"]
    assert not evidence["launch_authorization_verified"]
    assert evidence["new_native_accounts_checked"] == 22 and evidence["new_fits"] == 0
    assert evidence["raw_global_trial_lower_bound"] == 3729  # Synthetic only.
    assert evidence["model_target_audit"]["models_checked"] == 14
    assert evidence["model_target_audit"]["native_bindings_checked"] == 28
    assert evidence["model_target_audit"]["policies_checked"] == 9
    assert len(evidence["accounts"]) == 22
    assert evidence["statistics"]["DSR"] is None
    assert evidence["source_audit"]["source_numeric_years"] == [2022, 2023, 2024]
    assert evidence["model_target_audit"]["models_sha256"] == result["models_sha256"]
    assert not evidence["audited_screen"]["validated_alpha"]
    assert all(
        v["independent_audit"]
        for costs in evidence["audited_screen"]["checks"].values()
        for v in costs.values()
    )
    assert before == [file_sha(p) for p in files]


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_trial",
        "missing_control",
        "debt",
        "fit",
        "alpha",
        "status",
        "inherited_hash",
        "model_count",
        "binding_count",
        "spec",
        "native_record",
        "statistics",
        "diagnostic",
        "target_set",
        "promoted_screen",
    ],
)
def test_continuation_audit_native_gate_before_inherited_reads(
    continued_epoch, monkeypatch, change
):
    from stephen_quant.discovery import flow_response_continuation_audit as audit

    root, _, _, _, result, _ = continued_epoch
    path = root / "continuation/RESULT.json"
    raw = path.read_bytes()
    value = copy.deepcopy(result)
    if change == "duplicate_trial":
        value["trial_ids"]["risk-82"] = value["trial_ids"]["response-82"]
    elif change == "missing_control":
        del value["records"]["risk-82"]
    elif change == "debt":
        value["raw_global_trial_lower_bound"] -= 23
    elif change == "fit":
        value["new_fits"] = 14
    elif change == "alpha":
        value["validated_alpha"] = True
    elif change == "status":
        value["status"] = "PARTIAL"
    elif change == "inherited_hash":
        value["inherited_sha256"] = "0" * 64
    elif change == "model_count":
        value["inherited_supervised_models"] = 13
    elif change == "binding_count":
        value["inherited_native_bindings"] = 14
    elif change == "spec":
        value["spec_sha256"] = "0" * 64
    elif change == "native_record":
        value["records"]["risk-82"]["profit_cny"] += 100
    elif change == "statistics":
        value["statistics"]["DSR"] = 0.99
    elif change == "diagnostic":
        del value["diagnostics"]["risk"]
    elif change == "target_set":
        del value["targets_sha256"]["original_stable"]
    else:
        value["checks"]["response"]["82"]["independent_audit"] = True

    def forbidden(*a, **kw):
        raise AssertionError("inherited numerical read before complete native preflight")

    monkeypatch.setattr(audit, "verified_inherited", forbidden)
    try:
        path.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError):
            audit.audit_complete_continuation(
                operation=path.parent, input_folder=root / "inputs", original_tree=root / "original"
            )
    finally:
        path.write_bytes(raw)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE experiments SET code_version='changed'",
        "UPDATE data_snapshots SET snapshot_sha256='changed'",
        "UPDATE trials SET result_json=NULL WHERE rowid=(SELECT min(rowid) FROM trials)",
        'UPDATE trial_fit_contracts SET stages_json=\'[{"stage_id":"unapproved"}]\'',
    ],
)
def test_continuation_audit_rejects_mutated_native_metadata(
    continued_epoch, tmp_path, monkeypatch, statement
):
    import shutil
    import sqlite3

    from stephen_quant.discovery import flow_response_continuation_audit as audit

    root, _, _, _, _, _ = continued_epoch
    for name in ("frozen_spec.json", "RESULT.json", "registry.sqlite3"):
        shutil.copyfile(root / "continuation" / name, tmp_path / name)
    with sqlite3.connect(tmp_path / "registry.sqlite3") as db:
        if "trial_fit_contracts" in statement:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute(statement)
            # Deliberately corrupt this *copied synthetic* database after proving
            # its native trigger rejects normal mutation. The offline audit must
            # also reject the forgery, not rely solely on the write trigger.
            db.execute("DROP TRIGGER trial_fit_contracts_no_update")
        db.execute(statement)

    def forbidden(*a, **kw):
        raise AssertionError("mutated native metadata reached inherited reader")

    monkeypatch.setattr(audit, "verified_inherited", forbidden)
    with pytest.raises(ValueError):
        audit.audit_complete_continuation(
            operation=tmp_path, input_folder=root / "inputs", original_tree=root / "original"
        )


@pytest.mark.parametrize(
    "relative", ["history/history.json", "models/risk-2023.json", "targets/response.json"]
)
def test_continuation_rejects_changed_inherited_artifact_before_decode(
    continued_epoch, monkeypatch, relative
):
    from stephen_quant.discovery import flow_response_continuation_audit as audit

    root, _, _, _, _, _ = continued_epoch
    path = root / "operation" / relative
    raw = path.read_bytes()

    def forbidden(*a, **kw):
        raise AssertionError("changed inherited bytes reached history decoder")

    monkeypatch.setattr(audit, "VerifiedHistoryCache", forbidden)
    try:
        path.write_bytes(raw + b"\n")
        with pytest.raises(ValueError, match="inherited evidence"):
            audit.audit_complete_continuation(
                operation=root / "continuation",
                input_folder=root / "inputs",
                original_tree=root / "original",
            )
    finally:
        path.write_bytes(raw)


@pytest.fixture(scope="module")
def continuation_audit_history(continued_epoch):
    root, _, _, _, _, _ = continued_epoch
    return json.loads((root / "operation/history/history.json").read_bytes())


@pytest.mark.parametrize(
    "change", ["returns", "dates", "profit", "execution", "cash", "mark", "cost"]
)
def test_independent_continuation_account_rejects_self_consistent_rehashed_report(
    continued_epoch, continuation_audit_history, tmp_path, change
):
    import shutil

    from stephen_quant.discovery.flow_response_continuation import account_plans
    from stephen_quant.discovery.flow_response_epoch_audit import audit_saved_accounts

    root, _, tids, _, original, _ = continued_epoch
    key, policy = "response-82", "response"
    result = copy.deepcopy(original)
    record = result["records"][key]
    for relative in (
        f"targets/{policy}.json",
        f"accounts/{key}.jsonl",
        f"account_reports/{key}.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(root / "continuation" / relative, target)
    path = tmp_path / f"account_reports/{key}.json"
    report = json.loads(path.read_bytes())
    if change == "returns":
        record["daily_returns"][0] += 0.1
    elif change == "dates":
        record["dates"][0] = "2025-01-01"
    elif change == "profit":
        record["profit_cny"] += 1000
    elif change == "execution":
        record["execution"]["mean_cash_fraction"] = -1
    else:
        period = next(p for p in report["periods"] if p["marks"] and p["orders"])
        if change == "cash":
            period["cash"] += 1000
        elif change == "cost":
            period["orders"][0]["total_cost"] += 1000
        else:
            period["marks"][0]["shares"] += 1
        path.write_text(json.dumps(report), encoding="utf-8")
        record["full_account_sha256"] = file_sha(path)
        # Also forge the compact copy and its digest. Numerical audit, not merely
        # comparison of two copies, must reject the changed order/cash/holding.
        compact_path = tmp_path / f"accounts/{key}.jsonl"
        compact = [json.loads(line) for line in compact_path.read_text().splitlines()]
        row = next(r for r in compact if r["date"] == period["trade_date"])
        row.update(cash=period["cash"], positions=period["marks"], orders=period["orders"])
        compact_path.write_text("".join(json.dumps(r) + "\n" for r in compact), encoding="utf-8")
        record["account_sha256"] = file_sha(compact_path)
    with pytest.raises(ValueError):
        audit_saved_accounts(
            tmp_path,
            result,
            tids,
            continuation_audit_history,
            [p for p in account_plans() if p["key"] == key],
        )


@pytest.fixture(scope="module")
def audited_epoch(epoch):
    from stephen_quant.discovery.flow_response_epoch_audit import audit_complete_epoch
    from stephen_quant.discovery.flow_response_launch import ReadOnlyRegistry

    root, reg, _, _, _ = epoch
    before = file_sha(root / "operation/RESULT.json"), file_sha(reg.db_path)
    evidence = audit_complete_epoch(
        ReadOnlyRegistry(reg.db_path),
        operation=root / "operation",
        input_folder=root / "inputs",
        original_tree=root / "original",
    )
    assert before == (file_sha(root / "operation/RESULT.json"), file_sha(reg.db_path))
    return epoch, evidence


def test_complete_saved_pipeline_audit_is_not_alpha_certification(audited_epoch):
    (root, _, _, plan, result), evidence = audited_epoch
    assert evidence["pipeline_audit_pass"] and not evidence["validated_alpha"]
    assert evidence["source_audit"]["sessions_checked"] == len(plan["calendar"])
    assert (
        evidence["source_audit"]["per_stock_response_fits_checked"]
        == (len(plan["calendar"]) - 62) * 80
    )
    assert evidence["model_target_audit"]["models_checked"] == 14
    assert len(evidence["accounts"]) == 22
    assert all(
        r["pass"] and r["independent_execution_intent"] for r in evidence["accounts"].values()
    )
    assert evidence["result_sha256"] == file_sha(root / "operation/RESULT.json")
    assert result["statistics"]["DSR"] is None and not result["validated_alpha"]


@pytest.mark.parametrize(
    "kind", ["duplicate_trial", "native_account", "spec", "omitted_failed_debt"]
)
def test_offline_audit_rejects_changed_operation_before_source_read(epoch, monkeypatch, kind):
    from stephen_quant.discovery.flow_response_epoch_audit import audit_complete_epoch

    root, reg, _, _, _ = epoch
    path = root / "operation/RESULT.json"
    raw = path.read_bytes()
    changed = json.loads(raw)
    if kind == "duplicate_trial":
        changed["trial_ids"]["response-164"] = changed["trial_ids"]["response-82"]
    elif kind == "native_account":
        changed["records"]["response-82"]["profit_cny"] += 100
    elif kind == "omitted_failed_debt":
        changed["raw_global_trial_lower_bound"] = 3683
    else:
        changed["spec_sha256"] = "a" * 64

    def poison(*args, **kwargs):
        raise AssertionError("source should not be read before native preflight")

    monkeypatch.setattr(
        "stephen_quant.discovery.flow_response_epoch_audit.audit_source_history", poison
    )
    try:
        path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError):
            audit_complete_epoch(
                reg,
                operation=root / "operation",
                input_folder=root / "inputs",
                original_tree=root / "original",
            )
    finally:
        path.write_bytes(raw)


@pytest.mark.parametrize("kind", ["missing", "spec", "overlap", "database"])
def test_backend_preflight_before_target_or_source_read(tmp_path, monkeypatch, kind):
    plan = spec()
    output = tmp_path / "operation"
    output.mkdir()
    reg, tids = reserve_trials(output, plan)
    supplied = copy.deepcopy(plan)
    if kind == "missing":
        tids.pop("response-82")
    if kind == "spec":
        supplied["manifest_sha256"] = "d" * 64

    def poison(*args, **kwargs):
        raise AssertionError("unauthorized numerical reader")

    monkeypatch.setattr("stephen_quant.workflows.flow_response_epoch.load_original_targets", poison)
    monkeypatch.setattr(
        "stephen_quant.workflows.flow_response_epoch.build_history_from_frozen", poison
    )
    with pytest.raises(ValueError):
        execute_reserved_epoch(
            reg,
            tids,
            supplied,
            output=tmp_path / "different" if kind == "database" else output,
            input_folder=output / "source" if kind == "overlap" else tmp_path / "inputs",
            original_tree=tmp_path / "original",
        )
    assert not (output / "BACKEND_CLAIM.json").exists()


def test_partial_failure_retains_all_reservations_and_refuses_retry(tmp_path, monkeypatch):
    plan = spec()
    plan["anchor_card_sha256"] = synthetic_anchors(
        tmp_path / "original", [d for d in plan["calendar"] if d >= "2023-01-01"]
    )
    output = tmp_path / "operation"
    output.mkdir()
    reg, tids = reserve_trials(output, plan)

    def fail(*args, **kwargs):
        raise ValueError("synthetic source failure")

    monkeypatch.setattr(
        "stephen_quant.workflows.flow_response_epoch.build_history_from_frozen", fail
    )
    kwargs = {
        "output": output,
        "input_folder": tmp_path / "inputs",
        "original_tree": tmp_path / "original",
    }
    with pytest.raises(ValueError, match="synthetic source failure"):
        execute_reserved_epoch(reg, tids, plan, **kwargs)
    abort = json.loads((output / "ABORTED.json").read_bytes())
    assert abort["reserved_trials"] == reg.global_trial_count() == 23
    assert abort["raw_global_trial_lower_bound"] == 3706
    assert abort["completed_account_keys"] == [] and not (output / "RESULT.json").exists()
    abort_sha = file_sha(output / "ABORTED.json")
    with pytest.raises(FileExistsError):
        execute_reserved_epoch(reg, tids, plan, **kwargs)
    assert abort_sha == file_sha(output / "ABORTED.json")
