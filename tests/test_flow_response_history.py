import copy
import json
from dataclasses import replace
from datetime import date, timedelta

import duckdb
import numpy as np
import pytest

from stephen_quant.discovery.flow_response_accounts import execute_response_account, history_targets
from stephen_quant.discovery.flow_response_history import (
    VERSION,
    build_history_from_frozen,
    fit_history_predictor,
    read_verified_history,
)
from stephen_quant.discovery.flow_response_predictor import POLICIES, ranked_rows, stages
from stephen_quant.discovery.flow_response_series import response_stages
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.qmt.flow_response_inputs import load_response_sources
from stephen_quant.qmt.reliable_panel import file_sha


def frozen_sources(root):
    # Explicit SYNTHETIC weekday calendar, not a claim about exchange holidays.
    days = [
        str(date(2022, 1, 3) + timedelta(days=i))
        for i in range(365 + 55)
        if (date(2022, 1, 3) + timedelta(days=i)).weekday() < 5
    ]
    root.mkdir()
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE days(i INTEGER, d DATE)")
    conn.executemany("INSERT INTO days VALUES(?,?)", list(enumerate(days)))
    conn.execute("""CREATE TABLE daily AS SELECT d AS trade_date,
        lpad(CAST(600000+j AS VARCHAR),6,'0') instrument,
        CASE WHEN d=DATE '2023-01-02' THEN '*ST Synthetic' ELSE 'Synthetic' END AS name,
        10*exp(.0001*i+(.004+j*.00001)*sin(.7*i+j)) AS open,
        10*exp(.0001*i+(.006+j*.00002)*sin(.7*i+j)) AS close,
        100000+j*1000+1000*cos(i*.3+j) AS amount, 10000.0 AS volume,
        1.0 AS adjustment_factor,
        CAST(CAST(d AS VARCHAR)||'T17:00:00+08:00' AS TIMESTAMPTZ) available_at
        FROM days CROSS JOIN range(80) n(j)""")
    conn.execute("""CREATE TABLE fund_flow AS SELECT trade_date,instrument,
        1000000*sin(i*.37+CAST(instrument AS INTEGER)) AS net_inflow_amount,
        CAST(CAST(d AS VARCHAR)||'T18:00:00+08:00' AS TIMESTAMPTZ) available_at
        FROM daily JOIN days ON trade_date=d""")
    sources = []
    for name in ("daily", "fund_flow"):
        path = root / (name + ".parquet")
        conn.execute(f"COPY {name} TO ? (FORMAT PARQUET)", [str(path)])
        sources.append(
            {
                "source": name,
                "file": path.name,
                "sha256": file_sha(path),
                "rows": len(days) * 80,
                "min_date": days[0],
                "max_date": days[-1],
                "authorized_start": "2022-01-01",
                "authorized_end": "2024-12-31",
            }
        )
    conn.close()
    sources += [
        {"source": n, "file": n + ".parquet", "sha256": "a" * 64, "rows": 0}
        for n in ("auction", "chip", "minute")
    ]
    manifest = {
        "sources": sources,
        "snapshot_sha256": sha256_json(sources),
        "exposed_sealed_rows": 0,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return days, manifest["snapshot_sha256"]


@pytest.fixture(scope="module")
def integrated(tmp_path_factory):
    root = tmp_path_factory.mktemp("response-history")
    days, manifest = frozen_sources(root / "inputs")
    registry = ExperimentRegistry(root / "registry.sqlite3")
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest({"response_inputs": manifest})
    )
    eid = registry.create_experiment(
        ExperimentSpec("integration", "synthetic only", sid, "synthetic-code")
    )
    params = {
        "response_history_version": VERSION,
        "response_manifest_sha256": manifest,
        "response_calendar_sha256": sha256_json(days),
    }
    spec = TrialSpec(
        eid,
        "provider",
        "liquidity_impact_absorption",
        json.dumps(params),
        184,
        "2022-01-01",
        "2022-12-31",
        "2023-01-01",
        "2023-12-31",
        "unused",
        "unused",
        fit_stages=response_stages(days),
    )
    provider, _ = registry.create_trial(spec)
    registry.declare_feature_sources(provider, ())
    consumers = {}
    for policy in POLICIES + ("hash", "lowvol"):
        tid, _ = registry.create_trial(
            replace(
                spec,
                model_name=policy,
                hyperparams=json.dumps(params | {"response_policy": policy}),
                fit_stages=stages()[:1] if policy in POLICIES else (),
            )
        )
        registry.declare_feature_sources(tid, (provider,))
        consumers[policy] = tid
    path = build_history_from_frozen(
        registry,
        provider,
        tuple(consumers.values()),
        input_folder=root / "inputs",
        output_folder=root / "history",
        calendar=days,
        manifest_sha256=manifest,
    )
    models, paths = {}, {}
    for policy in POLICIES:
        paths[policy] = root / f"predictor-{policy}.json"
        models[policy] = fit_history_predictor(
            registry,
            consumers[policy],
            provider,
            history_path=path,
            year=2023,
            policy=policy,
            model_path=paths[policy],
        )
    return root, registry, provider, consumers, days, manifest, path, models, paths


def test_integrated_source_native_feature_matrix_and_same_training_support(integrated):
    root, reg, provider, consumers, days, manifest, path, models, _ = integrated
    h, evidence = read_verified_history(reg, consumers["response"], path)
    assert reg.global_trial_count() == 10  # Synthetic fixture only; no empirical reservation.
    assert len(reg.fit_lineage(provider)["fits"]) == len(days) - 62
    assert len({m["training_rows_sha256"] for m in models.values()}) == 1
    assert all(
        m["training_provenance"]["history_artifact_sha256"] == file_sha(path)
        for m in models.values()
    )
    assert models["response"]["training_signal_dates"] >= 30
    assert models["response"]["maximum_label_end"] < "2023-01-01"
    assert evidence["history_artifact_sha256"] == file_sha(path)
    assert h["source_evidence"]["sealed_numeric_rows_read"] == 0
    assert h["source_evidence"]["warmup_numeric_rows_read"] == 0
    assert not h["ranks"][days[60]] and len(h["ranks"][days[61]]) == 80
    assert not (root / "inputs" / "auction.parquet").exists()
    assert h["source_evidence"]["parent_snapshot_sha256"] == manifest


def test_independent_raw_source_to_historical_response_and_rank_recomputation(integrated):
    root, reg, _, consumers, days, manifest, path, _, _ = integrated
    history, _ = read_verified_history(reg, consumers["response"], path)
    source, _ = load_response_sources(
        root / "inputs", expected_manifest_sha256=manifest, calendar=days
    )
    daily = {(r["trade_date"], r["instrument"]): r for r in source["daily"]}
    flow = {(r["trade_date"], r["instrument"]): r for r in source["fund_flow"]}
    # Separate NumPy computation does not call bridge, fit_response or response_features.
    for i in (61, 140, 255):
        features = {}
        for name in history["ranks"][days[i]]:
            x, y = [], []
            for j in range(i - 60, i + 1):
                r, previous = daily[days[j], name], daily[days[j - 1], name]
                x.append(flow[days[j], name]["net_inflow_amount"] / (r["amount"] * 1000))
                y.append(r["close"] / previous["close"] - 1)
            x, y = np.asarray(x), np.asarray(y)
            mx, my, sx, sy = np.mean(x[:-1]), np.mean(y[:-1]), np.std(x[:-1]), np.std(y[:-1])
            slope = np.mean((x[:-1] - mx) / sx * (y[:-1] - my) / sy) / 1.01
            zx, zy = (x[-1] - mx) / sx, (y[-1] - my) / sy
            p = np.asarray([daily[d, name]["close"] for d in days[i - 20 : i + 1]])
            features[name] = {
                "volatility_20": float(np.std(np.log(p[1:] / p[:-1]), ddof=1)),
                "ret_20": float(p[-1] / p[0] - 1),
                "liquidity": float(
                    np.mean([daily[d, name]["amount"] * 1000 for d in days[i - 59 : i + 1]])
                ),
                "flow_ratio": float(x[-1]),
                "close_return": float(y[-1]),
                "flow_surprise": float(zx),
                "standardized_own_return": float(zy),
                "price_response_residual": float(zy - slope * zx),
            }
        expected = ranked_rows(features)
        actual = history["ranks"][days[i]]
        assert expected.keys() == actual.keys()
        for name in expected:
            assert expected[name]["cell"] == actual[name]["cell"]
            assert expected[name]["ranks"] == actual[name]["ranks"]
            assert expected[name]["vol"] == pytest.approx(actual[name]["vol"])


def test_all_policies_reach_fixed_accounts_with_cash_and_costs(integrated):
    _, reg, _, consumers, days, _, path, models, paths = integrated
    training_hashes = {p: file_sha(f) for p, f in paths.items()}
    for policy, tid in consumers.items():
        targets, coverage, sessions = history_targets(
            reg,
            tid,
            history_path=path,
            policy=policy,
            models={2023: models[policy]} if policy in models else None,
            paths={2023: paths[policy]} if policy in paths else None,
        )
        assert len(targets) == sum(d >= "2023-01-01" for d in days)
        assert all(
            row["selected"] == (0 if row["date"] == "2023-01-02" else 40) for row in coverage
        )
        assert all(t.decided_at[:10] < t.trade_date for t in targets if t.rebalance)
        assert sum(targets[1].weights.values()) == 0  # Empty current eligibility -> cash.
        assert sum(targets[16].weights.values()) == pytest.approx(0.75)
        assert sum(targets[21].weights.values()) == pytest.approx(1.0)
        standard = execute_response_account(sessions, targets, roundtrip_bps=82)
        stress = execute_response_account(sessions, targets, roundtrip_bps=164)
        assert standard.metrics.initial_nav == stress.metrics.initial_nav == 3_000_000
        assert all(p.end_nav > 0 and p.cash >= -1e-6 for p in standard.periods)
        assert any(p.orders for p in standard.periods)
        for account, multiplier in ((standard, 2), (stress, 4)):
            for period in account.periods:
                assert period.end_nav == pytest.approx(
                    period.cash + sum(m.market_value for m in period.marks)
                )
                assert period.net_return == pytest.approx(period.end_nav / period.previous_nav - 1)
                for order in period.orders:
                    bps = (23 if order.executed_notional < 0 else 18) * multiplier
                    assert order.total_cost == pytest.approx(
                        abs(order.executed_notional) * bps / 10000
                    )
    assert training_hashes == {p: file_sha(f) for p, f in paths.items()}


@pytest.mark.parametrize("kind", ["history", "bundle", "model"])
def test_runtime_tampering_is_rejected_without_replacing_native_hash(integrated, kind):
    root, reg, _, consumers, days, _, path, models, paths = integrated
    target = (
        path
        if kind == "history"
        else (path.parent / f"response-{days[61]}.json" if kind == "bundle" else paths["response"])
    )
    original = target.read_bytes()
    try:
        obj = json.loads(original)
        if kind == "history":
            obj["ranks"][days[65]]["600000"]["ranks"]["flow_surprise"] = 0.999
        elif kind == "bundle":
            obj["models"]["600000"]["slope"] = 0.123
        else:
            obj["weights"][0] += 10
        target.write_text(json.dumps(obj), encoding="utf-8")
        with pytest.raises(ValueError):
            history_targets(
                reg,
                consumers["response"],
                history_path=path,
                policy="response",
                models={2023: models["response"]},
                paths={2023: paths["response"]},
            )
    finally:
        target.write_bytes(original)
    assert root.exists()


def test_replay_and_wrong_policy_fail_before_source_or_matrix_read(integrated, monkeypatch):
    root, reg, provider, consumers, days, manifest, path, _, _ = integrated

    def poison(*args, **kwargs):
        raise AssertionError("must not read numerical source or history")

    monkeypatch.setattr(
        "stephen_quant.discovery.flow_response_history.load_response_sources", poison
    )
    monkeypatch.setattr(
        "stephen_quant.discovery.flow_response_history.read_verified_history", poison
    )
    with pytest.raises(ValueError, match="uncompleted"):
        build_history_from_frozen(
            reg,
            provider,
            tuple(consumers.values()),
            input_folder=root / "inputs",
            output_folder=root / "duplicate",
            calendar=days,
            manifest_sha256=manifest,
        )
    assert not (root / "duplicate").exists()
    with pytest.raises(ValueError, match="predeclared"):
        fit_history_predictor(
            reg,
            consumers["response"],
            provider,
            history_path=path,
            year=2024,
            policy="response",
            model_path=root / "wrong-year.json",
        )


def test_unbound_matrix_and_nonfrozen_cost_cannot_execute(integrated):
    _, reg, _, consumers, _, _, path, models, paths = integrated
    model = copy.deepcopy(models["response"])
    model["training_provenance"]["history_artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="historical matrix"):
        history_targets(
            reg,
            consumers["response"],
            history_path=path,
            policy="response",
            models={2023: model},
            paths={2023: paths["response"]},
        )
    with pytest.raises(ValueError, match="predeclared"):
        history_targets(reg, consumers["response"], history_path=path, policy="lowvol")
    for cost in (0, 41, 80, 82.0):
        with pytest.raises(ValueError, match="frozen"):
            execute_response_account((), (), roundtrip_bps=cost)


@pytest.mark.parametrize(
    "kind", ["manifest", "calendar", "snapshot", "consumer", "overlap", "exists"]
)
def test_source_preflight_rejects_before_reader_or_directory_mutation(tmp_path, monkeypatch, kind):
    days = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(64)]
    manifest = "a" * 64
    registry = ExperimentRegistry(tmp_path / "native.sqlite3")
    sid = registry.register_snapshot(
        build_composite_snapshot_manifest(
            {
                "response_inputs": "b" * 64 if kind == "snapshot" else manifest,
            }
        )
    )
    eid = registry.create_experiment(ExperimentSpec("preflight", "synthetic", sid, "test"))
    params = {
        "response_history_version": VERSION,
        "response_manifest_sha256": "b" * 64 if kind == "manifest" else manifest,
        "response_calendar_sha256": "b" * 64 if kind == "calendar" else sha256_json(days),
    }
    spec = TrialSpec(
        eid,
        "provider",
        "response",
        json.dumps(params),
        184,
        days[0],
        days[-1],
        "2023-01-01",
        "2023-12-31",
        "unused",
        "unused",
        fit_stages=response_stages(days),
    )
    provider, _ = registry.create_trial(spec)
    registry.declare_feature_sources(provider, ())
    consumer, _ = registry.create_trial(replace(spec, model_name="consumer", fit_stages=()))
    if kind != "consumer":
        registry.declare_feature_sources(consumer, (provider,))

    def poison(*args, **kwargs):
        raise AssertionError("unauthorized numerical reader called")

    monkeypatch.setattr(
        "stephen_quant.discovery.flow_response_history.load_response_sources", poison
    )
    output = tmp_path / "output"
    if kind == "exists":
        output.mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        build_history_from_frozen(
            registry,
            provider,
            (consumer,),
            input_folder=output if kind == "overlap" else tmp_path / "source",
            output_folder=output,
            calendar=days,
            manifest_sha256=manifest,
        )
    assert output.exists() == (kind == "exists")
