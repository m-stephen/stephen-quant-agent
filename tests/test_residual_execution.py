"""Fixed synthetic executable controls; these are not market Alpha evidence."""

import hashlib
import json
import random
from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import (
    StatefulBar,
    StatefulExecutionConfig,
    run_stateful_execution,
)
from stephen_quant.discovery.incremental_alpha import audit_account
from stephen_quant.discovery.reliable_research import ResearchDay
from stephen_quant.discovery.residual_execution import fit_stages, guarded_targets
from stephen_quant.discovery.residual_mechanisms import FIELDS, fit_year, ranked_rows
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest


def synthetic_days(kind):
    rng = random.Random(11101)
    features = {f"S{i:03d}": {k: rng.uniform(1, 2) for k in FIELDS} for i in range(200)}
    rows = ranked_rows(features)
    dates = [date(2022, 1, 3) + timedelta(days=i) for i in range(340)]
    dates += [date(2023, 1, 3) + timedelta(days=i) for i in range(100)]
    days = []
    for i, dt in enumerate(dates):
        iso = dt.isoformat()
        bars = []
        for n in features:
            increment = 0.004 * rows[n]["z"]["flow_reversal"] if kind == "planted" else 0.0
            price = 10 * (1 + increment) ** i
            bars.append(StatefulBar(iso, n, price, price, 1e7, f"{iso}T08:00:00+08:00"))
        days.append(ResearchDay(iso, features, tuple(bars)))
    return tuple(days)


def execute(tmp_path, kind):
    days = synthetic_days(kind)
    frozen = hashlib.sha256(
        json.dumps([asdict(d) for d in days], sort_keys=True).encode()
    ).hexdigest()
    registry = ExperimentRegistry(tmp_path / "synthetic.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic-days": frozen}))
    eid = registry.create_experiment(
        ExperimentSpec("synthetic-only", kind, sid, "v11.10.1-synthetic")
    )
    common = TrialSpec(
        eid,
        "synthetic",
        "flow_reversal",
        "{}",
        11101,
        "2022-01-03",
        "2022-12-31",
        "2023-01-01",
        "2023-12-31",
        "unused",
        "unused",
        fit_stages=fit_stages((2023,)),
    )
    # Reserve fit, candidate, matched control, blocked-fill account before fitting.
    tids = [
        registry.create_trial(
            replace(
                common, model_name=name, fit_stages=() if name == "control" else common.fit_stages
            )
        )[0]
        for name in ("fit", "candidate", "control", "blocked")
    ]
    model = fit_year(days, 2023)
    path = tmp_path / "2023-model.json"
    path.write_text(json.dumps(model, sort_keys=True))
    for tid in (tids[0], tids[1], tids[3]):
        registry.record_model_fit(tid, "2023", model=model, artifact_path=path)
    registry.record_trial_result(tids[0], json.dumps(model))
    window = tuple(d for d in days if d.date.startswith("2023"))
    cfg = StatefulExecutionConfig(
        maximum_position_weight=0.025, commission_bps=6, sell_tax_bps=10, slippage_bps=30
    )
    reports, diagnostics = {}, {}
    for name, tid in zip(("candidate", "control", "blocked"), tids[1:], strict=True):
        policy = "risk_hash" if name == "control" else "flow_reversal"
        targets, detail = guarded_targets(
            registry, tid, window, {2023: model}, policy, {2023: path}
        )
        sessions = tuple(d.bars for d in window)
        if name == "blocked":
            sessions = tuple(tuple(replace(b, can_buy_open=False) for b in s) for s in sessions)
        report = run_stateful_execution(sessions, targets, cfg, initial_nav=3_000_000)
        assert audit_account(report)["pass"]
        registry.record_trial_result(tid, report.to_json())
        reports[name] = report
        diagnostics[name] = detail
    assert registry.trial_count(eid) == 4
    return reports, diagnostics


@pytest.mark.parametrize("kind", ["planted", "null"])
def test_native_fit_to_costed_stateful_account_and_blocked_fills(tmp_path, kind):
    reports, diagnostics = execute(tmp_path, kind)
    candidate, control, blocked = (reports[k] for k in ("candidate", "control", "blocked"))
    assert blocked.metrics.final_nav == 3_000_000
    assert blocked.metrics.total_cost == 0
    assert blocked.metrics.blocked_orders > 0
    assert candidate.metrics.total_cost > 0
    assert candidate.metrics.final_nav == pytest.approx(candidate.periods[-1].end_nav)
    swaps = sum(d["hurdle_replacements"] for d in diagnostics["candidate"])
    if kind == "planted":
        assert swaps > 0
        assert candidate.metrics.net_total_return > 0
        assert candidate.metrics.net_total_return - control.metrics.net_total_return > 0.03
    else:
        assert swaps == 0
        assert candidate.to_json() == control.to_json()
        assert candidate.metrics.net_total_return < 0


def test_guard_rejects_mutated_model_before_actual_allocation(tmp_path):
    days = synthetic_days("planted")
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    sid = registry.register_snapshot(build_composite_snapshot_manifest({"synthetic": "a" * 64}))
    eid = registry.create_experiment(ExperimentSpec("synthetic", "guard", sid, "test"))
    spec = TrialSpec(
        eid,
        "model",
        "flow",
        "{}",
        0,
        "unused",
        "unused",
        "unused",
        "unused",
        "unused",
        "unused",
        fit_stages=fit_stages((2023,)),
    )
    tid, _ = registry.create_trial(spec)
    model = fit_year(days, 2023)
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    registry.record_model_fit(tid, "2023", model=model, artifact_path=path)
    model["models"]["flow_reversal"]["slope"] *= 2
    window = tuple(d for d in days if d.date.startswith("2023"))
    with pytest.raises(ValueError, match="artifact bytes"):
        guarded_targets(registry, tid, window, {2023: model}, "flow_reversal", {2023: path})
