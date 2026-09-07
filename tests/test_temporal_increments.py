import json
import random
import sqlite3
from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.temporal_increments import (
    HURDLE,
    MECHANISMS,
    fit_year,
    path_values,
    plans,
    select,
    temporal_days,
)
from stephen_quant.workflows import v1111_temporal_epoch as workflow


def fixture_days(years=(2022, 2023, 2024), count=210, size=60):
    rng = random.Random(1111)
    result = []
    for year in years:
        for i in range(count):
            dt = (date(year, 1, 3) + timedelta(days=i)).isoformat()
            fs, bars = {}, []
            for j in range(size):
                n = f"S{j:03d}"
                fs[n] = {
                    "volatility_20": (j + 1) / size,
                    "ret_20": rng.uniform(-0.2, 0.2),
                    "liquidity": 1e7 + rng.uniform(0, 1e7),
                    "net_inflow_ratio": rng.uniform(-1, 1),
                    "auction_return": rng.uniform(-0.1, 0.1),
                    "concentration": 0.1 + rng.random(),
                }
                price = 10 + i * (j + 1) / 10000
                bars.append(StatefulBar(dt, n, price, price, 1e7, f"{dt}T08:00:00+08:00"))
            result.append(ResearchDay(dt, fs, tuple(bars)))
    return tuple(result)


def test_path_formulas_are_shape_not_renamed_averages():
    positive = path_values([(1, 1, i) for i in range(20)])
    assert positive == dict(zip(MECHANISMS, (1, 1, 1), strict=True))
    reverse = path_values([(-1, -1, 20 - i) for i in range(20)])
    assert reverse == dict(zip(MECHANISMS, (-1, -1, -1), strict=True))
    assert path_values([(0, 0, 1)] * 20) == dict.fromkeys(MECHANISMS, 0)
    # Same flow mean, different directional consistency; not a renaming of mean(flow).
    uneven = path_values([(20, 0, 1)] + [(0, 0, 1)] * 19)
    assert uneven[MECHANISMS[0]] == pytest.approx(0.05)
    with pytest.raises(ValueError, match="twenty"):
        path_values([(1, 2, 3)] * 19)


def test_pool_is_current_lowrisk_and_missing_resets_rolling_history():
    days = fixture_days((2022,), count=60, size=205)
    altered = list(days)
    fs = {n: dict(f) for n, f in days[30].features.items()}
    fs["S000"].pop("net_inflow_ratio")
    altered[30] = replace(days[30], features=fs)
    panel, coverage = temporal_days(tuple(altered))
    assert not panel[18].features
    assert len(panel[19].features) == 200
    assert "S204" not in panel[19].features
    assert all("S000" not in panel[i].features for i in range(30, 50))
    assert "S000" in panel[50].features
    assert coverage[19]["common"] == 205
    assert panel[19].bars == days[19].bars  # No survivorship filtering of execution/exit bars.


def test_future_mutation_preserves_transforms_and_training():
    days = fixture_days((2022, 2023))
    panel, _ = temporal_days(days)
    changed, _ = temporal_days(
        tuple(replace(d, features={}) if d.date >= "2023-01-01" else d for d in days)
    )
    assert panel[:210] == changed[:210]
    assert fit_year(panel, 2023, {}) == fit_year(changed, 2023, {})
    model = fit_year(panel, 2023, {})
    assert model["maximum_label_end"] <= model["fit_cutoff"] < "2023-01-01"


def test_new_selector_retains_base_for_null_and_requires_original_hurdle():
    rows = {
        f"S{i:03d}": {"x": [1, 0, 0, 0], "vol": i / 100, "z": {m: i / 100 for m in MECHANISMS}}
        for i in range(100)
    }
    base, _ = select(rows, (), "stable_lowrisk")
    assert len(base) == 40
    zero = {"slope": 0.0, "nuisance_z": [0] * 4}
    assert select(rows, base, MECHANISMS[0], zero) == (base, 0)
    weak = {**zero, "slope": HURDLE / 2}
    assert select(rows, base, MECHANISMS[0], weak) == (base, 0)
    selected, swaps = select(rows, base, MECHANISMS[0], {**zero, "slope": 0.2})
    assert swaps > 0 and len(selected) == 40


def setup_run(tmp_path, monkeypatch, loader):
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}")
    output = tmp_path / "operation"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output_dir": str(output), "preregistration_comment": 1}))
    monkeypatch.setattr(
        workflow,
        "verify_lineage",
        lambda c: (
            tmp_path / "source",
            {"snapshot_sha256": "a" * 64},
            [evidence],
            (tmp_path / "parent",),
        ),
    )
    monkeypatch.setattr(workflow, "CLAIM_ROOT", tmp_path / "claims")
    monkeypatch.setattr(workflow, "load_frozen_days", loader)
    return config, output


def test_native_all_reservations_before_source_read_and_no_reentry(tmp_path, monkeypatch):
    def fail(_):
        with sqlite3.connect(tmp_path / "operation" / "registry.sqlite3") as conn:
            assert conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0] == 21
            assert conn.execute("SELECT COUNT(*) FROM trial_fit_contracts").fetchone()[0] == 21
            assert conn.execute("SELECT COUNT(*) FROM trial_model_fits").fetchone()[0] == 0
        raise ValueError("synthetic failure after reservation")

    config, output = setup_run(tmp_path, monkeypatch, fail)
    with pytest.raises(ValueError, match="synthetic failure"):
        workflow.run(config)
    assert json.loads((output / "ABORTED.json").read_text())["reservations_preserved"]
    config.write_text(
        json.dumps({"output_dir": str(tmp_path / "repeat"), "preregistration_comment": 1})
    )
    with pytest.raises(FileExistsError):
        workflow.run(config)
    assert not (tmp_path / "repeat").exists()


def test_entire_synthetic_epoch_uses_native_fit_path(tmp_path, monkeypatch):
    config, output = setup_run(
        tmp_path, monkeypatch, lambda _: (fixture_days(), {"synthetic": True})
    )
    result = workflow.run(config)
    assert result["engineering_pass"] and not result["validated_alpha"]
    assert result["completed_new_trials"] == result["reserved_new_trials"] == len(plans()) == 21
    assert result["raw_global_trial_lower_bound"] == 3310
    with sqlite3.connect(output / "registry.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM trial_model_fits").fetchone()[0] == 24
        assert (
            conn.execute("SELECT COUNT(*) FROM trials WHERE result_json IS NOT NULL").fetchone()[0]
            == 21
        )
    bindings = json.loads((output / "NATIVE_FIT_LINEAGE.json").read_text())
    assert len(bindings) == 21
    assert sum(len(v["fits"]) for v in bindings.values()) == 24
    assert len(list((output / "accounts").glob("*.jsonl"))) == 15
