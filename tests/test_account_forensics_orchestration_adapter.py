"""Tiny metadata-only tests of the explicit synthetic integration adapter."""

import importlib.util
from pathlib import Path

import pytest

from stephen_quant.discovery.account_forensics_acceptance import read
from stephen_quant.discovery.flow_response_launch import write
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    driver = Path(__file__).parent / "support/account_forensics_orchestration.py"
    spec = importlib.util.spec_from_file_location("forensic_test_adapter", driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "worktree"
    root.mkdir()
    for name in (module.DRIVER, *module.FIXTURES, "src/stephen_quant/synthetic.py",
                 "scripts/run_account_forensics.py", "scripts/run_flow_response.py"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic metadata bytes", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "SLOT", root / "artifacts/v123-launcher-orchestration-once")
    monkeypatch.setattr(module.runner, "require_host", lambda: None)
    monkeypatch.setattr(module.planner, "runtime_evidence", lambda: {"synthetic_unit_test": True})
    # Restore every explicit module attribute changed by install_boundaries.
    for target, names in ((module.planner, ("PLAN", "COMMIT", "CLAIM_KEY", "DRIVER", "paths",
                                           "code_snapshot", "completed_inputs")),
                          (module.runner, ("CLAIM_KEY", "DRIVER", "paths", "code_snapshot",
                                           "fetch_preregistration"))):
        for name in names:
            monkeypatch.setattr(target, name, getattr(target, name))
    return module


def test_metadata_prepare_frozen_and_exclusive(adapter):
    adapter.prepare()
    frozen = adapter.frozen_start()
    assert frozen["synthetic_only"] is True
    assert frozen["code"]["files"] == adapter.code_bytes()["files"]
    assert not (adapter.SLOT / "START.json").exists()
    assert not (adapter.SLOT / "fixture").exists()
    with pytest.raises(FileExistsError):
        adapter.prepare()


@pytest.mark.parametrize("field", ["helper", "fixture", "package", "runtime", "limits"])
def test_changed_freeze_is_refused(adapter, monkeypatch, field):
    adapter.prepare()
    if field in ("helper", "fixture", "package"):
        name = {"helper": adapter.DRIVER, "fixture": adapter.FIXTURES[0],
                "package": "src/stephen_quant/synthetic.py"}[field]
        (adapter.ROOT / name).write_text("# changed")
    elif field == "runtime":
        monkeypatch.setattr(adapter.planner, "runtime_evidence", lambda: {"changed": True})
    else:
        path = adapter.SLOT / "frozen/PREPARED.json"
        data = read(path)
        data["limits"]["wall_seconds"] = 28800
        path.write_text(__import__("json").dumps(data))
    with pytest.raises(ValueError):
        adapter.frozen_start()


def test_actual_plan_comparison_with_only_synthetic_metadata(adapter):
    from test_account_forensics_inputs import synthetic_calendar

    adapter.prepare()
    calendar = synthetic_calendar()
    binding = {"count": 726, "sha256": sha256_json(calendar)}
    parent = {"evidence": {"parent": {"calendar": calendar}}, "spec": {"calendar": binding}}
    folder = adapter.SLOT / "frozen"
    write(folder / "LAUNCH.json", {"plan": parent})
    evidence = {"bindings": {"operation": {"root": str(folder), "files": {
        "LAUNCH.json": file_sha(folder / "LAUNCH.json")}}}}
    write(folder / "FIXTURE.json", {"synthetic_only": True, "parent_sha256": sha256_json(parent),
                                    "input_evidence": evidence})
    original_prepare, original_verify = adapter.planner.prepare_plan, adapter.planner.verify_plan
    adapter.install_boundaries()
    assert adapter.planner.prepare_plan is original_prepare
    assert adapter.planner.verify_plan is original_verify
    plan = adapter.planner.prepare_plan(adapter.ROOT)
    fixture_sha = file_sha(folder / "FIXTURE.json")
    assert adapter.planner.verify_plan(plan, adapter.ROOT) == sha256_json(plan)
    assert adapter.planner.prepare_plan(adapter.ROOT) == plan
    assert file_sha(folder / "FIXTURE.json") == fixture_sha
    assert plan["scope"]["original_producer_commit"] == "SYNTHETIC_PARENT_NOT_A_GIT_COMMIT"
    assert Path(plan["paths"]["claim"]).is_relative_to(adapter.SLOT)
    assert Path(plan["paths"]["operations"]).is_relative_to(adapter.SLOT)
    assert set(plan["input_evidence"]["bindings"]["synthetic_manifest"]["files"]) == {
        "FIXTURE.json", "PREPARED.json"}
    with pytest.raises(ValueError):
        adapter.planner.prepare_plan(adapter.ROOT.parent)
    original_claim = plan["paths"]["claim"]
    plan["paths"]["claim"] = str(adapter.ROOT / "wrong-claim.json")
    with pytest.raises(ValueError):
        adapter.planner.verify_plan(plan, adapter.ROOT)
    plan["paths"]["claim"] = original_claim
    plan["scope"]["new_accounts"] = 1
    with pytest.raises(ValueError):
        adapter.planner.verify_plan(plan, adapter.ROOT)
    (folder / "LAUNCH.json").write_text("{}")
    with pytest.raises(ValueError):
        adapter.planner.prepare_plan(adapter.ROOT)


def test_fixture_factory_never_reuses_or_deletes(adapter):
    adapter.prepare()
    factory = adapter.PersistentFactory()
    root = factory.mktemp("forensic-synthetic")
    sentinel = root / "sentinel"
    sentinel.write_text("preserve")
    with pytest.raises(FileExistsError):
        factory.mktemp("forensic-synthetic")
    with pytest.raises(ValueError):
        factory.mktemp("another")
    assert sentinel.read_text() == "preserve"


def test_consumed_outer_slot_refuses_before_fixture_setup(adapter, monkeypatch):
    adapter.prepare()
    write(adapter.SLOT / "START.json", {"consumed": True})
    calls = []
    monkeypatch.setattr(adapter, "create_fixture", lambda: calls.append("setup"))
    with pytest.raises(FileExistsError):
        adapter.run()
    assert calls == []
    assert read(adapter.SLOT / "START.json") == {"consumed": True}
    assert not (adapter.SLOT / "fixture").exists()
