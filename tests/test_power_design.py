from dataclasses import replace

import numpy as np
import pytest

from stephen_quant.discovery.power_design import runner
from stephen_quant.discovery.power_design.contracts import LENGTHS, PowerSpec
from stephen_quant.discovery.power_design.measurement import (
    ar_mean_variance,
    matrix_hac,
    measurement_suite,
)
from stephen_quant.discovery.power_design.sources import generate
from stephen_quant.discovery.research_reset.contracts import SCENARIOS, ResetSpec, digest
from stephen_quant.discovery.research_reset.runner import read_json, write_new
from stephen_quant.discovery.research_reset.search import discover
from stephen_quant.discovery.research_reset.statistics import hac_mean
from stephen_quant.integrity.registry import ExperimentRegistry


@pytest.mark.parametrize("scene", SCENARIOS)
@pytest.mark.parametrize("length", (360, 720))
def test_all_source_prefixes_are_exactly_equal(scene, length):
    short, oracle = generate(314159, scene, PowerSpec())
    long, other = generate(314159, scene, PowerSpec(sessions=100 + length))
    assert short.dates == long.dates[:220]
    assert oracle.expression == other.expression
    for name in ("features", "available", "opening", "closing", "can_buy", "can_sell", "capacity"):
        np.testing.assert_array_equal(getattr(short, name), getattr(long, name)[:220])
    np.testing.assert_array_equal(oracle.signal, other.signal[:220])


@pytest.mark.parametrize(
    "key,value",
    [
        ("active_t_min", 2.0),
        ("active_mean_min", 0.0),
        ("sessions", 1000),
        ("strength_multiplier", 2.0),
        ("real_label_authorized", True),
        ("hac_lag", 20),
        ("historical_raw_attempts", 0),
        ("max_structures", 50),
        ("capital_cny", 20000000),
    ],
)
def test_frozen_scope_cannot_change(key, value):
    with pytest.raises(ValueError):
        replace(PowerSpec(), **{key: value}).validate()


def test_v12_original_contract_stays_frozen():
    with pytest.raises(ValueError):
        replace(ResetSpec(), sessions=820).validate()


@pytest.mark.parametrize("lag", (0, 1, 10, 30))
def test_hac_nonzero_lags_match_independent_matrix(lag):
    x = np.random.default_rng(51).normal(size=120)
    for i in range(1, len(x)):
        x[i] += 0.8 * x[i - 1]
    actual, expected = hac_mean(x, lag), matrix_hac(x, lag)
    for key in ("mean", "se", "t"):
        assert actual[key] == pytest.approx(expected[key], abs=1e-12)


def test_ar_mean_variance_is_finite_sample_not_asymptotic():
    assert ar_mean_variance(120, 0) == pytest.approx(1 / 120)
    assert ar_mean_variance(2, 0.8) == pytest.approx(0.9)
    assert ar_mean_variance(120, 0.8) < (1 + 0.8) / (1 - 0.8) / 120


def test_measurement_reports_uncertainty_without_automatic_certification():
    result = measurement_suite(20)
    assert result["numerical_status"] == "PASS"
    assert len(result["rows"]) == 9
    assert "coverage" in result["meaning"]
    assert all(row["independent_replications"] == 20 for row in result["rows"])


def test_long_tail_is_validated_not_only_first220():
    panel, _ = generate(91, "linear", PowerSpec(sessions=820))
    invalid = panel.closing.copy()
    invalid[-1, 0] = np.nan
    with pytest.raises(ValueError):
        replace(panel, closing=invalid).validate()


def test_net_train_never_reads_or_uses_future_tail():
    spec = PowerSpec()
    panel, _ = generate(123, "linear", spec)
    _, ranks, support, ranked = discover(panel, spec, lambda *a: None)
    expected = runner.net_training_rank(panel, ranked, ranks, support, spec, lambda *a: None)
    opening, closing, features = panel.opening.copy(), panel.closing.copy(), panel.features.copy()
    opening[96:] *= 100
    closing[96:] *= 0.01
    features[96:] *= -10
    changed = replace(panel, opening=opening, closing=closing, features=features)
    _, changed_ranks, changed_support, changed_ranked = discover(changed, spec, lambda *a: None)
    actual = runner.net_training_rank(
        changed, changed_ranked, changed_ranks, changed_support, spec, lambda *a: None
    )
    assert [(c.structure_id, value) for c, value, _ in expected] == [
        (c.structure_id, value) for c, value, _ in actual
    ]
    for _, _, evidence in actual:
        for account in evidence["accounts"].values():
            for role in account["accounts"].values():
                assert len(role["daily"]) == 95
                assert role["daily"][-1][0] == panel.dates[95]


def fake_development(*, eligible_length=360):
    results = []
    for length in LENGTHS:
        for multiplier in (1.0, 0.5):
            for scene in SCENARIOS if multiplier == 1.0 else SCENARIOS[:2]:
                for seed in range(8):
                    passed = not scene.endswith("null") and length >= eligible_length
                    results.append(
                        {
                            "scenario": scene,
                            "seed": seed,
                            "spec": PowerSpec(
                                sessions=100 + length, strength_multiplier=multiplier
                            ).payload(),
                            "promoted": passed,
                            "recovery": {"semantic": True},
                            "oracle_reference": {"passes_same_economic_gate": passed},
                            "net_diagnostic": {"promoted": False},
                            "paired": {"164:risk_only": {"paired": {"mean": 0.001}}},
                        }
                    )
    return results


def test_length_selection_is_predeclared_and_net_not_a_policy_selector():
    results = fake_development()
    summary = runner.summarize_development(results)
    assert len(results) == 144
    assert summary["selected_length"] == 360
    assert summary["cross_cell_independence"] is False
    for r in results:
        r["net_diagnostic"]["promoted"] = True
    assert runner.summarize_development(results)["selected_length"] == 360
    assert (
        runner.summarize_development(fake_development(eligible_length=1000))["selected_length"]
        is None
    )


def test_missing_or_duplicate_development_seed_rejected():
    results = fake_development()
    results[0]["seed"] = results[1]["seed"]
    with pytest.raises(ValueError):
        runner.summarize_development(results)


def test_native_path_trials_accounts_and_source_reconcile(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    registry.initialize()
    value, h = runner.run_path(
        730, "linear", PowerSpec(), tmp_path / "one", "b" * 64, registry, net_diagnostic=True
    )
    assert h == digest(read_json(tmp_path / "one" / "RESULT.json"))
    assert value["counts"]["structures"] == 48
    assert value["counts"]["account_runs"] == 30  # 12 primary +12 train +4 net eval +2 oracle
    assert value["counts"]["native_trials"] == 78
    assert registry.counts()["trials"] == 78
    assert len(set(value["native_trial_ids"])) == 78
    assert value["counts"]["empirical_trials"] == 0


def test_suite_preparation_is_once_only_and_audit_requires_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "root_control", lambda: tmp_path / "control")
    path = runner.prepare("development")
    assert read_json(path)["plan"]["real_labels"] is False
    with pytest.raises(FileExistsError):
        runner.prepare("development")
    with pytest.raises(ValueError):
        runner.prepare("audit")


def test_plan_mutation_is_rejected_before_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "root_control", lambda: tmp_path / "control")
    path = runner.prepare("development")
    envelope = read_json(path)
    envelope["plan"]["code"] = {}
    altered = tmp_path / "altered.json"
    write_new(altered, envelope)
    with pytest.raises(ValueError):
        runner.run(altered, tmp_path / "output")
    assert not (tmp_path / "control" / "claims").exists()


def test_failure_retains_consumed_suite_and_trials(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "root_control", lambda: tmp_path / "control")
    monkeypatch.setattr(runner, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(runner, "measurement_suite", lambda: {"numerical_status": "PASS"})

    def fail(*args, **kwargs):
        raise RuntimeError("injected synthetic engine failure")

    monkeypatch.setattr(runner, "run_path", fail)
    path = runner.prepare("development")
    out = tmp_path / "artifacts" / "failed"
    with pytest.raises(RuntimeError):
        runner.run(path, out)
    assert read_json(out / "TERMINAL.json")["status"] == "ENGINEERING_FAIL"
    with pytest.raises(FileExistsError):
        runner.run(path, tmp_path / "artifacts" / "retry")
