from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from stephen_quant.discovery.portfolio_native import PortfolioObservation, PortfolioPolicy
from stephen_quant.discovery.v10_generator import generate_v10_candidates
from stephen_quant.workflows.v10_empirical import (
    _cross_source_panel,
    _observations,
    _panel,
    _placebo,
    _predictor_quality,
    _regime_attribution,
    _robust_discovery_key,
    _signed_expression,
)


def test_v10_empirical_panel_uses_next_open_and_unsealed_features(tmp_path: Path) -> None:
    root = tmp_path / "warehouse"
    (root / "catalog").mkdir(parents=True)
    connection = duckdb.connect(str(root / "catalog" / "warehouse.duckdb"))
    try:
        connection.execute(
            "CREATE TABLE qd_daily_current AS SELECT DATE '2021-10-01'+CAST(day AS INTEGER) trade_date, "
            "printf('%06d.SZ',asset) instrument, 10.0+asset/100.0+day/1000.0 \"close\", "
            "10.0+asset/100.0+day/1000.0 \"open\", 1000000.0+asset*1000 amount, 1.0 adjustment_factor "
            "FROM range(0,180) d(day), range(1,61) a(asset)"
        )
        connection.execute(
            "CREATE TABLE qd_minute_features_current AS SELECT trade_date,instrument,"
            "0.001*CAST(substr(instrument,1,6) AS INTEGER) intraday_return,0.01 late_30_return,"
            "0.02 realized_volatility,0.001 vwap_deviation,0.2 opening_volume_share,"
            "0.3 closing_volume_share,0.000001 amihud_intraday,0.005 multiscale_divergence,false sealed "
            "FROM qd_daily_current"
        )
    finally:
        connection.close()
    rows = _panel(root, "2022-01-01", "2022-03-31")
    assert rows
    assert all(row["execution_date"] > row["signal_date"] for row in rows)
    assert all(row["exit_date"] > row["execution_date"] for row in rows)


def test_v10_empirical_omits_cross_sections_smaller_than_frozen_top_k() -> None:
    candidate = generate_v10_candidates(
        budget=1, enabled_sources=("minute_features",)
    ).candidates[0]
    rows = tuple(
        {
            "signal_date": "2022-01-03",
            "execution_date": "2022-01-04",
            "exit_date": "2022-02-01",
            "instrument": f"{index:06d}.SZ",
            candidate.fields[0].name: float(index),
            "forward_return": index / 1000,
            "prior_adv": 1_000_000.0,
        }
        for index in range(39)
    )
    assert _observations(rows, candidate) == ()


def test_v10_centered_interaction_preserves_signed_cross_section() -> None:
    candidate = next(
        item
        for item in generate_v10_candidates(budget=500).candidates
        if item.operator == "centered_interaction" and len(item.fields) == 2
    )
    rows = tuple(
        {
            "signal_date": "2022-01-03",
            "execution_date": "2022-01-04",
            "exit_date": "2022-02-01",
            "instrument": f"{index:06d}.SZ",
            candidate.fields[0].name: float(index),
            candidate.fields[1].name: float((index * 7) % 40),
            "forward_return": index / 1000,
            "prior_adv": 1_000_000.0,
        }
        for index in range(40)
    )
    scores = [item.score for item in _observations(rows, candidate)]
    assert min(scores) < 0 < max(scores)


def test_v10_report_expression_includes_candidate_direction() -> None:
    candidates = generate_v10_candidates(budget=500).candidates
    positive = next(item for item in candidates if item.direction > 0)
    negative = next(item for item in candidates if item.direction < 0)
    assert _signed_expression(positive) == positive.expression
    assert _signed_expression(negative) == f"-({negative.expression})"


def test_v10_universe_placebo_perturbs_membership_not_signal(monkeypatch) -> None:
    rows = tuple(
        PortfolioObservation(
            "2022-01-04",
            f"{index:06d}.SZ",
            float(index),
            index / 1000,
            0.0,
            1_000_000.0,
            "2022-01-03T18:00:00+08:00",
            "2022-01-04T09:30:00+08:00",
        )
        for index in range(50)
    )
    sizes: list[int] = []

    def fake_evaluate(sample, *, policy):
        sizes.append(len(sample))
        return SimpleNamespace(net_excess_total_return=0.0)

    monkeypatch.setattr(
        "stephen_quant.workflows.v10_empirical.evaluate_portfolio_native", fake_evaluate
    )
    policy = PortfolioPolicy(top_k=40)
    observed = SimpleNamespace(net_excess_total_return=1.0)
    assert _placebo(rows, observed, policy, "universe") == 0.01
    assert set(sizes) == {40}


def test_v10_robust_key_prefers_two_positive_halves() -> None:
    stable = SimpleNamespace(
        periods=tuple(
            SimpleNamespace(net_excess_return=value, benchmark_return=(-1) ** index * 0.01)
            for index, value in enumerate((0.02,) * 6)
        ),
        double_cost_total_return=0.08,
        annualized_net_excess_sharpe=1.0,
        total_turnover=4.0,
    )
    spike = SimpleNamespace(
        periods=tuple(
            SimpleNamespace(net_excess_return=value, benchmark_return=(-1) ** index * 0.01)
            for index, value in enumerate((0.12, 0.12, 0.12, -0.04, -0.04, -0.04))
        ),
        double_cost_total_return=0.20,
        annualized_net_excess_sharpe=2.0,
        total_turnover=4.0,
    )
    assert _robust_discovery_key(stable) > _robust_discovery_key(spike)


def test_v10_regime_attribution_compounds_up_and_down_markets() -> None:
    report = SimpleNamespace(
        periods=(
            SimpleNamespace(benchmark_return=-0.01, net_excess_return=0.02),
            SimpleNamespace(benchmark_return=0.01, net_excess_return=0.03),
            SimpleNamespace(benchmark_return=-0.02, net_excess_return=0.04),
        )
    )
    regimes = {item.regime: item for item in _regime_attribution(report)}
    assert regimes["benchmark_down"].periods == 2
    assert regimes["benchmark_down"].net_excess_total_return == pytest.approx(0.0608)
    assert regimes["benchmark_up"].net_excess_total_return == pytest.approx(0.03)


def test_v10_predictor_quality_rejects_cross_sectional_constant_without_labels() -> None:
    rows = tuple(
        {
            "signal_date": f"2022-01-{day:02d}",
            "good": float(asset),
            "constant": 0.0,
            "forward_return": 999.0,
        }
        for day in range(1, 6)
        for asset in range(25)
    )
    eligible, rejected = _predictor_quality(rows, ("good", "constant"))
    assert eligible == ("good",)
    assert rejected == ("constant",)


def test_v10_cross_source_panel_uses_prior_close_and_execution_auction(monkeypatch) -> None:
    base = ({
        "signal_date": "2022-01-03",
        "execution_date": "2022-01-04",
        "instrument": "000001.SZ",
        "amount_cny": 1_000_000.0,
        "prior_adv": 2_000_000.0,
    },)
    monkeypatch.setattr(
        "stephen_quant.workflows.v10_empirical._panel", lambda *args, **kwargs: base
    )
    monkeypatch.setattr(
        "stephen_quant.workflows.v10_empirical.latest_multisource_snapshot",
        lambda root: "a" * 64,
    )
    values = {
        "fund_flow": (
            "2022-01-03",
            (
                ("net_inflow_amount", 100_000.0),
                ("large_buy_amount", 80_000.0),
                ("extra_large_buy_amount", 40_000.0),
                ("large_sell_amount", 20_000.0),
                ("extra_large_sell_amount", 10_000.0),
            ),
        ),
        "auction": (
            "2022-01-04",
            (("auction_return", 0.02), ("auction_amount", 200_000.0)),
        ),
        "chip": (
            "2022-01-03",
            (
                ("chip_win_rate", 0.6),
                ("chip_weighted_cost", 10.0),
                ("chip_cost_15", 8.0),
                ("chip_cost_85", 12.0),
            ),
        ),
    }

    def fake_load(root, *, source_kind, **kwargs):
        day, cells = values[source_kind]
        row = SimpleNamespace(trade_date=day, instrument="000001.SZ", values=cells)
        return SimpleNamespace(observations=(row,))

    monkeypatch.setattr(
        "stephen_quant.workflows.v10_empirical.load_warehouse_alternative", fake_load
    )
    rows, snapshot = _cross_source_panel(Path("."), "2022-01-01", "2022-12-31")
    assert snapshot == "a" * 64
    assert rows[0]["net_inflow_ratio"] == 0.1
    assert rows[0]["main_inflow_ratio"] == 0.09
    assert rows[0]["auction_return"] == 0.02
    assert rows[0]["auction_amount_ratio"] == 0.1
    assert rows[0]["profit_ratio"] == 0.6
    assert rows[0]["concentration"] == 0.4
