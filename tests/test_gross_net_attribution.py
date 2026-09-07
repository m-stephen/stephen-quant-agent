import importlib
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    TargetAllocation,
    run_stateful_execution,
)
from stephen_quant.discovery.gross_net_attribution import (
    DEBT,
    attribution,
    execution_config,
    frozen_targets,
    plans,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def script(name):
    folder = str(Path(__file__).resolve().parents[1] / "scripts")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(name)


def fake_records():
    result = {}
    for p in plans():
        for cost in (0, 82, 164):
            key = p["target_key"] + f"-{cost}"
            a, b = 0.05 + (p["policy"] == "full") * 0.02, 0.06 - cost / 10000
            total = (1 + a) * (1 + b) - 1
            result[key] = {
                "key": key,
                "roundtrip_bps": cost,
                "years": {"2023": a, "2024": b},
                "metrics": {
                    "net_total_return": total,
                    "final_nav": 3e6 * (1 + total),
                    "total_cost": cost * 1000.0,
                },
            }
    return result


def test_exact_twelve_replay_budget_no_new_model_family():
    ps = plans()
    assert len(ps) == len({p["key"] for p in ps}) == 12
    assert DEBT == 3648
    assert all(p["scale"] == p["roundtrip_bps"] == 0 for p in ps)
    assert sum(p["mode"] == "full_target" for p in ps) == 2
    assert all(p["operation_kind"] == "frozen_target_replay" for p in ps)


def test_only_costs_change_in_execution_configuration():
    for p in plans():
        expected = StatefulExecutionConfig(
            maximum_position_weight=0.025,
            commission_bps=6,
            sell_tax_bps=10,
            slippage_bps=30,
            rebalance_mode=p["mode"],
        )
        actual = execution_config(p)
        assert replace(actual, commission_bps=6, sell_tax_bps=10, slippage_bps=30) == expected


def test_reject_unregistered_policy_change():
    p = plans()[0] | {"mode": "full_target"}
    with pytest.raises(ValueError, match="unregistered"):
        execution_config(p)


def test_cost_addback_is_not_zero_cost_replay():
    days = ("2023-01-03", "2023-01-04")
    bars = tuple(
        (StatefulBar(d, "A", op, cp, 1e6, d + "T08:00:00+08:00"),)
        for d, op, cp in zip(days, (10.0, 20.0), (20.0, 30.0), strict=True)
    )
    targets = (
        TargetAllocation(days[0], "2023-01-02T23:00:00+08:00", {"A": 1.0}),
        TargetAllocation(days[1], "2023-01-03T23:00:00+08:00", {"A": 1.0}, False),
    )
    config = StatefulExecutionConfig(
        maximum_position_weight=1, commission_bps=0, sell_tax_bps=0, slippage_bps=0
    )
    zero = run_stateful_execution(bars, targets, config, initial_nav=1000.0)
    paid = run_stateful_execution(
        bars, targets, replace(config, commission_bps=100), initial_nav=1000.0
    )
    assert zero.metrics.final_nav == pytest.approx(3000.0)
    assert abs(zero.metrics.final_nav - paid.metrics.final_nav - paid.metrics.total_cost) > 1
    assert zero.periods[0].marks[0].shares != paid.periods[0].marks[0].shares


def target_rows():
    return [asdict(TargetAllocation("2023-01-03", "2023-01-02T23:59:59+08:00", {"A": 0.025}))]


def test_frozen_target_preserves_every_field():
    rows = target_rows()
    rebuilt = frozen_targets(rows, sha256_json(rows), ["2023-01-03"])
    assert [asdict(t) for t in rebuilt] == rows


@pytest.mark.parametrize("edit", ["weights", "rebalance", "forced_exits", "decided_at"])
def test_target_field_tampering_rejected(edit):
    rows = target_rows()
    digest = sha256_json(rows)
    rows[0][edit] = {
        "weights": {"A": 0.024},
        "rebalance": False,
        "forced_exits": ("A",),
        "decided_at": "2023-01-02T20:00:00+08:00",
    }[edit]
    with pytest.raises(ValueError, match="semantics"):
        frozen_targets(rows, digest, ["2023-01-03"])


@pytest.mark.parametrize("timestamp", ["2023-01-03T09:30:00+08:00", "2023-01-02T23:59:59"])
def test_target_late_or_timezone_free_decision_rejected(timestamp):
    rows = target_rows()
    rows[0]["decided_at"] = timestamp
    with pytest.raises(ValueError, match="precede"):
        frozen_targets(rows, sha256_json(rows), ["2023-01-03"])


@pytest.mark.parametrize("year", [2025, 2026])
def test_restricted_target_year_refused(year):
    rows = target_rows()
    rows[0]["trade_date"] = f"{year}-01-03"
    with pytest.raises(ValueError, match="restricted"):
        frozen_targets(rows, sha256_json(rows), [f"{year}-01-03"])


def test_incomplete_or_duplicate_calendar_refused():
    rows = target_rows()
    with pytest.raises(ValueError, match="calendar"):
        frozen_targets(rows, sha256_json(rows), ["2023-01-04"])
    with pytest.raises(ValueError, match="unique"):
        frozen_targets(rows * 2, sha256_json(rows * 2), ["2023-01-03"] * 2)


def test_factorial_attribution_has_no_promotion_and_independent_reference_matches():
    records = fake_records()
    actual = attribution(records)
    script("audit_gross_net_attribution").compare(
        actual,
        script("audit_gross_net_attribution").reference_differences(records),
        "test reference",
    )
    assert len(actual["path_drag"]) == 24 and len(actual["increments"]) == 42
    assert actual["validated_alpha"] is False
    assert actual["screen_survived"] == {"linear": False, "quadratic": False}
    assert any(abs(r["addback_error"]) > 1e-4 for r in actual["path_drag"])


@pytest.mark.parametrize("fault", ["missing", "extra", "year", "identity", "nan", "compound"])
def test_bad_comparison_panel_rejected(fault):
    rows = fake_records()
    r = rows["linear-full-0"]
    if fault == "missing":
        rows.pop("linear-full-0")
    elif fault == "extra":
        rows["extra"] = deepcopy(r)
    elif fault == "year":
        r["years"] = {"2023": 0.1}
    elif fault == "identity":
        r["key"] = "fake"
    elif fault == "nan":
        r["metrics"]["net_total_return"] = float("nan")
    else:
        r["metrics"]["net_total_return"] += 0.01
    with pytest.raises(ValueError):
        attribution(rows)


def test_exact_twelve_native_no_fit_reservations(tmp_path):
    d = script("run_gross_net_attribution")
    registry, ids = d.reserve(tmp_path, {"plans": plans(), "runtime_code_sha256": "a" * 64})
    assert registry.global_trial_count() == len(ids) == 12
    assert all(
        registry.fit_lineage(tid) == {"stages": [], "fits": [], "sha256": sha256_json([])}
        for tid in ids.values()
    )
    with sqlite3.connect(tmp_path / "registry.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM trial_model_fits").fetchone()[0] == 0


def test_inherited_model_tamper_rejected_before_decoding(tmp_path):
    d = script("run_gross_net_attribution")
    (tmp_path / "models").mkdir()
    (tmp_path / "models/linear-full-2023.json").write_text("{}")
    with pytest.raises(ValueError, match="model bytes"):
        d.inherited_receipt(tmp_path, {"models_sha256": {"linear-full-2023": "0" * 64}})


def test_no_preregistration_rejected_before_source_access(tmp_path):
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"preregistration_comment": True}))
    with pytest.raises(ValueError, match="preregistration"):
        script("run_gross_net_attribution").run(config)


def test_existing_output_and_source_overlap_refused(tmp_path):
    d = script("run_gross_net_attribution")
    with pytest.raises(FileExistsError):
        d.check_output(tmp_path, ())
    with pytest.raises(ValueError, match="independent"):
        d.check_output(tmp_path / "new", (tmp_path,))


def test_claim_and_output_use_exclusive_create(tmp_path):
    from stephen_quant.workflows.v114_reliable_epoch import write_json

    p = tmp_path / "claim.json"
    write_json(p, {"reserved": 12})
    digest = file_sha(p)
    with pytest.raises(FileExistsError):
        write_json(p, {"reserved": 0})
    assert file_sha(p) == digest


def test_native_replay_receipt_tampering_rejected(tmp_path):
    d, auditor = script("run_gross_net_attribution"), script("audit_gross_net_attribution")
    spec = {"plans": plans(), "runtime_code_sha256": "a" * 64}
    registry, ids = d.reserve(tmp_path, spec)
    (tmp_path / "inherited_lineage.json").write_text("{}")
    records = {}
    for p in plans():
        r = {
            "key": p["key"],
            "fit_lineage_sha256": sha256_json([]),
            "inherited_receipt_sha256": file_sha(tmp_path / "inherited_lineage.json"),
        }
        registry.record_trial_result(ids[p["key"]], json.dumps(r))
        records[p["key"]] = r
    result = {"spec": spec, "records": records}
    auditor.native_replays(tmp_path, result)
    (tmp_path / "inherited_lineage.json").write_text('{"changed":true}')
    with pytest.raises(ValueError, match="receipt"):
        auditor.native_replays(tmp_path, result)


@pytest.mark.parametrize("fault", [None, "shares", "open", "missing_open"])
def test_independent_source_open_and_share_continuity(tmp_path, fault):
    import duckdb

    d = script("audit_gross_net_attribution")
    folder = tmp_path / "accounts"
    folder.mkdir()
    rows = [
        {
            "date": "2023-01-03",
            "orders": [{"instrument": "A", "executed_notional": 100.0}],
            "positions": [{"instrument": "A", "shares": 10.0}],
        },
        {
            "date": "2023-01-04",
            "orders": [{"instrument": "A", "executed_notional": -40.0}],
            "positions": [{"instrument": "A", "shares": 8.0}],
        },
    ]
    if fault == "shares":
        rows[1]["positions"][0]["shares"] = 7.0
    (folder / "test.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    with duckdb.connect() as con:
        con.execute("CREATE TABLE valid_bars(date DATE,instrument VARCHAR,op DOUBLE)")
        con.execute("INSERT INTO valid_bars VALUES ('2023-01-03','A',10)")
        if fault != "missing_open":
            con.execute(
                "INSERT INTO valid_bars VALUES ('2023-01-04','A',?)",
                [21 if fault == "open" else 20],
            )
        if fault is None:
            assert d.source_shares(con, tmp_path) == 2
        else:
            with pytest.raises(ValueError):
                d.source_shares(con, tmp_path)


@pytest.mark.parametrize("fault", [None, "promotion", "statistics", "scope", "budget", "mode"])
def test_independent_diagnostic_contract_cannot_promote_or_expand(fault):
    result = {
        "spec": {"plans": plans(), "reserved_trials": 12, "raw_debt_before": 3648},
        "completed_trials": 12,
        "reserved_trials": 12,
        "raw_global_trial_lower_bound": 3660,
        "engineering_pass": True,
        "protected_unchanged": True,
        "restricted_rows_read": 0,
        "validated_alpha": False,
        "screen_survived": {"linear": False, "quadratic": False},
        "statistics": {"dsr": None, "pbo": None, "placebo": None, "status": "NOT_RUN"},
    }
    if fault == "promotion":
        result["validated_alpha"] = True
    elif fault == "statistics":
        result["statistics"]["dsr"] = 0.99
    elif fault == "scope":
        result["restricted_rows_read"] = 1
    elif fault == "budget":
        result["reserved_trials"] = 11
    elif fault == "mode":
        result["spec"]["plans"][0]["mode"] = "full_target"
    if fault is None:
        script("audit_gross_net_attribution").declared_contract(result)
    else:
        with pytest.raises(ValueError):
            script("audit_gross_net_attribution").declared_contract(result)
