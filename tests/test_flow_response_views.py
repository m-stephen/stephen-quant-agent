import gc
import weakref
from dataclasses import asdict
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.flow_response_predictor import pairs_for_year, ranked_rows
from stephen_quant.discovery.flow_response_storage import freeze
from stephen_quant.discovery.flow_response_views import HistoricalBarMapping, HistoricalSessions
from stephen_quant.discovery.search_power_dsl import sha256_json


def rows(count=48, names=4):
    days = [str(date(2022, 1, 3) + timedelta(days=i)) for i in range(count)]
    bars = {
        d: {
            f"S{n}": asdict(
                StatefulBar(
                    d,
                    f"S{n}",
                    10 + i * 0.1 + n,
                    10 + i * 0.1 + n + 0.05,
                    100000,
                    f"{d}T08:00:00+08:00",
                    True,
                    True,
                    False,
                    "synthetic",
                )
            )
            for n in range(names)
        }
        for i, d in enumerate(days)
    }
    return days, freeze(bars)


def test_replayable_sessions_preserve_values_order_indexing_and_slices():
    days, bars = rows()
    expected = tuple(tuple(StatefulBar(**b) for b in bars[d].values()) for d in days)
    view = HistoricalSessions(bars, days)
    assert view == expected == tuple(view)
    assert tuple(view) == tuple(view)  # Not a consumed generator.
    assert view[0] == expected[0] and view[-1] == expected[-1]
    assert tuple(view[3:8:2]) == expected[3:8:2]
    assert tuple(view[::-1]) == expected[::-1]
    assert HistoricalSessions(bars, []) == ()
    with pytest.raises(IndexError):
        view[len(days)]
    with pytest.raises(TypeError):
        view["wrong"]
    with pytest.raises(ValueError, match="unique"):
        HistoricalSessions(bars, [days[0], days[0]])
    with pytest.raises(ValueError, match="missing"):
        HistoricalSessions(bars, ["2099-01-01"])


def test_prefix_view_never_projects_excluded_numeric_rows(monkeypatch):
    import stephen_quant.discovery.flow_response_views as module

    days, source = rows()
    bars = dict(source)
    bars[days[-1]] = {"POISON": {"unexpected": "must never be passed to StatefulBar"}}
    created = []

    def construct(**values):
        created.append((values["trade_date"], values["instrument"]))
        return StatefulBar(**values)

    monkeypatch.setattr(module, "StatefulBar", construct)
    view = HistoricalBarMapping(bars, days[:-1])
    assert not created
    day = view[days[0]]
    assert not created
    assert day["S1"] == StatefulBar(**bars[days[0]]["S1"])
    assert created == [(days[0], "S1")]
    assert day.get("missing") is None
    with pytest.raises(KeyError):
        view[days[-1]]
    assert len(created) == 1


def test_iteration_does_not_retain_a_second_full_bar_matrix(monkeypatch):
    import stephen_quant.discovery.flow_response_views as module

    days, bars = rows(count=60, names=80)
    live, peaks, creations = weakref.WeakSet(), [], []

    def construct(**values):
        value = StatefulBar(**values)
        live.add(value)
        peaks.append(len(live))
        creations.append(1)
        return value

    monkeypatch.setattr(module, "StatefulBar", construct)
    view = HistoricalSessions(bars, days)
    assert not creations
    for session in view:
        assert len(session) == 80
    del session
    gc.collect()
    assert not live and len(creations) == 60 * 80
    assert max(peaks) <= 160  # Loop may overlap previous and current day.
    assert view._mapping._bars is bars


def test_execution_and_saved_evidence_identical_with_lazy_sessions():
    days, raw = rows(names=4)
    bars = {d: dict(r) for d, r in raw.items()}
    # Missing bars, blocked entry, capacity and delayed recovery stay untouched.
    for d in days[9:34]:
        bars[d].pop("S0")
    bars[days[0]]["S1"] = dict(bars[days[0]]["S1"], can_buy_open=False)
    bars[days[4]]["S2"] = dict(bars[days[4]]["S2"], capacity_cny=30.0)
    targets = tuple(
        TargetAllocation(d, f"{d}T08:00:00+08:00", {"S0": 0.2, "S1": 0.2, "S2": 0.2}, i % 5 == 0)
        for i, d in enumerate(days)
    )
    literal = tuple(tuple(StatefulBar(**b) for b in bars[d].values()) for d in days)
    config = StatefulExecutionConfig(maximum_position_weight=0.25, rebalance_mode="target_changes")
    old = run_stateful_execution(literal, targets, config)
    new = run_stateful_execution(HistoricalSessions(bars, days), targets, config)
    assert new == old
    assert sha256_json(asdict(new)) == sha256_json(asdict(old))


def test_training_pairs_and_evidence_identical_without_full_bar_copy():
    days, raw = rows(count=130, names=80)
    risk = {
        f"S{n}": {
            "volatility_20": 0.01 + n * 0.001,
            "ret_20": 0.02 + n * 0.001,
            "liquidity": 10000000 + n * 10000,
            "flow_ratio": 0.1,
            "close_return": 0.01,
            "flow_surprise": 0.2,
            "standardized_own_return": 0.3,
            "price_response_residual": 0.4,
        }
        for n in range(80)
    }
    features = {d: ranked_rows(risk) for d in days}
    old_bars = {d: {n: StatefulBar(**b) for n, b in raw[d].items()} for d in days}
    expected = pairs_for_year(days, features, old_bars, 2023)
    actual = pairs_for_year(days, features, HistoricalBarMapping(raw, days[:-5]), 2023)
    assert actual == expected
    assert sha256_json(actual) == sha256_json(expected)


def test_unused_flow_rows_released_before_risk_panel(tmp_path, monkeypatch):
    import stephen_quant.discovery.flow_response_history as module

    class FlowRows(list):
        pass

    payload = {"daily": [], "fund_flow": FlowRows(["synthetic"])}
    observed = weakref.ref(payload["fund_flow"])
    monkeypatch.setattr(module, "_preflight", lambda *a, **kw: "a" * 64)
    monkeypatch.setattr(module, "load_response_sources", lambda *a, **kw: (payload, {}))
    monkeypatch.setattr(module, "bridge_source_rows", lambda *a, **kw: ({}, [], {}))

    def panel(*args):
        assert observed() is None
        raise RuntimeError("lifecycle checkpoint reached")

    monkeypatch.setattr(module, "build_response_panel", panel)
    with pytest.raises(RuntimeError, match="lifecycle checkpoint"):
        module.build_history_from_frozen(
            None,
            "provider",
            (),
            input_folder=tmp_path / "input",
            output_folder=tmp_path / "output",
            calendar=[],
            manifest_sha256="a" * 64,
        )
