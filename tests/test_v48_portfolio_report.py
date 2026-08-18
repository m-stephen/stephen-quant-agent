from __future__ import annotations

import math
from pathlib import Path

from stephen_quant.workflows.v41_semantic_alpha import UsageEvent
from stephen_quant.workflows.v47_low_turnover_alpha import BufferedAvoidAccountingEvent
from stephen_quant.workflows.v48_portfolio_report import compare_index, summarize_accounting


def _event(
    day: str,
    end_day: str,
    gross: float,
    benchmark: float,
    cost: float,
) -> BufferedAvoidAccountingEvent:
    net = gross - cost
    return BufferedAvoidAccountingEvent(
        day=day,
        end_day=end_day,
        offset=0,
        gross_portfolio_return=gross,
        benchmark_return=benchmark,
        net_portfolio_return=net,
        excess_return=net - benchmark,
        turnover=0.1,
        cost_rate=cost,
        selected_instruments=40,
        retained_instruments=30,
    )


def test_accounting_summary_reports_absolute_cny_and_existing_excess() -> None:
    events = (
        _event("2025-01-02", "2025-01-22", 0.010, 0.005, 0.001),
        _event("2025-01-03", "2025-01-23", -0.002, 0.001, 0.001),
    )

    controls = (
        UsageEvent("2025-01-02", 0, 0.003, 0.1, 0.001, True),
        UsageEvent("2025-01-03", 0, -0.002, 0.1, 0.001, True),
    )

    result = summarize_accounting(
        "full",
        events,
        nav=3_000_000,
        clipped=0.0,
        matched_control=controls,
    )

    expected_net = 1.009 * 0.997 - 1
    assert math.isclose(result.net_total_return, expected_net)
    assert math.isclose(result.net_profit_cny, 3_000_000 * expected_net)
    assert math.isclose(result.final_nav_cny, 3_000_000 * (1 + expected_net))
    assert math.isclose(result.total_cost_cny, 6_000)
    assert math.isclose(result.cross_section_benchmark_return, 1.005 * 1.001 - 1)
    assert math.isclose(result.existing_model_excess_return, 1.004 * 0.996 - 1)
    assert math.isclose(result.mean_retained_fraction, 0.75)
    expected_control = 1.008 * 0.999 - 1
    assert math.isclose(result.matched_control_net_return, expected_control)
    assert math.isclose(
        result.factor_value_add_cny,
        3_000_000 * (expected_net - expected_control),
    )


def test_index_comparison_is_truncated_to_real_file_coverage(tmp_path: Path) -> None:
    index = tmp_path / "index.csv"
    index.write_text(
        "日期,开盘价\n20250102,100\n20250103,101\n20250122,105\n",
        encoding="utf-8",
    )
    events = (
        _event("2025-01-02", "2025-01-22", 0.010, 0.005, 0.001),
        _event("2025-01-03", "2025-01-23", -0.002, 0.001, 0.001),
    )

    result = compare_index("test", index, events, nav=3_000_000)

    assert result.comparison_start == "2025-01-02"
    assert result.comparison_end == "2025-01-22"
    assert math.isclose(result.index_price_return, 0.05)
    assert math.isclose(result.candidate_net_return, 0.009)
    assert math.isclose(result.value_advantage_cny, 3_000_000 * (0.009 - 0.05))
