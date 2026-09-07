from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import StatefulBar
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.discovery.signal_timing import (
    LABELS,
    READOUTS,
    contract,
    day_response,
    endpoints,
    mature_indices,
    memberships,
    plans,
    require_contract,
    response,
    strong_responses,
    summarize,
)


def features(size=240):
    return {
        f"S{i:04}": {
            "volatility_20": (i + 1) / 1000,
            "liquidity": 1e7 * (i % 13 + 1),
            "ret_20": -i,
            "flow_consistency": i,
            "auction_tail_balance": -i,
            "chip_path_efficiency": -i,
        }
        for i in range(size)
    }


def panel(n=50, start="2023-01-01"):
    result = []
    for i in range(n):
        d = (date.fromisoformat(start) + timedelta(days=i)).isoformat()
        result.append(
            ResearchDay(
                d,
                features(1),
                (StatefulBar(d, "S0000", 100 + i, 100.5 + i, 1e6, f"{d}T08:00:00+08:00"),),
            )
        )
    return tuple(result)


def sample(days=None):
    ds = days or panel()
    return {
        **endpoints(ds, [{b.instrument: b for b in d.bars} for d in ds], 0, "S0000"),
        **memberships(ds[0].features)["S0000"],
    }


def test_budget_native_contract_and_scope():
    ps = plans()
    assert len(ps) == len({p["key"] for p in ps}) == 90
    assert contract()["raw_debt_before"] == 3366
    assert not contract()["validated_alpha"]

    class Registry:
        def fit_lineage(self, tid):
            return {"stages": [], "fits": [], "sha256": sha256_json([])}

    require_contract(Registry(), {p["key"]: i for i, p in enumerate(ps)})
    with pytest.raises(ValueError, match="90"):
        require_contract(Registry(), {})

    class Bad:
        def fit_lineage(self, tid):
            return {}

    with pytest.raises(ValueError, match="no-fit"):
        require_contract(Bad(), {p["key"]: i for i, p in enumerate(ps)})


@pytest.mark.parametrize("size", [1, 3, 11, 239, 240, 721])
def test_asof_memberships_conserve_cells_and_sparse_cash(size):
    fs = features(size)
    members = memberships(fs)
    assert set(members) == set(fs)
    assert members == memberships(dict(reversed(list(fs.items()))))
    for group in ("low", "middle", "high"):
        for p in READOUTS:
            total = sum(m[f"w_{p}"] for m in members.values() if m["group"] == group)
            assert 0 <= total <= 1 + 1e-10
        for cell in ("0", "1", "2", "3"):
            ms = [m for m in members.values() if (m["group"], m["cell"]) == (group, cell)]
            if ms:
                assert sum(m["w_cell_equal_weight"] for m in ms) == pytest.approx(0.25)
                for p in READOUTS[:-1]:
                    assert sum(m[f"w_{p}"] > 0 for m in ms) == min(10, len(ms))


@pytest.mark.parametrize(
    "label,start,end",
    [
        ("before_entry", 100.5, 101),
        ("same_day", 101, 101.5),
        ("open_1", 101, 102),
        ("open_5", 101, 106),
        ("open_20", 101, 121),
    ],
)
def test_exact_calendar_endpoints(label, start, end):
    value, valid, entry, stress = response(sample(), label)
    assert value == pytest.approx(end / start - 1)
    assert valid == entry == 1
    assert (stress is None) == (label in LABELS[:2])


def test_overnight_only_planted_gain_is_not_post_entry_profit():
    r = sample()
    r.update(
        signal_close=100,
        entry_open=110,
        entry_close=110,
        exit1_open=110,
        exit5_open=110,
        exit20_open=110,
    )
    assert response(r, "before_entry")[0] == pytest.approx(0.1)
    assert all(response(r, l)[0] == 0 for l in LABELS[1:])


def test_same_day_planted_gain_not_labeled_tplus1_cash():
    r = sample()
    r.update(entry_open=100, entry_close=110, exit1_open=100)
    assert response(r, "same_day")[0] == pytest.approx(0.1)
    assert response(r, "same_day")[3] is None
    assert response(r, "open_1")[0] == 0
    assert contract()["not_tradable"] == ["before_entry", "same_day"]


def test_missing_prices_never_change_selection_or_denominator():
    r = sample()
    before = {k: v for k, v in r.items() if k.startswith("w_")}
    r["entry_open"] = None
    assert response(r, "open_20") == (0, 0, 0, 0)
    rows = day_response([r])
    chosen = next(
        x for x in rows if x["group"] == "low" and x["policy"] == "hash" and x["label"] == "open_20"
    )
    assert chosen["weight"] == 0.025
    assert chosen["valid_weight"] == chosen["gross"] == 0
    assert {k: v for k, v in r.items() if k.startswith("w_")} == before
    r["entry_open"], r["exit20_open"] = 100, None
    assert response(r, "open_20")[3] == -1


def test_exit_sell_limit_is_not_zero_loss_and_entry_block_is_cash():
    r = sample()
    r["exit1_sell"] = 0
    assert response(r, "open_1")[3] == -1
    r["entry_buy"] = 0
    assert response(r, "open_1")[3] == 0


def test_common_maturity_and_no_restricted_calendar():
    ds = panel(40, "2024-11-22")
    assert len(mature_indices(ds)) == 19
    assert all(i + 21 < len(ds) for i in mature_indices(ds))
    with pytest.raises(ValueError, match="restricted"):
        mature_indices(panel(50, "2024-12-01"))
    with pytest.raises(ValueError, match="ordered"):
        mature_indices(tuple(reversed(ds)))


def test_future_features_cannot_change_current_membership():
    ds = panel()
    extended = ds[:1] + tuple(replace(d, features=features(721)) for d in ds[1:])
    assert memberships(ds[0].features) == memberships(extended[0].features)
    assert sample(ds) == sample(extended)


def test_fixed_dates_not_stock_count_weight_annual_mean():
    r = sample()
    r.update(entry_open=100, exit1_open=110)
    a = day_response([r])
    b = day_response([{**r, "date": "2023-01-02", "exit1_open": 90}])
    s = summarize(a + b)
    got = next(x for x in s if (x["group"], x["policy"], x["label"]) == ("low", "hash", "open_1"))
    assert got["dates"] == 2
    assert got["mean_gross"] == pytest.approx(0)
    assert got["mean_weight"] == 0.025
    assert not any(strong_responses(s).values())


def test_response_gate_requires_both_years_each_control_and_coverage():
    rows = [
        {
            "group": "low",
            "policy": p,
            "label": "open_5",
            "year": y,
            "mean_gross": 0.03 if p == "quiet_accumulation" else 0.01,
            "valid_weight": 1,
            "entry_weight": 1,
            "mean_stress": 0.02,
        }
        for p in ("quiet_accumulation", "hash", "price_reversal", "cell_equal_weight")
        for y in ("2023", "2024")
    ]
    key = "low-quiet_accumulation-open_5"
    assert strong_responses(rows)[key]
    rows[1]["valid_weight"] = 0.98
    assert not strong_responses(rows)[key]
    rows[1]["valid_weight"] = 1
    rows[-1]["mean_gross"] = 0.029
    assert not strong_responses(rows)[key]
