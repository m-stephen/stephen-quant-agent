import importlib.util
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.workflows.v114_reliable_epoch import write_json


def setup(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "stability_driver", Path("scripts/run_stability_challenge.py")
    )
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    parent, output = tmp_path / "parent", tmp_path / "output"
    parent.mkdir()
    dates = ("2023-01-03", "2023-01-04", "2023-01-05", "2024-01-03", "2024-01-04", "2024-01-05")
    days = tuple(
        ResearchDay(
            dt,
            {},
            (StatefulBar(dt, "S", 10 + i / 10, 10.02 + i / 10, 1e7, dt + "T08:00:00+08:00"),),
        )
        for i, dt in enumerate(dates)
    )
    targets = tuple(TargetAllocation(dt, dt + "T08:00:00+08:00", {"S": 0.02}) for dt in dates)
    write_json(parent / "targets/stable_lowrisk.json", [asdict(t) for t in targets])
    write_json(parent / "targets/lowvol.json", [asdict(t) for t in targets])
    previous = {"raw_global_trial_lower_bound": 3310, "engineering_pass": True, "records": {}}
    for policy in driver.POLICIES:
        previous["records"][policy] = {}
        for cost in (82, 102):
            report = run_stateful_execution(
                tuple(d.bars for d in days),
                targets,
                StatefulExecutionConfig(
                    maximum_position_weight=0.025,
                    commission_bps=6,
                    sell_tax_bps=10,
                    slippage_bps=30 if cost == 82 else 40,
                ),
                initial_nav=3_000_000,
            )
            previous["records"][policy][str(cost)] = {
                "account_sha256": driver.save_account(parent, f"{policy}-{cost}", report)
            }
    write_json(parent / "RESULT.json", previous)
    write_json(parent / "INDEPENDENT_AUDIT.json", {"pass": True})
    for name in ("registry.sqlite3", "first_read_reservations.json", "NATIVE_FIT_LINEAGE.json"):
        (parent / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(driver, "PARENT_SHA", driver.file_sha(parent / "RESULT.json"))
    monkeypatch.setattr(driver, "CARD", tmp_path / "card.json")
    monkeypatch.setattr(driver, "CLAIM_ROOT", tmp_path / "claims")
    write_json(
        driver.CARD,
        {
            "source_result_sha256": driver.PARENT_SHA,
            "runtime_code_sha256": driver.runtime_code_hash(),
            "snapshot_sha256": "a" * 64,
            "targets_file_sha256": {
                p: driver.file_sha(parent / "targets" / (p + ".json")) for p in driver.POLICIES
            },
            "targets_canonical_sha256": {
                p: sha256_json([asdict(t) for t in targets]) for p in driver.POLICIES
            },
        },
    )
    config = tmp_path / "config.json"
    write_json(config, {})
    monkeypatch.setattr(
        driver,
        "verify_lineage",
        lambda c: (tmp_path / "inputs", {"snapshot_sha256": "a" * 64}, [], ()),
    )

    def loader(_):
        with sqlite3.connect(output / "registry.sqlite3") as con:
            assert con.execute("SELECT COUNT(*) FROM trials").fetchone()[0] == 10
            assert (
                con.execute(
                    "SELECT COUNT(*) FROM trial_fit_contracts WHERE stages_json='[]'"
                ).fetchone()[0]
                == 10
            )
        return days, {"synthetic": True}

    monkeypatch.setattr(driver, "load_frozen_days", loader)
    return driver, config, parent, output


def test_complete_synthetic_stress_has_ten_native_contracts_and_exact_replay(tmp_path, monkeypatch):
    driver, config, parent, output = setup(tmp_path, monkeypatch)
    result = driver.run(config, parent, output, 1)
    assert result["completed_new_trials"] == 10
    assert result["raw_global_trial_lower_bound"] == 3320
    assert not result["validated_alpha"] and not result["stress_survived"]
    assert all(not v["increment"] for v in result["checks"].values())
    with pytest.raises(FileExistsError):
        driver.run(config, parent, tmp_path / "second", 1)


def test_changed_targets_are_rejected_before_market_loader(tmp_path, monkeypatch):
    driver, config, parent, output = setup(tmp_path, monkeypatch)
    (parent / "targets/stable_lowrisk.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        driver, "load_frozen_days", lambda _: pytest.fail("must not read market data")
    )
    with pytest.raises(ValueError, match="target bytes"):
        driver.run(config, parent, output, 1)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    assert len(json.loads((output / "first_read_reservations.json").read_text())["trials"]) == 10
