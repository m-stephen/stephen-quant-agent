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
