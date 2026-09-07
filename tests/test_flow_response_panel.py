import math
from datetime import date, timedelta

import numpy as np
import pytest

from stephen_quant.qmt.flow_response_panel import build_response_panel


def daily_source(count=85):
    days = [str(date(2022, 1, 1) + timedelta(days=i)) for i in range(count)]
    rows = [
        {
            "trade_date": d,
            "instrument": n,
            "name": "Example",
            "open": 10 + i / 100,
            "close": 10 + i / 100 + 0.01 * math.sin(i),
            "adjustment_factor": 1.0,
            "amount": 100_000.0 + i * 100,
            "volume": 10000.0,
            "available_at": f"{d}T17:00:00+08:00",
        }
        for i, d in enumerate(days)
        for n in ("600001", "600002")
    ]
    return days, rows


def test_independent_risk_units_and_lagged_capacity():
    days, rows = daily_source()
    risk, bars, _ = build_response_panel(rows, days)
    values = [r for r in rows if r["instrument"] == "600001"]
    p = np.asarray([r["close"] for r in values[-21:]])
    expected = {
        "volatility_20": np.std(np.diff(np.log(p)), ddof=1),
        "ret_20": p[-1] / p[0] - 1,
        "liquidity": np.mean([r["amount"] * 1000 for r in values[-60:]]),
    }
    assert risk[days[-1]]["600001"] == pytest.approx(expected)
    assert bars[days[-1]]["600001"].capacity_cny == pytest.approx(
        0.05 * np.mean([r["amount"] * 1000 for r in values[-61:-1]])
    )
    assert not risk[days[19]] and len(risk[days[20]]) == 2
    assert bars[days[0]]["600001"].capacity_cny == 0


def test_global_gap_resets_risk_and_open_capacity():
    days, rows = daily_source()
    rows = [r for r in rows if (r["trade_date"], r["instrument"]) != (days[50], "600001")]
    risk, bars, _ = build_response_panel(rows, days)
    assert "600001" not in risk[days[70]] and "600001" in risk[days[71]]
    assert bars[days[51]]["600001"].capacity_cny == 0
    assert bars[days[52]]["600001"].capacity_cny > 0


def test_unavailable_daily_before_poison_and_no_retroactive_backfill():
    days, rows = daily_source()
    row = next(r for r in rows if r["trade_date"] == days[50])
    row.update(available_at="2024-01-01T17:00:00+08:00", close="poison", amount="poison")
    risk, bars, quality = build_response_panel(rows, days)
    assert "600001" not in bars[days[50]] and "600001" not in risk[days[70]]
    assert bars[days[51]]["600001"].capacity_cny == 0
    assert quality["daily_not_available"] == 1


def test_st_and_illiquid_ineligible_but_not_removed_from_execution_marks():
    days, rows = daily_source()
    rows[-2]["name"] = "*ST Test"
    for r in rows:
        if r["instrument"] == "600002":
            r["amount"] = 100.0
    risk, bars, _ = build_response_panel(rows, days)
    assert not risk[days[-1]] and len(bars[days[-1]]) == 2


def test_adjustment_and_no_reported_trade_handling():
    days, rows = daily_source()
    before = build_response_panel(rows, days)
    for r in rows:
        if r["trade_date"] >= days[40]:
            r["open"] /= 2
            r["close"] /= 2
            r["adjustment_factor"] = 2
    after = build_response_panel(rows, days)
    assert before[0] == after[0]
    assert before[1][days[-1]]["600001"].open_price == after[1][days[-1]]["600001"].open_price
    rows[-2]["volume"] = 0
    bar = build_response_panel(rows, days)[1][days[-1]]["600001"]
    assert not bar.can_buy_open and not bar.can_sell_open
    assert bar.tradability_reason == "no_reported_trades"


def test_appended_values_cannot_change_earlier_risk_or_capacity():
    days, rows = daily_source()
    before = build_response_panel([r for r in rows if r["trade_date"] <= days[65]], days[:66])
    for r in rows:
        if r["trade_date"] > days[65]:
            r.update(amount=1e9, close=999.0, open=888.0)
    after = build_response_panel(rows, days)
    assert before[0] == {d: after[0][d] for d in days[:66]}
    assert before[1] == {d: after[1][d] for d in days[:66]}


@pytest.mark.parametrize("kind", ["duplicate", "calendar", "naive", "empty", "overflow"])
def test_panel_contract_rejections(kind):
    days, rows = daily_source()
    if kind == "duplicate":
        rows.append(rows[0])
    elif kind == "calendar":
        rows[0]["trade_date"] = "2026-01-01"
    elif kind == "naive":
        rows[0]["available_at"] = days[0] + "T17:00:00"
    elif kind == "empty":
        rows = [r for r in rows if r["trade_date"] != days[0]]
    else:
        rows[0]["amount"] = 1e308
    with pytest.raises(ValueError):
        build_response_panel(rows, days)
