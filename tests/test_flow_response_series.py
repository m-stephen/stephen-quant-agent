import copy
import hashlib
import json
import math
import sqlite3
from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.discovery.flow_response_series import (
    DAILY_SUPPORT,
    bind_response_bundle,
    bridge_rows,
    bridge_source_rows,
    clock,
    fit_response_bundle,
    guarded_response_values,
    response_stages,
    validate_bundle,
)
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def source(count=64, names=3):
    calendar = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(count)]
    daily, flow = [], []
    for i, dt in enumerate(calendar):
        for j in range(names):
            asset = f"synthetic-{j}"
            factor = 2 if i >= 30 else 1
            daily.append(
                {
                    "trade_date": dt,
                    "instrument": asset,
                    "close": (10 + 0.01 * i + 0.02 * math.sin(i + j)) / factor,
                    "adjustment_factor": factor,
                    "amount": 100_000.0,
                    "available_at": clock(dt, "17:00:00"),
                }
            )
            flow.append(
                {
                    "trade_date": dt,
                    "instrument": asset,
                    "net_inflow_amount": 100_000_000 * 0.01 * math.sin(i * 0.7 + j),
                    "available_at": clock(dt, "18:00:00"),
                }
            )
    return daily, flow, calendar


def test_bridge_units_split_global_gaps_and_visibility():
    daily, flow, calendar = source()
    observations, excluded = bridge_rows(daily, flow, calendar)
    assert len(excluded) == 3 and not observations[calendar[0]]
    o = observations[calendar[30]]["synthetic-0"]
    assert o.flow_ratio == pytest.approx(0.01 * math.sin(30 * 0.7))
    assert o.close_return == pytest.approx(
        (10 + 0.3 + 0.02 * math.sin(30)) / (10 + 0.29 + 0.02 * math.sin(29)) - 1
    )
    assert o.observed_at == clock(calendar[30], "15:00:00")
    assert o.available_at == clock(calendar[30], "18:00:00")
    daily = [
        r
        for r in daily
        if not (r["trade_date"] == calendar[10] and r["instrument"] == "synthetic-0")
    ]
    flow = [
        r
        for r in flow
        if not (r["trade_date"] == calendar[10] and r["instrument"] == "synthetic-0")
    ]
    obs, gaps = bridge_rows(daily, flow, calendar)
    assert "synthetic-0" not in obs[calendar[11]]
    assert "synthetic-0" in obs[calendar[12]]
    assert any(
        r["date"] == calendar[11] and r["reason"] == "missing_previous_global_close" for r in gaps
    )


@pytest.mark.parametrize(
    "kind", ["duplicate_daily", "duplicate_flow", "orphan", "future_date", "naive"]
)
def test_bridge_source_contract_rejection(kind):
    daily, flow, calendar = source()
    if kind == "duplicate_daily":
        daily.append(daily[5])
    elif kind == "duplicate_flow":
        flow.append(flow[5])
    elif kind == "orphan":
        flow[5] = flow[5] | {"instrument": "unknown"}
    elif kind == "future_date":
        daily[5] = daily[5] | {"trade_date": "2026-01-01", "close": "poison"}
    else:
        daily[5] = daily[5] | {"available_at": "2022-01-02T17:00:00"}
    with pytest.raises(ValueError):
        bridge_rows(daily, flow, calendar)
    if kind != "orphan":
        with pytest.raises(ValueError):
            bridge_source_rows(daily, flow, calendar, support_policy=DAILY_SUPPORT)


def test_explicit_support_records_exact_keys_without_inspecting_orphan_values():
    daily, flow, days = source(80)
    baseline, _ = bridge_rows(daily, flow, days)
    # No available_at or numeric fields: key exclusion must not access them.
    flow.append({"trade_date": days[20], "instrument": "orphan"})
    result, exclusions, support = bridge_source_rows(
        list(reversed(daily)), list(reversed(flow)), days, support_policy=DAILY_SUPPORT
    )
    assert result == baseline
    assert exclusions[0] == {
        "date": days[20],
        "asset": "orphan",
        "reason": "flow_without_same_date_daily",
    }
    expected_hash = hashlib.sha256(f'["{days[20]}","orphan"]\n'.encode()).hexdigest()
    assert support["identity_sha256"]["flow_only"] == expected_hash
    assert support["counts"] == {
        "daily": 240,
        "fund_flow": 241,
        "common": 240,
        "daily_only": 0,
        "flow_only": 1,
    }
    assert support["flow_key_coverage"] == 240 / 241
    assert support["daily_key_coverage"] == 1.0
    again = bridge_source_rows(daily, flow, days, support_policy=DAILY_SUPPORT)
    assert again == (result, exclusions, support)
    with pytest.raises(ValueError, match="without a daily"):
        bridge_rows(daily, flow, days)


def test_support_gaps_reset_global_adjacency_and_do_not_use_future_presence():
    daily, flow, days = source(80)
    daily = [
        r for r in daily if not (r["trade_date"] == days[20] and r["instrument"] == "synthetic-0")
    ]
    flow = [
        r for r in flow if not (r["trade_date"] == days[30] and r["instrument"] == "synthetic-1")
    ]
    obs, _, support = bridge_source_rows(daily, flow, days, support_policy=DAILY_SUPPORT)
    assert list(obs) == days
    assert "synthetic-0" in obs[days[19]]  # Later absence must not filter past eligibility.
    assert "synthetic-0" not in obs[days[20]] and "synthetic-0" not in obs[days[21]]
    assert "synthetic-0" in obs[days[22]]
    assert "synthetic-1" not in obs[days[30]] and "synthetic-1" in obs[days[31]]
    model = fit_response_bundle(obs, days, 61, "a" * 64)
    assert set(model["models"]) == {"synthetic-2"}  # No compressed60-row fit across either gap.
    assert support["counts"]["flow_only"] == support["counts"]["daily_only"] == 1


@pytest.mark.parametrize("kind", ["duplicate", "calendar", "key", "policy"])
def test_explicit_support_does_not_relax_key_gates(kind):
    daily, flow, days = source()
    orphan = {"trade_date": days[3], "instrument": "orphan"}
    flow.append(orphan)
    if kind == "duplicate":
        flow.append(orphan)
    elif kind == "calendar":
        orphan["trade_date"] = "2026-01-01"
    elif kind == "key":
        orphan["instrument"] = " "
    with pytest.raises(ValueError):
        bridge_source_rows(
            daily, flow, days, support_policy="guess" if kind == "policy" else DAILY_SUPPORT
        )


@pytest.mark.parametrize("kind", ["daily", "flow"])
def test_unavailable_numerics_are_not_inspected(kind):
    daily, flow, calendar = source()
    if kind == "daily":
        daily[-1] = daily[-1] | {"available_at": "2023-01-01T17:00:00+08:00", "close": "poison"}
    else:
        flow[-1] = flow[-1] | {
            "available_at": "2023-01-01T17:00:00+08:00",
            "net_inflow_amount": "poison",
        }
    obs, excluded = bridge_rows(daily, flow, calendar)
    assert "synthetic-2" not in obs[calendar[-1]]
    assert excluded[-1]["reason"] == (
        "daily_not_available" if kind == "daily" else "flow_not_available"
    )


def test_bundle_prefix_invariance_real_observation_dates_and_exclusions():
    daily, flow, calendar = source(80)
    observations, _ = bridge_rows(daily, flow, calendar)
    before = fit_response_bundle(observations, calendar, 61, "a" * 64)
    mutated = copy.deepcopy(observations)
    for dt in calendar[61:]:
        mutated[dt] = {"not-a-real-row": object()}
    assert fit_response_bundle(mutated, calendar, 61, "a" * 64) == before
    assert fit_response_bundle(observations, calendar[:64], 61, "a" * 64) == before
    assert validate_bundle(before) == validate_bundle(copy.deepcopy(before))
    assert before["training_observation_sessions"] == calendar[1:61]
    assert before["training_observation_dates"] == 60 and before["model_count"] == 3
    assert "maximum_label_end" not in before and "training_signal_sessions" not in before
    observations[calendar[10]].pop("synthetic-1")
    after = fit_response_bundle(observations, calendar, 61, "a" * 64)
    assert after["excluded"] == {"synthetic-1": "missing_global_session"}
    assert after["model_count"] == 2
    assert set(before["models"]) == set(after["models"]) | set(after["excluded"])


def test_zero_identifiable_models_do_not_create_fake_native_fit():
    daily, flow, calendar = source()
    observations, _ = bridge_rows(daily, flow, calendar)
    observations[calendar[10]] = {}
    with pytest.raises(ValueError, match="no identifiable"):
        fit_response_bundle(observations, calendar, 61, "a" * 64)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 1e308])
def test_flow_denominator_quality_exclusions(value):
    daily, flow, calendar = source()
    daily[-1]["amount"] = value
    obs, excluded = bridge_rows(daily, flow, calendar)
    assert "synthetic-2" not in obs[calendar[-1]]
    assert excluded[-1]["reason"] == "invalid_flow_denominator"


@pytest.fixture
def native(tmp_path):
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    snapshot = build_composite_snapshot_manifest({"synthetic": "a" * 64})
    sid = registry.register_snapshot(snapshot)
    eid = registry.create_experiment(ExperimentSpec("response", "synthetic", sid, "synthetic-code"))
    daily, flow, calendar = source()
    spec = TrialSpec(
        eid,
        "response-provider",
        "liquidity-impact",
        "{}",
        184,
        calendar[0],
        calendar[-1],
        calendar[61],
        calendar[-1],
        "unused",
        "unused",
        fit_stages=response_stages(calendar),
    )
    provider, _ = registry.create_trial(spec)
    registry.declare_feature_sources(provider, ())
    consumers = []
    for name in ("cost82", "cost164"):
        tid, _ = registry.create_trial(replace(spec, model_name=name, fit_stages=()))
        registry.declare_feature_sources(tid, (provider,))
        consumers.append(tid)
    observations, _ = bridge_rows(daily, flow, calendar)
    return registry, spec, provider, consumers, observations, calendar, snapshot.snapshot_sha256


def complete_provider(native, tmp_path, result_override=None):
    registry, _, provider, _, obs, calendar, snapshot = native
    bundles = []
    for i in (61, 62):
        bundle = fit_response_bundle(obs, calendar, i, snapshot)
        path = tmp_path / f"bundle-{i}.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        bind_response_bundle(registry, provider, bundle, path)
        bundles.append((bundle, path))
    lineage = registry.fit_lineage(provider)
    result = {"feature_provider_ready": True, "native_fit_lineage_sha256": lineage["sha256"]}
    registry.record_trial_result(
        provider, json.dumps(result if result_override is None else result_override)
    )
    return bundles


def test_native_shared_fit_consumers_and_same_current_support(native, tmp_path):
    registry, _, provider, consumers, obs, calendar, _ = native
    for consumer in consumers:
        with pytest.raises(ValueError, match="incomplete native feature"):
            registry.record_trial_result(consumer, "{}")
    bundles = complete_provider(native, tmp_path)
    for consumer in consumers:
        evidence = registry.bind_feature_source(consumer, provider)
        assert evidence == registry.bind_feature_source(consumer, provider)
        assert evidence["fit_stage_count"] == 2
    bundle, path = bundles[0]
    current = obs[calendar[61]]
    outputs = [
        guarded_response_values(registry, tid, provider, bundle, path, current) for tid in consumers
    ]
    assert outputs[0] == outputs[1] and len(outputs[0]) == 3
    assert guarded_response_values(registry, consumers[0], provider, bundle, path, {}) == {}
    for consumer in consumers:
        registry.record_trial_result(consumer, "{}")
        assert registry.feature_sources(consumer)["providers"] == [provider]
    with registry.connect() as conn:
        assert conn.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM trial_feature_bindings").fetchone()[0] == 2
    assert (
        registry.global_trial_count() == 3
    )  # One synthetic provider + two consumers, not repeated fits.


def test_missing_bind_fails_before_current_values_are_read(native, tmp_path):
    registry, _, provider, consumers, _, _, _ = native
    bundle, path = complete_provider(native, tmp_path)[0]

    class Poison:
        def keys(self):
            raise AssertionError("must not inspect current features")

    with pytest.raises(ValueError, match="incomplete native feature"):
        guarded_response_values(registry, consumers[0], provider, bundle, path, Poison())


@pytest.mark.parametrize(
    "mutation", ["snapshot", "model_asset", "model_date", "count", "invented_labels"]
)
def test_bundle_and_native_guards(native, tmp_path, mutation):
    registry, _, provider, _, obs, calendar, snapshot = native
    bundle = fit_response_bundle(obs, calendar, 61, snapshot)
    if mutation == "snapshot":
        bundle["snapshot_sha256"] = "b" * 64
    elif mutation == "model_asset":
        bundle["models"]["synthetic-0"]["asset"] = "other"
    elif mutation == "model_date":
        bundle["models"]["synthetic-0"]["prediction_session"] = 99
    elif mutation == "count":
        bundle["model_count"] += 1
    else:
        bundle["maximum_label_end"] = calendar[60]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(ValueError):
        bind_response_bundle(registry, provider, bundle, path)


@pytest.mark.parametrize(
    "result", [{"failed": True}, {"feature_provider_ready": True, "native_fit_lineage_sha256": "x"}]
)
def test_failed_or_misbound_provider_outcome_not_consumable(native, tmp_path, result):
    registry, _, provider, consumers, _, _, _ = native
    complete_provider(native, tmp_path, result)
    with pytest.raises(ValueError, match="provider outcome"):
        registry.bind_feature_source(consumers[0], provider)


def test_declarations_precede_fit_and_do_not_rebind(native, tmp_path):
    registry, spec, provider, consumers, _, _, _ = native
    with pytest.raises(ValueError, match="collision"):
        registry.declare_feature_sources(consumers[0], ())
    complete_provider(native, tmp_path)
    late, _ = registry.create_trial(replace(spec, fit_stages=()))
    with pytest.raises(ValueError, match="unfitted"):
        registry.declare_feature_sources(late, (provider,))
    with pytest.raises(ValueError, match="explicit native"):
        registry.feature_sources(late)


def test_invalid_provider_graph_and_legacy_compatibility(native):
    registry, spec, provider, consumers, _, _, _ = native
    other_eid = registry.create_experiment(
        ExperimentSpec(
            "other", "synthetic", registry.experiment_snapshot_id(spec.experiment_id), "other-code"
        )
    )
    foreign, _ = registry.create_trial(replace(spec, experiment_id=other_eid))
    registry.declare_feature_sources(foreign, ())
    fresh, _ = registry.create_trial(replace(spec, fit_stages=()))
    for bad in ((foreign,), (fresh,), (consumers[0],), (provider, provider)):
        with pytest.raises(ValueError):
            registry.declare_feature_sources(fresh, bad)
    registry.record_trial_result(fresh, "{}")  # Legacy path still works, but isn't called verified.
    with pytest.raises(ValueError, match="explicit native"):
        registry.feature_sources(fresh)
    with pytest.raises(ValueError, match="precede consumer"):
        registry.declare_feature_sources(fresh, ())


@pytest.mark.parametrize("mutation", ["file", "model", "calendar"])
def test_runtime_bundle_mutation_is_rejected(native, tmp_path, mutation):
    registry, _, provider, consumers, obs, calendar, _ = native
    bundle, path = complete_provider(native, tmp_path)[0]
    registry.bind_feature_source(consumers[0], provider)
    if mutation == "file":
        altered = copy.deepcopy(bundle)
        altered["models"]["synthetic-0"]["slope"] *= 0.5
        path.write_text(json.dumps(altered), encoding="utf-8")
    elif mutation == "model":
        bundle["models"]["synthetic-0"]["slope"] *= 0.5
    else:
        bundle["calendar_window_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        guarded_response_values(registry, consumers[0], provider, bundle, path, obs[calendar[61]])


def test_bound_provider_outcome_tampering_detected(native, tmp_path):
    registry, _, provider, consumers, _, _, _ = native
    complete_provider(native, tmp_path)
    registry.bind_feature_source(consumers[0], provider)
    with registry.connect() as conn:
        conn.execute(
            "UPDATE trials SET result_json=? WHERE trial_id=?", ('{"failed":true}', provider)
        )
    with pytest.raises(ValueError, match="provider outcome"):
        registry.feature_sources(consumers[0])


@pytest.mark.parametrize("table", ["trial_feature_contracts", "trial_feature_bindings"])
@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_feature_lineage_is_append_only(native, tmp_path, table, action):
    registry, _, provider, consumers, _, _, _ = native
    complete_provider(native, tmp_path)
    registry.bind_feature_source(consumers[0], provider)
    sql = f"DELETE FROM {table}" if action == "DELETE" else f"UPDATE {table} SET trial_id=trial_id"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"), registry.connect() as conn:
        conn.execute(sql)
