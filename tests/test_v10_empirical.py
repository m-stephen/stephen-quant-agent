from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import duckdb

from stephen_quant.discovery.portfolio_native import PortfolioObservation, PortfolioPolicy
from stephen_quant.discovery.v10_generator import generate_v10_candidates
from stephen_quant.workflows.v10_empirical import (
    _observations,
    _panel,
    _placebo,
    _predictor_quality,
    _robust_discovery_key,
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
        periods=tuple(SimpleNamespace(net_excess_return=value) for value in (0.02,) * 6),
        double_cost_total_return=0.08,
        annualized_net_excess_sharpe=1.0,
        total_turnover=4.0,
    )
    spike = SimpleNamespace(
        periods=tuple(
            SimpleNamespace(net_excess_return=value)
            for value in (0.12, 0.12, 0.12, -0.04, -0.04, -0.04)
        ),
        double_cost_total_return=0.20,
        annualized_net_excess_sharpe=2.0,
        total_turnover=4.0,
    )
    assert _robust_discovery_key(stable) > _robust_discovery_key(spike)


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
