import copy
import json
from datetime import date, timedelta

import pytest

from stephen_quant.discovery.flow_response_protocol import (
    BUDGET,
    CONTROLS,
    DEBT,
    candidate_packet,
    check_complete_reservations,
    contract,
    plans,
    reserve_trials,
    screen_records,
)
from stephen_quant.discovery.search_power_dsl import sha256_json


def spec():
    return {
        "calendar": [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(64)]
        + ["2023-01-03", "2023-01-04", "2024-01-02", "2024-01-03"],
        "contract": contract(),
        "plans": plans(),
        "packet": candidate_packet(),
        "manifest_sha256": "a" * 64,
        "anchor_card_sha256": "b" * 64,
        "runtime_code_sha256": "c" * 64,
    }


def test_exact_finite_packet_family_and_native_budget(tmp_path):
    proposal = candidate_packet()
    assert len(proposal["accepted"]) == 2 and not proposal["rejected"]
    assert len({r["keys"]["policy_id"] for r in proposal["accepted"]}) == 2
    assert {r["keys"]["family"] for r in proposal["accepted"]} == {"liquidity_impact_absorption"}
    assert "ridge_rank_score" in proposal["accepted"][0]["recipe"]["expression"]
    assert len(plans()) == BUDGET == 23 and len(CONTROLS) == 9
    assert contract()["actual_supervised_models"] == 14
    assert contract()["supervised_native_bindings"] == 28
    assert contract()["after_full_reservation_debt"] == 3683
    # JSON roundtrip cannot invalidate tuples vs lists in a reproducible config.
    registry, tids = reserve_trials(tmp_path, json.loads(json.dumps(spec())))
    receipt = check_complete_reservations(registry, tids)
    assert receipt["reserved"] == registry.global_trial_count() == 23
    assert receipt["prior_debt"] == DEBT == 3660 and receipt["debt"] == 3683
    with registry.connect() as conn:
        assert conn.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM trial_feature_contracts").fetchone()[0] == 23
        assert (
            conn.execute("SELECT count(*) FROM trials WHERE result_json IS NOT NULL").fetchone()[0]
            == 0
        )
    with pytest.raises(FileExistsError):
        reserve_trials(tmp_path, spec())


@pytest.mark.parametrize("kind", ["budget", "debt", "cost", "packet", "calendar", "tombstone"])
def test_changed_protocol_rejected_before_database_creation(tmp_path, kind):
    value = copy.deepcopy(spec())
    if kind in ("budget", "debt"):
        value["contract"]["budget" if kind == "budget" else "prior_trial_debt"] -= 1
    elif kind == "cost":
        value["plans"][-1]["roundtrip_bps"] = 41
    elif kind == "packet":
        value["packet"]["accepted"].pop()
    elif kind == "calendar":
        value["calendar"] = value["calendar"][:-2]
    else:
        family = value["packet"]["accepted"][0]["keys"]["family_id"]
        value["tombstones"] = {"family_tombstones": [family]}
        value["packet"] = candidate_packet(**value["tombstones"])
    with pytest.raises(ValueError, match="finite"):
        reserve_trials(tmp_path, value)
    assert not (tmp_path / "registry.sqlite3").exists()


def test_pre_read_receipt_rejects_missing_or_completed_trial(tmp_path):
    reg, tids = reserve_trials(tmp_path, spec())
    missing = dict(tids)
    missing.pop("original_stable-164")
    with pytest.raises(ValueError):
        check_complete_reservations(reg, missing)
    reg.record_trial_result(tids["original_lowvol-82"], "{}")
    with pytest.raises(ValueError, match="reservation"):
        check_complete_reservations(reg, tids)


def records():
    result = {}
    for p in plans()[1:]:
        primary = p["role"] == "primary"
        result[p["key"]] = {
            "years": {"2023": 0.12 if primary else 0.03, "2024": 0.14 if primary else 0.04},
            "pooled_sharpe": 1.0,
            "metrics": {"net_total_return": 0.3 if primary else 0.1, "max_drawdown": -0.10},
            "audit": {"pass": True},
        }
    diagnostics = {
        p: [{"date": y + "-02-01", "selected": 40} for y in ("2023", "2024")]
        for p in ("response", "response_interaction")
    }
    return result, diagnostics


def test_every_control_both_costs_and_independent_audit_required():
    rows, diagnostic = records()
    result = screen_records(rows, diagnostic, independent_audit_pass=True)
    assert all(result["screen_survived"].values()) and not result["validated_alpha"]
    no_audit = screen_records(rows, diagnostic, independent_audit_pass=False)
    assert not any(no_audit["screen_survived"].values())
    for control in CONTROLS:
        changed = copy.deepcopy(rows)
        changed[f"{control}-164"]["metrics"]["net_total_return"] = 0.29
        result = screen_records(changed, diagnostic, independent_audit_pass=True)
        assert not any(result["screen_survived"].values())
    diagnostic["response"][0]["selected"] = 37
    result = screen_records(rows, diagnostic, independent_audit_pass=True)
    assert not result["screen_survived"]["response"]
    rows.pop("original_stable-164")
    with pytest.raises(ValueError, match="all22"):
        screen_records(rows, diagnostic, independent_audit_pass=True)


def test_packet_wording_cannot_reset_family_or_policy_identity():
    p = candidate_packet()
    blocked = p["accepted"][0]["keys"]["policy_id"]
    q = candidate_packet(policy_tombstones=(blocked,))
    assert len(q["accepted"]) == len(q["rejected"]) == 1
    assert q["rejected"][0]["reason"] == "tombstone"
    assert p["historical_debt_reset_allowed"] is False
    assert sha256_json(contract()) == sha256_json(json.loads(json.dumps(contract())))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_account_cannot_survive_screen(value):
    rows, diagnostics = records()
    rows["response-82"]["pooled_sharpe"] = value
    with pytest.raises(ValueError, match="finite"):
        screen_records(rows, diagnostics, independent_audit_pass=True)
