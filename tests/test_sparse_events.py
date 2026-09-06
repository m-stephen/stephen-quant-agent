import math
from dataclasses import replace
from datetime import date, timedelta
from statistics import mean, stdev

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    run_stateful_execution,
)
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.sparse_events import (
    POLICIES,
    catalog,
    contract,
    innovation_days,
    plans,
    require_contract,
    risk_cells,
    schedules,
    screen,
)


def panel(count=100, size=240, start=date(2023, 1, 1)):
    return tuple(
        ResearchDay(
            (start + timedelta(days=i)).isoformat(),
            {
                f"S{j:04d}": {
                    "volatility_20": 0.1 + j / 10000,
                    "liquidity": 1e8 + j * 1e6,
                    "ret_20": 0.01,
                    "flow": 1.0,
                    "flow_z": 0.0,
                    "price_z": 1.5,
                }
                for j in range(size)
            },
            (),
        )
        for i in range(count)
    )


def event(days, i, names=("S0000",), lag=1):
    for n in names:
        days[i - lag].features[n].update(flow_z=3.0)
        days[i].features[n].update(price_z=0.0)


def test_exact_bounded_catalog_and_no_fit():
    assert len(catalog()) == len({a["sha256"] for a in catalog()}) == 8
    assert len(plans()) == len({p["key"] for p in plans()}) == 50
    assert contract()["raw_debt_before"] + len(plans()) == 3506
    assert contract()["native_fit_stages"] == []
    assert not contract()["validated_alpha"]


def test_native_contract_before_values():
    class Registry:
        def fit_lineage(self, tid):
            return {"stages": [], "fits": [], "sha256": sha256_json([])}

    r = Registry()
    ids = {p["key"]: str(i) for i, p in enumerate(plans())}
    require_contract(r, ids)
    with pytest.raises(ValueError, match="all50"):
        require_contract(r, {k: "same" for k in ids})
    with pytest.raises(ValueError, match="all50"):
        require_contract(r, dict(list(ids.items())[:-1]))
    r.fit_lineage = lambda tid: {"stages": ["scaler"], "fits": []}
    with pytest.raises(ValueError, match="no-fit"):
        require_contract(r, ids)


@pytest.mark.parametrize("size", [0, 1, 3, 11, 12, 13, 240, 721])
def test_cells_disjoint_deterministic_and_no_aux_source_requirement(size):
    f = panel(1, size)[0].features
    cells = risk_cells(f)
    assert set(cells) == set(f)
    assert cells == risk_cells(dict(reversed(list(f.items()))))
    assert len(set(cells.values())) <= 12


def raw_panel(count=80):
    result, close = [], 10.0
    for i in range(count):
        dt = (date(2022, 1, 1) + timedelta(days=i)).isoformat()
        close *= 1 + 0.01 * math.sin(i)
        bar = StatefulBar(dt, "S0000", close, close, 1e7, dt + "T08:00:00+08:00")
        f = {
            "net_inflow_ratio": math.cos(i),
            "volatility_20": 0.1,
            "ret_20": 0.01,
            "liquidity": 1e8,
        }
        result.append(ResearchDay(dt, {"S0000": f}, (bar,)))
    return result


def test_innovations_use_previous20_not_current_and_are_prefix_invariant():
    days, evidence = raw_panel(), []
    converted = innovation_days(days, evidence.append)
    assert not converted[20].features and "S0000" in converted[21].features
    rows = {r["index"]: r for r in evidence}
    prior = [rows[i] for i in range(1, 21)]
    current = rows[21]
    assert current["flow_z"] == pytest.approx(
        (current["flow"] - mean(r["flow"] for r in prior)) / stdev(r["flow"] for r in prior)
    )
    assert current["price_z"] == pytest.approx(
        current["price_return"] / stdev(r["price_return"] for r in prior)
    )
    assert innovation_days(days[:45]) == converted[:45]
    assert converted[25].bars is days[25].bars


@pytest.mark.parametrize("missing", ["flow", "bar", "risk", "all"])
def test_missing_global_observation_resets_history(missing):
    days = raw_panel()
    if missing == "flow":
        days[30].features["S0000"].pop("net_inflow_ratio")
    elif missing == "risk":
        days[30].features["S0000"].pop("liquidity")
    elif missing == "bar":
        days[30] = replace(days[30], bars=())
    else:
        days[30] = replace(days[30], features={})
    converted = innovation_days(days)
    resume = 52 if missing == "bar" else 51
    assert all(not converted[i].features for i in range(30, resume))
    assert converted[resume].features


@pytest.mark.parametrize("kind", ["flow", "price"])
def test_zero_variance_no_event(kind):
    days = raw_panel()
    for i, d in enumerate(days):
        if kind == "flow":
            d.features["S0000"]["net_inflow_ratio"] = 1.0
        else:
            days[i] = replace(d, bars=(replace(d.bars[0], open_price=10.0, close_price=10.0),))
    assert all(not d.features for d in innovation_days(days))


@pytest.mark.parametrize("lag", [1, 3])
def test_sequence_lag_next_open_twenty_session_expiry_and_cash(lag):
    days = panel(65)
    event(days, 5, lag=lag)
    ast = next(
        a
        for a in catalog()
        if a["lag"] == lag
        and a["start"] == "positive_flow_innovation"
        and a["confirm"] == "quiet_positive_flow"
    )
    targets, admissions, counts = schedules(days, ast)
    assert len(admissions) == 1 and admissions[0]["signal_index"] == 5
    assert admissions[0]["entry_index"] == 6 and admissions[0]["expiry_index"] == 26
    primary = targets["event"]
    assert not primary[5].weights
    assert all(primary[i].weights == {"S0000": 0.025} for i in range(6, 26))
    assert not primary[26].weights
    assert counts[5]["admissions"] == 1
    assert targets["confirm_only"][6].weights == {}  # no same-cell confirm alternatives
    assert sum(targets["risk_hash"][6].weights.values()) == 0.025


def test_first_hit_cooldown_and_no_extension():
    days = panel(100)
    for i in (5, 7, 26, 44, 45, 47):
        event(days, i)
    # consecutive hit at44/45 is not a new edge even when cooldown expires.
    days[44].features["S0000"]["flow_z"] = 3
    t, admissions, _ = schedules(days, catalog()[0])
    assert [r["signal_index"] for r in admissions] == [5, 47]
    assert not t["event"][26].weights


def test_full_slots_rejected_trigger_is_consumed_no_deferred_recycling():
    days = panel(100)
    first = tuple(f"S{j:04d}" for j in range(40))
    event(days, 5, first)
    event(days, 8, ("S0040",))
    event(days, 30, ("S0040",))
    event(days, 50, ("S0040",))
    log = []
    t, admissions, _ = schedules(days, catalog()[0], log.append)
    assert len(t["event"][6].weights) == 40
    assert [(r["signal_index"], r["event"]) for r in admissions if r["event"] == "S0040"] == [
        (50, "S0040")
    ]
    assert next(r for r in log if r["index"] == 8)["admitted"] is False


def test_same_date_control_matching_excludes_events_and_own_names():
    days = panel(70)
    event(days, 5, ("S0000", "S0001"))
    for j in range(2, 15):
        days[5].features[f"S{j:04d}"]["price_z"] = 0
    t, admissions, _ = schedules(days, catalog()[0])
    assert len(admissions) == 2
    cells = risk_cells(days[5].features)
    for policy in POLICIES[1:]:
        chosen = [r[policy] for r in admissions]
        assert len(set(chosen)) == 2
        assert not set(chosen) & {"S0000", "S0001"}
        assert all(cells[r[policy]] == r["cell"] for r in admissions)
        assert all(sum(t[policy][i].weights.values()) == 0.05 for i in range(6, 26))
        assert not t[policy][26].weights


def test_schedule_prefix_invariance_and_no_year_reset():
    days = panel(100, start=date(2023, 12, 1))
    event(days, 22)
    t, admissions, _ = schedules(days, catalog()[0])
    prefix, _, _ = schedules(days[:70], catalog()[0])
    assert all(prefix[p] == t[p][:70] for p in POLICIES)
    assert t["event"][35].weights == {"S0000": 0.025}
    assert admissions[0]["expiry_index"] == 43


def test_warmup_is_not_a_trade_and_last_signal_cannot_enter_past_end():
    days = panel(45, start=date(2022, 12, 20))
    event(days, 5)
    event(days, 44)
    t, a, _ = schedules(days, catalog()[0])
    assert not a and all(not row.weights for row in t["event"])
    assert t["event"][0].trade_date == "2023-01-01"


def test_target_execution_is_next_open_with_cash_and_fixed_planned_expiry():
    days = list(panel(45, 12))
    event(days, 5)
    for i, d in enumerate(days):
        days[i] = replace(
            d,
            bars=tuple(
                StatefulBar(
                    d.date,
                    n,
                    10.0,
                    10.0,
                    1e7,
                    d.date + "T08:00:00+08:00",
                )
                for n in d.features
            ),
        )
    t, _, _ = schedules(days, catalog()[0])
    report = run_stateful_execution(
        tuple(d.bars for d in days),
        t["event"],
        StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=6,
            sell_tax_bps=10,
            slippage_bps=30,
            rebalance_mode="target_changes",
        ),
        initial_nav=3e6,
    )
    executed = [
        (d.trade_date, o.executed_notional)
        for d in report.periods
        for o in d.orders
        if abs(o.executed_notional) > 1e-8
    ]
    assert executed[0][0] == days[6].date and executed[0][1] > 0
    assert executed[-1][0] == days[26].date and executed[-1][1] < 0
    assert min(d.cash / d.end_nav for d in report.periods) > 0.97
    assert report.periods[-1].end_nav < 3e6


def test_screen_requires_bothyears_matching_and_all_controls():
    a = {
        "audit": {"pass": True},
        "years": {"2023": 0.1, "2024": 0.1},
        "pooled_sharpe": 1.0,
        "metrics": {"max_drawdown": -0.1, "net_total_return": 0.21},
    }
    c = {**a, "metrics": {**a["metrics"], "net_total_return": 0.15}}
    counts = [
        {"year": y, "admissions": 50, "risk_hash": 50, "confirm_only": 49} for y in ("2023", "2024")
    ]
    assert all(screen(a, [c, c, c], counts).values())
    counts[0]["confirm_only"] = 48
    assert not screen(a, [c, c, c], counts)["matching"]
    counts[0]["admissions"] = 49
    assert not screen(a, [c, c, c], counts)["admissions"]


@pytest.mark.parametrize("kind", ["future", "unordered", "empty", "ast"])
def test_fail_closed(kind):
    days, ast = panel(3), catalog()[0]
    if kind == "future":
        days = panel(3, start=date(2025, 1, 1))
    elif kind == "unordered":
        days = tuple(reversed(days))
    elif kind == "empty":
        days = ()
    else:
        ast = {**ast, "lag": 2}
    with pytest.raises(ValueError):
        schedules(days, ast)
