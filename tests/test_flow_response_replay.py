import json
from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest
from test_flow_response_protocol import spec

from stephen_quant.baseline.stateful import StatefulBar, TargetAllocation
from stephen_quant.discovery.flow_response_accounts import execute_response_account
from stephen_quant.discovery.flow_response_protocol import reserve_trials
from stephen_quant.discovery.flow_response_replay import (
    audit_response_account,
    load_original_targets,
)
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.qmt.reliable_panel import file_sha


def account():
    days = [str(date(2023, 1, 2) + timedelta(days=i)) for i in range(26)]
    sessions, targets = [], []
    for i, d in enumerate(days):
        bars = [StatefulBar(d, "B", 1.0, 1.0, 1e6, d + "T08:00:00+08:00")]
        if i < 2 or i >= 23:
            bars.append(
                StatefulBar(
                    d,
                    "A",
                    10.0 if i < 23 else 8.0,
                    10.0 if i < 23 else 8.0,
                    1e6,
                    d + "T08:00:00+08:00",
                    True,
                    True,
                )
            )
        sessions.append(tuple(bars))
        targets.append(
            TargetAllocation(
                d, d + "T08:00:00+08:00", {"A": 0.025} if i == 0 else {}, i in (0, 2, 23)
            )
        )
    sessions, targets = tuple(sessions), tuple(targets)
    report = execute_response_account(sessions, targets, roundtrip_bps=82)
    return sessions, targets, report


def test_independent_fill_cash_stale_writeoff_and_recovery_reconstruction():
    sessions, targets, report = account()
    result = audit_response_account(report, sessions, targets, roundtrip_bps=82)
    assert result["pass"] and result["executed_tickets"] == 2
    assert result["final_nav"] == report.metrics.final_nav
    assert report.metrics.writeoff_events == report.metrics.recovery_events == 1
    assert not result["independent_source_and_target_selection"]


@pytest.mark.parametrize(
    "kind",
    [
        "cash",
        "fill",
        "mark",
        "stale",
        "cost",
        "limit",
        "capacity",
        "date",
        "config",
        "intent",
        "omitted_order",
        "target",
        "overnight",
        "turnover",
        "writeoff_summary",
        "recovery_summary",
        "period_summary",
        "mark_source",
    ],
)
def test_independent_account_detects_corruption(kind):
    sessions, targets, report = account()
    periods = list(report.periods)
    if kind == "cash":
        periods[0] = replace(periods[0], cash=periods[0].cash + 100)
    elif kind in ("fill", "cost"):
        orders = list(periods[0].orders)
        orders[0] = replace(
            orders[0],
            **(
                {"executed_notional": orders[0].executed_notional + 100}
                if kind == "fill"
                else {"total_cost": 0.0}
            ),
        )
        periods[0] = replace(periods[0], orders=tuple(orders))
    elif kind in ("mark", "stale", "mark_source"):
        marks = list(periods[3].marks)
        marks[0] = replace(
            marks[0],
            **(
                {"mark_price": 1.0}
                if kind == "mark"
                else {"source": "current_close"}
                if kind == "mark_source"
                else {"stale_sessions": 0}
            ),
        )
        periods[3] = replace(periods[3], marks=tuple(marks))
    elif kind in ("limit", "capacity"):
        bars = list(sessions[0])
        bars[1] = replace(
            bars[1], **({"can_buy_open": False} if kind == "limit" else {"capacity_cny": 0.0})
        )
        sessions = (tuple(bars),) + sessions[1:]
    elif kind == "date":
        targets = (replace(targets[0], decided_at="2023-01-03T08:00:00+08:00"),) + targets[1:]
    elif kind == "intent":
        orders = list(periods[0].orders)
        orders[0] = replace(orders[0], desired_notional=orders[0].desired_notional + 100)
        periods[0] = replace(periods[0], orders=tuple(orders))
    elif kind == "omitted_order":
        periods[0] = replace(periods[0], orders=())
    elif kind == "target":
        targets = (replace(targets[0], weights={"A": 0.01}),) + targets[1:]
    elif kind in ("overnight", "turnover"):
        field = "overnight_mark_return" if kind == "overnight" else "traded_notional_cny"
        periods[0] = replace(periods[0], **{field: getattr(periods[0], field) + 1})
    elif kind.endswith("_summary"):
        field = {
            "writeoff_summary": "writeoff_loss",
            "recovery_summary": "recovery_value",
            "period_summary": "periods",
        }[kind]
        report = replace(
            report, metrics=replace(report.metrics, **{field: getattr(report.metrics, field) + 1})
        )
    else:
        report = replace(report, config=replace(report.config, slippage_bps=0.0))
    report = replace(report, periods=tuple(periods))
    with pytest.raises(ValueError):
        audit_response_account(report, sessions, targets, roundtrip_bps=82)


@pytest.fixture
def anchors(tmp_path):
    original = tmp_path / "original"
    (original / "configs").mkdir(parents=True)
    folder = original / "artifacts/temporal-increments/epoch-001/targets"
    folder.mkdir(parents=True)
    calendar = ["2023-01-03", "2023-01-04", "2024-01-02", "2024-01-03"]
    raw = [asdict(TargetAllocation(d, d + "T08:00:00+08:00", {"A": 0.025}, True)) for d in calendar]
    card = {"targets_file_sha256": {}, "targets_canonical_sha256": {}}
    for name in ("lowvol", "stable_lowrisk"):
        path = folder / f"{name}.json"
        path.write_text(json.dumps(raw, indent=3) + "\n", encoding="utf-8")
        card["targets_file_sha256"][name] = file_sha(path)
        card["targets_canonical_sha256"][name] = sha256_json(raw)
    card_path = original / "configs/v11.11-frozen-stability-observation.json"
    card_path.write_text(json.dumps(card), encoding="utf-8")
    plan = spec()
    plan["anchor_card_sha256"] = file_sha(card_path)
    reg, tids = reserve_trials(tmp_path, plan)
    return reg, tids, original, plan["anchor_card_sha256"], calendar, folder


def test_anchor_original_bytes_preserved_without_support_replacement(anchors):
    reg, tids, original, sha, calendar, folder = anchors
    targets, proofs = load_original_targets(
        reg, tids, original_tree=original, card_sha256=sha, calendar=calendar
    )
    assert set(targets) == {"original_lowvol", "original_stable"}
    assert targets["original_lowvol"][0].weights == {"A": 0.025}
    assert proofs["original_lowvol"]["target_bytes"] == (folder / "lowvol.json").read_bytes()
    assert proofs["original_lowvol"]["file_sha256"] == file_sha(folder / "lowvol.json")
    assert reg.global_trial_count() == 23


@pytest.mark.parametrize("kind", ["bytes", "calendar", "card", "completed", "missing"])
def test_anchor_contract_rejection(anchors, kind):
    reg, tids, original, sha, calendar, folder = anchors
    if kind == "bytes":
        p = folder / "lowvol.json"
        p.write_bytes(p.read_bytes() + b" ")  # Same semantics, changed actual bytes still rejected.
    elif kind == "calendar":
        calendar = calendar[:-1]
    elif kind == "card":
        sha = "b" * 64
    elif kind == "completed":
        reg.record_trial_result(tids["original_lowvol-82"], "{}")
    else:
        tids.pop("original_lowvol-82")
    with pytest.raises((ValueError, KeyError)):
        load_original_targets(reg, tids, original_tree=original, card_sha256=sha, calendar=calendar)
