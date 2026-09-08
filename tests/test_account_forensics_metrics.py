"""Small explicit saved cash/NAV fixtures for report arithmetic, not alpha search."""

from copy import deepcopy

import pytest

from stephen_quant.discovery.account_forensics_metrics import account_summary, primary_difference


def report():
    dates = ["2023-12-28", "2023-12-29", "2024-01-02", "2024-01-03"]
    periods, previous = [], 1000
    for dt, nav in zip(dates, (1100, 990, 1089, 1197.9), strict=True):
        periods.append({"trade_date": dt, "previous_nav": previous, "end_nav": nav,
                        "net_return": nav / previous - 1, "cash": nav / 10,
                        "traded_notional_cny": previous * .2, "total_cost": 1,
                        "marks": [{"synthetic": True}], "writeoff_positions": 0,
                        "writeoff_loss": 0, "recovery_positions": 0, "recovery_value": 0})
        previous = nav
    return dates, {"periods": periods, "metrics": {
        "initial_nav": 1000, "final_nav": 1197.9, "net_total_return": .1979,
        "max_drawdown": -.1, "total_cost": 4}}


def test_years_carry_capital_and_turnover_is_not_membership_churn():
    dates, saved = report()
    before = deepcopy(saved)
    out = account_summary(saved, calendar=dates)
    assert saved == before
    assert out["continuous"]["profit_cny"] == pytest.approx(197.9)
    assert out["years"]["2024"]["opening_nav_cny"] == 990
    assert out["years"]["2024"]["net_return"] == pytest.approx(.21)
    assert out["years"]["2024"]["profit_cny"] == pytest.approx(207.9)
    assert out["continuous"]["mean_daily_one_way_turnover"] == pytest.approx(.1)
    assert out["continuous"]["sum_one_way_turnover"] == pytest.approx(.4)
    assert out["continuous"]["mean_cash_nav_weight"] == pytest.approx(.1)
    assert not out["validated_alpha"]


def test_primary_differences_do_not_manufacture_court_statistics():
    dates, saved = report()
    out = primary_difference(saved, saved, calendar=dates)
    for w in out["windows"].values():
        assert w["net_return_difference_pp"] == w["profit_difference_cny"] == 0
        assert w["paired_mean_net_return_difference_bps"] == 0
    assert out["dsr"] is out["pbo"] is out["placebo_pvalue"] is None
    assert not out["validated_alpha"]


def test_different_accounts_have_correct_paired_means_and_actual_carry_profit():
    dates, saved = report()
    flat = deepcopy(saved)
    for p in flat["periods"]:
        p.update(previous_nav=1000, end_nav=1000, net_return=0, cash=100)
    flat["metrics"].update(final_nav=1000, net_total_return=0, max_drawdown=0)
    windows = primary_difference(saved, flat, calendar=dates)["windows"]
    assert windows["continuous"]["net_return_difference_pp"] == pytest.approx(19.79)
    assert windows["continuous"]["profit_difference_cny"] == pytest.approx(197.9)
    assert windows["continuous"]["paired_mean_net_return_difference_bps"] == pytest.approx(500)
    assert windows["2023"]["profit_difference_cny"] == pytest.approx(-10)
    assert windows["2024"]["net_return_difference_pp"] == pytest.approx(21)
    assert windows["2024"]["profit_difference_cny"] == pytest.approx(207.9)  # Not210.
    assert windows["2024"]["paired_mean_net_return_difference_bps"] == pytest.approx(1000)


@pytest.mark.parametrize("change", ["calendar", "nav", "fees", "drawdown"])
def test_report_mismatch_rejected(change):
    dates, saved = report()
    if change == "calendar":
        dates.pop()
    elif change == "nav":
        saved["periods"][1]["previous_nav"] = 1000
    elif change == "fees":
        saved["metrics"]["total_cost"] = 3
    elif change == "drawdown":
        saved["metrics"]["max_drawdown"] = 0
    with pytest.raises(ValueError):
        account_summary(saved, calendar=dates)
