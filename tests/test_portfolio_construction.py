"""Pure synthetic construction tests; no real source/return/Trial execution."""

import copy
import hashlib
from types import MappingProxyType

import pytest

from stephen_quant.discovery.flow_response_predictor import INPUTS
from stephen_quant.discovery.pairwise_ranking import select
from stephen_quant.discovery.portfolio_construction import contract, select_global


def rows(n=100):
    return {
        f"S{i:03d}": {"cell": 20 * i // n, "ranks": dict.fromkeys(INPUTS, 0.0), "vol": i / 1000}
        for i in range(n)
    }


def test_diagnostic_contract_is_finite_not_alpha_or_actual_reservation():
    c = contract()
    assert c["budget"] == len(c["accounts"]) == 4
    assert c["prior_trial_lower_bound"] == 3729
    assert c["projected_after_reservation"] == 3733
    assert c["new_fits"] == 0
    assert c["primary_alpha_candidates"] == []
    assert not c["validated_alpha"] and not c["automatic_retry"]
    assert {p["roundtrip_bps"] for p in c["accounts"]} == {82, 164}
    assert c["statistics"]["status"] == "NOT_RUN_DIAGNOSTIC"
    c["accounts"].clear()
    assert len(contract()["accounts"]) == 4


def test_global_lowvol_is_not_volatility_cell_allocation():
    r = rows(200)
    global_names = select_global(r, "global_lowvol")
    cell_names = select(r, {n: -v["vol"] for n, v in r.items()}, ())
    assert len(global_names) == len(cell_names) == 40
    assert global_names == tuple(sorted(r)[:40])
    assert len({r[n]["cell"] for n in cell_names}) == 20
    assert len({r[n]["cell"] for n in global_names}) == 4


def test_retains_only_current_top60_and_fills_from_current_top_rank():
    r = rows()
    old = tuple(f"S{i:03d}" for i in range(30, 70))
    expected = tuple(
        sorted([f"S{i:03d}" for i in range(30, 60)] + [f"S{i:03d}" for i in range(10)])
    )
    assert select_global(r, "global_lowvol", old) == expected
    assert "S059" in expected and "S060" not in expected


def test_no_current_support_means_cash_not_future_or_previous_fill():
    assert select_global({}, "global_lowvol", ("outside",)) == ()
    r = rows(17)
    assert select_global(r, "global_lowvol", ("outside",)) == tuple(sorted(r))


def test_hash_reuses_exact_parent_seed_and_is_order_independent():
    r = rows()
    expected = tuple(
        sorted(
            sorted(
                r,
                key=lambda n: hashlib.sha256(f"v11.21:184:{n}".encode()).hexdigest(),
                reverse=True,
            )[:40]
        )
    )
    assert select_global(r, "global_hash") == expected
    assert select_global(dict(reversed(list(r.items()))), "global_hash") == expected
    assert select_global(r, "global_hash", expected) == expected


def test_inputs_unmodified_and_ties_have_deterministic_identity_order():
    r = rows()
    for v in r.values():
        v["vol"] = 0.1
    before = copy.deepcopy(r)
    assert select_global(r, "global_lowvol") == tuple(sorted(r)[:40])
    assert before == r


@pytest.mark.parametrize("broken", [float("nan"), float("inf"), -0.1, True, "0.1"])
def test_invalid_volatility_rejected_without_silent_support_drop(broken):
    r = rows()
    r["S000"]["vol"] = broken
    with pytest.raises(ValueError, match="common support"):
        select_global(r, "global_lowvol")


@pytest.mark.parametrize("bad_rank", [float("nan"), 2.0, True])
def test_unused_but_required_feature_invalid_rejects_even_hash(bad_rank):
    r = rows()
    r["S000"]["ranks"][INPUTS[-1]] = bad_rank
    with pytest.raises(ValueError, match="common support"):
        select_global(r, "global_hash")


def test_missing_feature_rejects_even_though_lowvol_does_not_use_it():
    r = rows()
    r["S000"]["ranks"].pop(INPUTS[-1])
    with pytest.raises(ValueError, match="common support"):
        select_global(r, "global_lowvol")


@pytest.mark.parametrize("policy", ["response", "risk", "hash", "global_lowvol-82"])
def test_no_hidden_model_direction_or_cost_variants(policy):
    with pytest.raises(ValueError, match="fixed no-fit"):
        select_global(rows(), policy)


def test_duplicate_previous_names_rejected():
    with pytest.raises(ValueError, match="unique previous"):
        select_global(rows(), "global_hash", ("S001", "S001"))


def test_accepts_immutable_common_support_without_copying_history():
    r = MappingProxyType(rows())
    assert select_global(r, "global_lowvol") == tuple(sorted(r)[:40])


def test_list_is_not_an_explicit_identity_mapping():
    with pytest.raises(TypeError, match="mapping"):
        select_global([], "global_hash")
