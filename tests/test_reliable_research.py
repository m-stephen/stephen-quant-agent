from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from stephen_quant.baseline.stateful import (
    StatefulExecutionConfig,
    run_stateful_execution,
)
from stephen_quant.discovery.reliability_calibration import (
    family_placebo,
    synthetic_days,
    wilson,
)
from stephen_quant.discovery.reliable_research import (
    ResearchCandidate,
    build_targets,
    candidate_pack,
    candidate_scores,
    fit_prefix_model,
    metric_bundle,
    run_candidate,
    temporal_selection,
    validate_proposal,
)
from stephen_quant.qmt.reliable_panel import freeze_inputs


def _frozen_fixture(folder, *, drop_last=False, missing_minute=False):
    import json

    duckdb = pytest.importorskip("duckdb")
    from stephen_quant.discovery.search_power_dsl import sha256_json
    from stephen_quant.qmt.reliable_panel import file_sha

    folder.mkdir()
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE daily AS SELECT DATE '2021-12-01'+cast(i AS INTEGER) trade_date, "
        "'60000'||cast(j AS VARCHAR)||'.SH' instrument, 'example' AS name, "
        "10.0+i/100 AS open,10.02+i/100 AS close,20000.0 amount,1000.0 volume,1.0 adjustment_factor, "
        "(DATE '2021-12-01'+cast(i AS INTEGER))::TIMESTAMPTZ available_at "
        "FROM range(80) x(i),range(2) y(j)"
    )
    if drop_last:
        conn.execute(
            "DELETE FROM daily WHERE trade_date=DATE '2022-02-18' AND instrument='600000.SH'"
        )
    tables = {
        "daily": "SELECT * FROM daily",
        "minute": "SELECT trade_date,instrument,available_at,0.01 late_30_return,0.02 realized_volatility,0.001 amihud_intraday FROM daily"
        + (" WHERE false" if missing_minute else ""),
        "fund_flow": "SELECT trade_date,instrument,available_at,1000.0 net_inflow_amount FROM daily",
        "chip": "SELECT trade_date,instrument,available_at,8.0 chip_cost_15,12.0 chip_cost_85,10.0 chip_weighted_cost FROM daily",
        "auction": "SELECT trade_date,instrument,available_at,0.01 auction_return FROM daily",
    }
    sources = []
    for name, query in tables.items():
        path = folder / (name + ".parquet")
        escaped = str(path).replace("'", "''")
        conn.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET)")
        sources.append({"source": name, "file": path.name, "sha256": file_sha(path)})
    conn.close()
    (folder / "manifest.json").write_text(
        json.dumps({"sources": sources, "snapshot_sha256": sha256_json(sources)}), encoding="utf-8"
    )


def test_frozen_sql_loader_has_no_future_price_or_minute_intersection_filter(tmp_path):
    from stephen_quant.qmt.reliable_panel import load_frozen_days

    _frozen_fixture(tmp_path / "first")
    _frozen_fixture(tmp_path / "changed", drop_last=True, missing_minute=True)
    original, _ = load_frozen_days(tmp_path / "first")
    changed, _ = load_frozen_days(tmp_path / "changed")
    baseline = ResearchCandidate("baseline", ("ret_20",))
    assert len(original) == len(changed)
    for a, b in zip(original[:-1], changed[:-1], strict=True):
        assert candidate_scores(a.features, baseline) == candidate_scores(b.features, baseline)
    assert build_targets(original, baseline) == build_targets(changed, baseline)


def test_frozen_loader_rejects_changed_bytes(tmp_path):
    from stephen_quant.qmt.reliable_panel import load_frozen_days

    _frozen_fixture(tmp_path / "first")
    with (tmp_path / "first/daily.parquet").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="hash changed"):
        load_frozen_days(tmp_path / "first")


def test_overlap_does_not_discount_raw_trials():
    from stephen_quant.workflows.v114_reliable_epoch import overlap_evidence

    report = overlap_evidence(
        {"a": [1.0, 2.0], "b": [1.0, 2.0]}, {"a": [{"X"}, {"Y"}], "b": [{"X"}, {"Y"}]}
    )
    assert report["pairs"][0]["near_duplicate"]
    assert report["pairs"][0]["mean_actual_holdings_jaccard"] == 1
    assert report["raw_trial_count_reduced"] is False


def test_exact_replay_rejects_changed_code_before_reading_inputs(tmp_path):
    from stephen_quant.workflows.v114_reliable_epoch import replay_epoch, write_json

    write_json(tmp_path / "RESULT.json", {"spec": {"runtime_code_sha256": "invalid"}})
    with pytest.raises(ValueError, match="exact original"):
        replay_epoch(tmp_path)
    assert not (tmp_path / "replays").exists()


def test_exact_replay_executes_accounts_and_appends_zero_trial_ledger(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict

    import stephen_quant.workflows.v114_reliable_epoch as workflow
    from stephen_quant.integrity.registry import ExperimentRegistry

    source, _, _ = synthetic_days(114, True, periods=25)
    days = tuple(
        replace(
            d,
            date=d.date.replace("2022", year),
            bars=tuple(
                replace(
                    b,
                    trade_date=b.trade_date.replace("2022", year),
                    capacity_available_at=b.capacity_available_at.replace("2022", year),
                )
                for b in d.bars
            ),
        )
        for year in ("2023", "2024")
        for d in source
    )
    c = ResearchCandidate("replay", ("ret_20",), horizon=5)
    record = {"identity": c.identity, "inner": {}, "outer": {}}
    for stage, year in (("inner", "2023"), ("outer", "2024")):
        window = tuple(d for d in days if d.date.startswith(year))
        for cost in (1, 2):
            account, _, target_hash = run_candidate(window, c, multiplier=cost)
            base, _, _ = run_candidate(window, c, multiplier=cost, benchmark=True)
            metrics = metric_bundle(account, base)
            metrics["targets_sha256"] = target_hash
            record[stage][str(cost)] = metrics
    registry = ExperimentRegistry(tmp_path / "registry.sqlite3")
    registry.initialize()
    report = {
        "spec": {"runtime_code_sha256": workflow.runtime_code_hash(), "candidates": [asdict(c)]},
        "models": {},
        "candidates": [record],
    }
    workflow.write_json(tmp_path / "RESULT.json", report)
    monkeypatch.setattr(workflow, "load_frozen_days", lambda _: (days, {}))
    monkeypatch.setattr(workflow, "candidate_pack", lambda: (c,))
    result = workflow.replay_epoch(tmp_path)
    assert result["account_windows_compared"] == 4
    assert result["registry_unchanged"] and result["inferential_trial_delta"] == 0
    assert len(list((tmp_path / "replays").glob("*/STARTED.json"))) == 1
    ledger = json.loads(next((tmp_path / "replays").glob("*/RESULT.json")).read_text())
    assert ledger["pass"]


@pytest.mark.parametrize("side", ["high", "low"])
@pytest.mark.parametrize("direction", [-1, 1])
def test_gate_eligibility_does_not_reverse(side, direction):
    features = {f"S{i:03d}": {"ret_20": i / 100, "concentration": i / 100} for i in range(100)}
    candidate = ResearchCandidate(
        "gate", ("ret_20",), direction=direction, gate_field="concentration", gate_side=side
    )
    scores, complete = candidate_scores(features, candidate)
    assert complete == 100
    assert all(int(n[1:]) >= 69 if side == "high" else int(n[1:]) <= 29 for n in scores)
    assert len(scores) < 40


def test_unused_field_does_not_change_baseline():
    features = {f"S{i}": {"ret_20": i / 100} for i in range(100)}
    c = ResearchCandidate("baseline", ("ret_20",))
    before = candidate_scores(features, c)
    for i, row in enumerate(features.values()):
        row["unused_flow"] = float("nan") if i < 10 else 0.2
    assert candidate_scores(features, c) == before


def test_future_price_changes_do_not_change_past_targets():
    days, _, _ = synthetic_days(123, False, periods=40)
    c = ResearchCandidate("baseline", ("ret_20",), horizon=5)
    original, _ = build_targets(days, c)
    damaged = list(days)
    damaged[-1] = replace(
        days[-1],
        bars=tuple(
            replace(b, open_price=b.open_price * 0.4, close_price=b.close_price * 0.5)
            for b in days[-1].bars[1:]
        ),
    )
    changed, _ = build_targets(tuple(damaged), c)
    assert original == changed


def test_daily_mark_detects_intraholding_loss_and_cash_when_gate_empty():
    days, _, _ = synthetic_days(123, False, periods=30)
    c = ResearchCandidate("baseline", ("ret_20",))
    damaged = list(days)
    damaged[10] = replace(
        days[10], bars=tuple(replace(b, close_price=b.close_price * 0.5) for b in days[10].bars)
    )
    account, _, _ = run_candidate(tuple(damaged), c)
    assert account.metrics.max_drawdown < -0.4
    cash_days = tuple(replace(d, features={}) for d in days)
    cash, _, _ = run_candidate(cash_days, c)
    assert cash.metrics.final_nav == 3_000_000
    assert cash.metrics.total_cost == 0


def test_missing_holding_not_deleted_and_compact_benchmark_matches():
    days, _, _ = synthetic_days(114, True, periods=55)
    c = ResearchCandidate("baseline", ("ret_20",))
    targets, _ = build_targets(days, c)
    sessions = tuple(day.bars for day in days)
    config = StatefulExecutionConfig(maximum_position_weight=0.025)
    full = run_stateful_execution(sessions, targets, config)
    compact = run_stateful_execution(sessions, targets, config, retain_details=False)
    assert full.metrics == compact.metrics
    assert [p.end_nav for p in full.periods] == [p.end_nav for p in compact.periods]
    assert all(not p.marks and not p.orders for p in compact.periods)


def test_absolute_active_and_relative_wealth_are_distinct():
    days, _, _ = synthetic_days(114, True, periods=55)
    c = ResearchCandidate("baseline", ("ret_20",))
    account, _, _ = run_candidate(days, c)
    base, _, _ = run_candidate(days, c, benchmark=True)
    metrics = metric_bundle(account, base)
    assert metrics["profit_cny"] == pytest.approx(3_000_000 * metrics["absolute_return"])
    assert metrics["relative_wealth_return"] == pytest.approx(
        (1 + metrics["absolute_return"]) / (1 + metrics["benchmark_return"]) - 1
    )
    assert metrics["excess_percentage_points"] == pytest.approx(
        metrics["absolute_return"] - metrics["benchmark_return"]
    )


def test_temporal_selector_uses_real_purged_manifest_and_declared_winner():
    days = [(date(2023, 1, 1) + timedelta(days=i)).isoformat() for i in range(250)]
    returns = {
        "a": [0.001 + (0.002 if i % 2 else -0.002) for i in range(250)],
        "b": [(0.003 if i < 125 else -0.003) + (0.001 if i % 2 else -0.001) for i in range(250)],
    }
    result = temporal_selection(days, returns, 48)
    assert result["winner"] == "a"
    assert len(result["folds"]) == 20
    assert sum(f["purged_n"] for f in result["folds"]) > 0
    manifest = result["split_manifest"]
    for fold in manifest["folds"]:
        assert not set(fold["train_ids"]) & set(fold["test_ids"])
        assert not set(fold["train_ids"]) & set(fold["purged_ids"])


def test_model_prefix_cannot_fit_outer_labels():
    days, _, _ = synthetic_days(114, True, periods=80)
    c = ResearchCandidate("model", ("ret_20",), "stump", horizon=5)
    model = fit_prefix_model(days, c)
    assert model["fit_end"] < "2023-01-01"
    changed = days[:-1] + (replace(days[-1], date="2024-01-01"),)
    with pytest.raises(ValueError, match="prefix"):
        fit_prefix_model(changed, c)


def test_proposal_contract_and_bounded_pack():
    assert len(candidate_pack()) == 24
    c = validate_proposal(
        {
            "mechanism": "temporary selling pressure",
            "falsifier": "no net improvement",
            "candidate": {"name": "test", "fields": ["ret_20"]},
        }
    )
    assert c.identity
    with pytest.raises(ValueError):
        validate_proposal(
            {
                "mechanism": "bad",
                "falsifier": "none",
                "candidate": {"name": "bad", "fields": ["future_return"]},
            }
        )


def test_proposal_ledger_preserves_rejections_and_budget():
    from stephen_quant.discovery.reliable_research import screen_proposals

    proposal = {
        "mechanism": "selling pressure",
        "falsifier": "no net reversal",
        "candidate": {"name": "test", "fields": ["ret_20"]},
    }
    other = {**proposal, "candidate": {"name": "other", "fields": ["ret_20"]}}
    result = screen_proposals([proposal, proposal, other, {}], maximum=1)
    assert [r["status"] for r in result] == [
        "ACCEPTED_NOT_EXECUTED",
        "REJECTED",
        "REJECTED",
        "REJECTED",
    ]
    assert "duplicate" in result[1]["reason"]
    assert "budget" in result[2]["reason"]


def test_null_uncertainty_and_positive_controls():
    assert wilson(0, 100)[1] < 0.05
    assert wilson(5, 100)[1] > 0.05
    positive = family_placebo({"a": [0.01] * 200, "b": [-0.01] * 200})
    assert positive["p_value"] <= 0.05


def test_sealed_dates_rejected_before_source_connection(tmp_path):
    with pytest.raises(ValueError, match="authorized"):
        freeze_inputs(tmp_path, tmp_path / "bad", end="2025-01-01")
    assert not (tmp_path / "bad").exists()
