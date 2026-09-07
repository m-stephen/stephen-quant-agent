import copy
import json
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
    result = execute_reserved_epoch(
        reg,
        tids,
        plan,
        output=output,
        input_folder=root / "inputs",
        original_tree=root / "original",
    )
    return root, reg, tids, plan, result


def test_complete_synthetic_epoch_all_accounts_fits_and_exact_original_bytes(
    epoch, record_testsuite_property
):
    root, reg, tids, plan, result = epoch
    assert reg.global_trial_count() == result["reserved_trials"] == 23
    assert len(result["records"]) == 22 and len(result["models_sha256"]) == 14
    assert result["raw_global_trial_lower_bound"] == 3683  # Hypothetical debt in temp fixture.
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
    assert abort["raw_global_trial_lower_bound"] == 3683
    assert abort["completed_account_keys"] == [] and not (output / "RESULT.json").exists()
    abort_sha = file_sha(output / "ABORTED.json")
    with pytest.raises(FileExistsError):
        execute_reserved_epoch(reg, tids, plan, **kwargs)
    assert abort_sha == file_sha(output / "ABORTED.json")
