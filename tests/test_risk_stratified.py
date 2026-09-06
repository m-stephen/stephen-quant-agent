from dataclasses import replace
from datetime import date, timedelta
from itertools import pairwise

import pytest

from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.risk_stratified import (
    GROUPS,
    MECHANISMS,
    cells,
    contract,
    mechanism_days,
    plans,
    scores,
    screen,
    select,
    targets_for,
)
from stephen_quant.discovery.search_power_dsl import sha256_json


def features(size=720):
    return {
        f"S{i:04d}": {
            "volatility_20": (i + 1) / 1000,
            "liquidity": (1 + (i * 37) % size) * 1e7,
            "ret_20": ((i * 71) % size - size / 2) / size,
            "flow_consistency": (i % 5 - 2) / 2,
            "auction_tail_balance": (i % 7 - 3) / 3,
            "chip_path_efficiency": (i % 11 - 5) / 5,
            "net_inflow_ratio": 0.02 * (i % 5 - 2),
            "auction_return": 0.01 * (i % 7 - 3),
            "concentration": 0.1 + (i % 11) / 100,
        }
        for i in range(size)
    }


def days(count=55, size=240):
    fs = features(size)
    return tuple(
        ResearchDay((date(2023, 1, 1) + timedelta(days=i)).isoformat(), fs, ())
        for i in range(count)
    )


class Registry:
    def fit_lineage(self, tid):
        return {"stages": [], "fits": [], "sha256": sha256_json([])}


def test_budget_and_identity_are_finite_and_all_groups_required():
    rows = plans()
    assert len(rows) == len({r["key"] for r in rows}) == 32
    assert {r["roundtrip_bps"] for r in rows} == {82, 164}
    assert contract()["trial_lower_bound_before"] == 3334
    assert contract()["native_fit_stages"] == []
    assert not contract()["validated_alpha"]


@pytest.mark.parametrize("size", [0, 1, 2, 3, 11, 719, 720, 721])
def test_strata_and_cells_partition_all_names_once(size):
    fs = features(size)
    grouped = cells(fs)
    flattened = [n for group in grouped.values() for bucket in group.values() for n in bucket]
    assert sorted(flattened) == sorted(fs)
    assert len(flattened) == len(set(flattened))
    sizes = [sum(map(len, grouped[g].values())) for g in GROUPS]
    assert max(sizes) - min(sizes) <= 1
    nonempty = [
        [fs[n]["volatility_20"] for bucket in grouped[g].values() for n in bucket] for g in GROUPS
    ]
    nonempty = [v for v in nonempty if v]
    assert all(max(a) <= min(b) for a, b in pairwise(nonempty))
    assert grouped == cells(dict(reversed(list(fs.items()))))


def test_nonfinite_risk_or_mechanism_is_rejected():
    fs = features(3)
    fs["S0000"]["ret_20"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        cells(fs)


def test_joint_scores_economic_directions_and_ties():
    fs = features(4)
    for i, n in enumerate(fs):
        fs[n].update(
            flow_consistency=i, ret_20=-i, chip_path_efficiency=-i, auction_tail_balance=-i
        )
    for policy in MECHANISMS:
        values = scores(fs, list(fs), policy)
        assert values["S0003"] > values["S0000"]
        assert all(0 <= x <= 1 for x in values.values())
    for n in fs:
        fs[n].update(flow_consistency=0, ret_20=0)
    assert len(set(scores(fs, list(fs), "flow_price_absorption").values())) == 1
    assert scores({}, [], "hash") == {}
    with pytest.raises(ValueError, match="unregistered"):
        scores(fs, list(fs), "choose_best_direction")


def test_hash_is_stable_not_refreshed_random_noise():
    fs = features(5)
    before = scores(fs, list(fs), "hash")
    assert before == scores(features(5), list(reversed(fs)), "hash")
    assert len(set(before.values())) == 5


def test_equal_cell_quotas_and_sparse_cash_no_rescaling():
    fs = features()
    for grouped in cells(fs).values():
        for p in (*MECHANISMS, "hash", "price_reversal"):
            chosen, detail = select(fs, grouped, (), p)
            assert len(chosen) == 40
            assert {x["selected"] for x in detail} == {10}
            assert set(chosen) <= {n for ns in grouped.values() for n in ns}
    sparse = cells(features(9))["high"]
    chosen, _ = select(features(9), sparse, (), "hash")
    assert len(chosen) == 3 and len(chosen) * 0.025 < 1


def test_retention_top13_is_applied_to_each_cell_and_removed_names_exit():
    fs = features()
    grouped = cells(fs)["low"]
    previous = []
    for bucket in grouped.values():
        s = scores(fs, bucket, "hash")
        order = sorted(bucket, key=lambda n: (-s[n], n))
        previous.extend(order[3:13])
    chosen, _ = select(fs, grouped, previous, "hash")
    assert set(chosen) == set(previous)
    removed = previous[0]
    new = {k: [n for n in ns if n != removed] for k, ns in grouped.items()}
    chosen, _ = select(fs, new, previous, "hash")
    assert removed not in chosen and len(chosen) == 40
    new["0"] += new["1"][:1]
    with pytest.raises(ValueError, match="disjoint"):
        select(fs, new, previous, "hash")


def test_missing_history_resets_and_all_risk_support_is_kept():
    source = list(days())
    altered = {n: dict(f) for n, f in source[25].features.items()}
    altered["S0000"].pop("net_inflow_ratio")
    source[25] = replace(source[25], features=altered)
    panel, _ = mechanism_days(source)
    assert len(panel[19].features) == 240  # Not old lowest200 truncation.
    assert not panel[18].features
    assert all("S0000" not in panel[i].features for i in range(25, 45))
    assert "S0000" in panel[45].features
    assert panel[25].bars is source[25].bars


def test_prefix_invariance_and_no_future_date_or_label_dependence():
    source = days()
    before, _ = mechanism_days(source)
    after, _ = mechanism_days(source[:40] + tuple(replace(d, features={}) for d in source[40:]))
    assert before[:40] == after[:40]
    a, _ = targets_for(Registry(), 1, before, "middle", "quiet_accumulation", {})
    b, _ = targets_for(Registry(), 1, after, "middle", "quiet_accumulation", {})
    assert a[:41] == b[:41]  # Next-open targets still use the prior session.
    for t in a:
        assert sum(t.weights.values()) <= 1 + 1e-12
        assert all(0 < w <= 0.025 for w in t.weights.values())
    with pytest.raises(ValueError, match="ordered"):
        mechanism_days(source[::-1])


def test_registry_rejection_precedes_feature_read():
    class BadRegistry:
        def fit_lineage(self, tid):
            return {"stages": ["undeclared_model"], "fits": []}

    with pytest.raises(ValueError, match="native no-fit"):
        targets_for(BadRegistry(), 1, days(), "high", "auction_exhaustion", {})


def test_joint_ranks_can_change_real_selection_not_zero_hurdle_swaps():
    fs = features()
    grouped = cells(fs)["middle"]
    a, _ = select(fs, grouped, (), "flow_price_absorption")
    b, _ = select(fs, grouped, (), "hash")
    assert len(set(a) ^ set(b)) >= 10


def test_screen_failures_are_not_tuned_away():
    def row(total=0.5, y2023=0.1):
        return {
            "audit": {"pass": True},
            "years": {"2023": y2023, "2024": 0.2},
            "pooled_sharpe": 1,
            "metrics": {"net_total_return": total, "max_drawdown": -0.15},
        }

    assert all(screen(row(), [row(0.2)]).values())
    assert not screen(row(y2023=-0.001), [row(0.2)])["both_years_positive"]
    assert not screen(row(), [row(0.49)])["total_increment"]
    assert not screen(row(y2023=0.01), [row(0.2)])["annual_increment"]
