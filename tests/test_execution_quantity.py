import pytest

from stephen_quant.baseline.execution_quantity import (
    audit_saved_account,
    buy_rule,
    buy_ticket,
    minimum_commission_gap,
)


def test_main_rounds_down_without_exceeding_cash():
    rule = buy_rule("600000.SH", "2023-01-03")
    assert buy_ticket(1999.99, 10, rule)["raw_quantity"] == 100
    assert buy_ticket(2000, 10, rule)["raw_quantity"] == 200
    assert buy_ticket(999, 10, rule)["below_minimum"]
    assert buy_ticket(0, 10, rule)["unallocated_notional"] == 0
    assert not buy_ticket(0, 10, rule)["below_minimum"]


def test_star_is_minimum_200_not_multiple_200():
    rule = buy_rule("688001", "2024-01-02")
    assert buy_ticket(2010, 10, rule)["raw_quantity"] == 201
    assert buy_ticket(1990, 10, rule)["raw_quantity"] == 0
    assert buy_ticket(2_000_000, 10, rule)["raw_quantity"] == 100_000
    assert buy_ticket(2_000_000, 10, rule)["single_ticket_maximum_bound"]


@pytest.mark.parametrize(
    "code,day",
    [
        ("600001.SZ", "2023-01-03"),
        ("688001.SH", "2025-01-03"),
        ("830001.BJ", "2023-01-03"),
        ("900001.SH", "2023-01-03"),
        ("510300.SH", "2023-01-03"),
        ("garbage", "2023-01-03"),
    ],
)
def test_unknown_board_date_and_suffix_rejected(code, day):
    with pytest.raises(ValueError):
        buy_rule(code, day)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf")])
def test_invalid_budget_rejected(value):
    with pytest.raises(ValueError):
        buy_ticket(value, 10, buy_rule("000001", "2023-01-03"))


def test_minimum_fee_is_not_applied_to_zero_or_twice_to_sign():
    assert minimum_commission_gap(0) == 0
    assert minimum_commission_gap(1000) == pytest.approx(4.4)
    assert minimum_commission_gap(-1000) == pytest.approx(4.4)
    assert minimum_commission_gap(10000) == 0


def test_saved_account_diagnostic_does_not_fabricate_raw_positions():
    periods = [
        {
            "date": "2023-01-03",
            "positions": [{"instrument": "600001", "shares": 12.345}],
            "orders": [{"instrument": "600001", "executed_notional": 1999.99}],
        },
        {
            "date": "2023-01-04",
            "positions": [],
            "orders": [{"instrument": "600001", "executed_notional": -2200}],
        },
    ]
    prices = {
        ("2023-01-03", "600001"): {
            "open": 10,
            "factor": 2,
            "previous_factor": 2,
            "previous_date": "2022-12-30",
        },
        ("2023-01-04", "600001"): {
            "open": 9,
            "factor": 2.2,
            "previous_factor": 2,
            "previous_date": "2023-01-03",
        },
    }
    s, tickets, review = audit_saved_account(periods, prices)
    assert s["held_factor_change_keys"] == 1 and len(review) == 1
    assert tickets[0]["raw_quantity"] == 100  # Raw 10, not adjusted 20.
    assert s["extra_minimum_commission_cny"] == pytest.approx(7.480006)
    assert not s["physical_execution_verified"] and not s["validated_alpha"]
    assert "net_total_return" not in s
    assert s["sell_tickets"] == 1 and len(tickets) == 1
    assert periods[0]["positions"][0]["shares"] == 12.345


def test_missing_prices_and_unsupported_boards_stay_missing():
    p = [
        {
            "date": "2023-01-03",
            "positions": [],
            "orders": [
                {"instrument": "600001", "executed_notional": 1000},
                {"instrument": "830001.BJ", "executed_notional": 1000},
            ],
        }
    ]
    s, tickets, _ = audit_saved_account(p, {("2023-01-03", "830001.BJ"): {"open": 10}})
    assert s["missing_buy_prices"] == 1 and s["unsupported_buy_tickets"] == 1
    assert s["unallocated_buy_fraction"] is None and len(tickets) == 2
