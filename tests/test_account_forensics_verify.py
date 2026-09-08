"""Independent arithmetic catches producer-output mutations on synthetic data."""

import json
from copy import deepcopy

import pytest
from test_account_forensics_metrics import report
from test_account_forensics_structure import exposure_fixture

from stephen_quant.discovery.account_forensics_metrics import account_summary, primary_difference
from stephen_quant.discovery.account_forensics_verify import (
    compare,
    verify_compact,
    verify_exposures,
    verify_metrics,
    verify_primary,
)


def saved():
    dates, value = report()
    for p in value["periods"]:
        p["marks"] = [{"instrument": "synthetic", "market_value": p["end_nav"] - p["cash"]}]
        p["orders"] = [{"instrument": "synthetic", "total_cost": p["total_cost"],
                        "executed_notional": p["traded_notional_cny"]}]
        p["stale_position_days"] = 0
    return dates, value


def test_independent_annual_carry_and_paired_metrics():
    calendar, value = saved()
    summary = account_summary(value, calendar=calendar)
    assert verify_metrics(value, summary, calendar=calendar)["arithmetic_verified"]
    assert summary["years"]["2024"]["profit_cny"] == pytest.approx(207.9)
    primary = primary_difference(value, value, calendar=calendar)
    assert verify_primary(value, value, primary, calendar=calendar)["primary_arithmetic_verified"]
    primary["windows"]["continuous"]["net_return_difference_pp"] = 1
    with pytest.raises(ValueError):
        verify_primary(value, value, primary, calendar=calendar)


def test_nonzero_primary_separate_annual_capital_and_tampering():
    calendar, response = saved()
    risk = deepcopy(response)
    previous = 1000
    for p, nav in zip(risk["periods"], (1050, 1050, 1155, 1097.25), strict=True):
        p.update(previous_nav=previous, end_nav=nav, net_return=nav / previous - 1, cash=nav / 10)
        p["marks"][0]["market_value"] = nav * .9
        previous = nav
    risk["metrics"].update(final_nav=1097.25, net_total_return=.09725, max_drawdown=-.05)
    primary = primary_difference(response, risk, calendar=calendar)
    assert verify_primary(response, risk, primary, calendar=calendar)["primary_arithmetic_verified"]
    windows = primary["windows"]
    assert windows["continuous"]["net_return_difference_pp"] == pytest.approx(10.065)
    assert windows["continuous"]["profit_difference_cny"] == pytest.approx(100.65)
    assert windows["continuous"]["paired_mean_net_return_difference_bps"] == pytest.approx(250)
    assert windows["2023"]["profit_difference_cny"] == pytest.approx(-60)
    assert windows["2024"]["net_return_difference_pp"] == pytest.approx(16.5)
    assert windows["2024"]["profit_difference_cny"] == pytest.approx(160.65)
    for window in windows:
        mutated = deepcopy(primary)
        mutated["windows"][window]["profit_difference_cny"] += 1
        with pytest.raises(ValueError):
            verify_primary(response, risk, mutated, calendar=calendar)


@pytest.mark.parametrize("field", ["profit_cny", "opening_nav_cny", "fees_cny",
                                   "mean_daily_one_way_turnover", "mean_cash_nav_weight",
                                   "max_drawdown", "sharpe_252_zero_risk_free"])
def test_each_metric_mutation_is_refused(field):
    calendar, value = saved()
    summary = account_summary(value, calendar=calendar)
    summary["continuous"][field] += 1
    with pytest.raises(ValueError):
        verify_metrics(value, summary, calendar=calendar)


@pytest.mark.parametrize("change", ["cash", "orders", "traded_notional_cny", "previous_nav"])
def test_original_amount_contradictions_are_refused(change):
    calendar, value = saved()
    summary = account_summary(value, calendar=calendar)
    if change == "orders":
        value["periods"][1][change][0]["total_cost"] += 1
    else:
        value["periods"][1][change] += 1
    with pytest.raises(ValueError):
        verify_metrics(value, summary, calendar=calendar)


@pytest.mark.parametrize("change", [None, "missing", "extra", "nav", "fields"])
def test_compact_full_every_row(tmp_path, change):
    _, value = saved()
    rows = [{"date": p["trade_date"], "nav": p["end_nav"], "return": p["net_return"],
             "cash": p["cash"], "cost": p["total_cost"], "stale_positions": 0,
             "writeoff_loss": p["writeoff_loss"], "positions": p["marks"], "orders": p["orders"]}
            for p in value["periods"]]
    if change == "missing":
        rows.pop()
    elif change == "extra":
        rows.append(rows[-1])
    elif change == "nav":
        rows[1]["nav"] += 1
    elif change == "fields":
        rows[1]["hidden"] = True
    path = tmp_path / "compact.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if change is None:
        assert verify_compact(value, path) == 4
    else:
        with pytest.raises(ValueError):
            verify_compact(value, path)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), "1"])
def test_nonfinite_or_non_numeric_not_accepted(value):
    with pytest.raises(ValueError):
        compare(value, 1.0)


@pytest.mark.parametrize("change", [None, "mapping_asof", "invested_cny", "unknown_names",
                                   "zero_value_held_names", "unknown_invested_weight"])
def test_independent_exposure_keeps_unknown_and_zero_holdings(change):
    from stephen_quant.discovery.account_forensics_structure import prior_day_exposures

    value, calendar, ranks = exposure_fixture()
    emitted = prior_day_exposures(value, source_calendar=calendar, ranks=ranks)
    if change == "mapping_asof":
        emitted["daily"][0][change] = "2023-01-03"
    elif change in ("unknown_names", "zero_value_held_names"):
        emitted["daily"][0][change] = []
    elif change is not None:
        emitted["daily"][0][change] += 1
    if change is None:
        assert verify_exposures(value, emitted, source_calendar=calendar,
                                ranks=ranks)["exposure_arithmetic_verified"]
    else:
        with pytest.raises(ValueError):
            verify_exposures(value, emitted, source_calendar=calendar, ranks=ranks)
